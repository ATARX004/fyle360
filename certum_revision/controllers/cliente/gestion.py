# -*- coding: utf-8 -*-
"""Portal cliente: política de revisión del proceso y solicitudes de plazo.

- La política (modo + capas) la fija el nivel 1 del cliente (feature A).
- Las solicitudes de ampliación de plazo (feature D) se enrutan por jerarquía:
  nivel 1 → directo al proveedor; nivel inferior → autoriza el superior y sube.
"""
import logging

from odoo import http
from odoo.http import request

from ..helpers import (
    ROL_CLIENTE,
    _nivel_usuario,
    _rol_en_proceso,
    is_ajax,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)


def _proceso_or_none(proceso_id):
    proc = request.env['certum.rev.proceso'].sudo().browse(int(proceso_id))
    if not proc.exists():
        return None, None
    return proc, _rol_en_proceso(proc)


class CertumRevGestion(http.Controller):

    # ── Política de revisión (nivel 1 del cliente) ────────────────────
    @http.route('/my/proceso/<int:proceso_id>/politica', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def set_politica(self, proceso_id, **post):
        proc, rol = _proceso_or_none(proceso_id)
        if proc is None or rol != ROL_CLIENTE:
            return json_err('No tienes acceso a este proceso.', 403)
        if _nivel_usuario() != 1:
            return json_err('Solo el nivel 1 del cliente define la política de revisión.', 403)

        modo = (post.get('modo') or 'cualquiera').strip()
        if modo not in ('cualquiera', 'secuencial'):
            return json_err('Modo no válido.')
        try:
            capas = int(post.get('capas') or 1)
        except (TypeError, ValueError):
            capas = 1
        capas = max(1, min(20, capas))

        proc.write({
            'revision_modo': modo,
            'revision_capas': capas if modo == 'secuencial' else 1,
            'revision_config': True,
        })
        _logger.info('[AUDIT] set_politica user=%s proceso=%s modo=%s capas=%s',
                     request.env.user.id, proc.id, modo, capas)
        payload = {'ok': True, 'modo': modo, 'capas': proc.revision_capas}
        if is_ajax():
            return json_r(payload)
        return request.redirect('/my/proceso/%d' % proc.id)

    # ── Solicitud de ampliación de plazo ──────────────────────────────
    @http.route('/my/proceso/<int:proceso_id>/solicitar-plazo', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def solicitar_plazo(self, proceso_id, **post):
        proc, rol = _proceso_or_none(proceso_id)
        if proc is None or rol != ROL_CLIENTE:
            return json_err('No tienes acceso a este proceso.', 403)
        try:
            dias = int(post.get('dias') or 0)
        except (TypeError, ValueError):
            dias = 0
        if dias <= 0:
            return json_err('Indica cuántos días adicionales necesitas.')

        nivel = _nivel_usuario() or 99  # sin nivel = el más bajo posible
        # Enrutamiento por jerarquía.
        if nivel == 1:
            estado, autorizador = 'pendiente_proveedor', 0
        else:
            estado, autorizador = 'pendiente_autorizacion', nivel - 1

        sol = request.env['certum.rev.solicitud'].sudo().create({
            'proceso_id': proc.id,
            'solicitante_id': request.env.user.partner_id.id,
            'solicitante_nivel': nivel,
            'dias_pedidos': min(365, dias),
            'motivo': (post.get('motivo') or '').strip()[:2000] or False,
            'estado': estado,
            'autorizador_nivel': autorizador,
        })
        _logger.info('[AUDIT] solicitar_plazo user=%s proceso=%s solicitud=%s '
                     'nivel=%s estado=%s', request.env.user.id, proc.id, sol.id,
                     nivel, estado)
        payload = {'ok': True, 'id': sol.id, 'estado': sol.estado}
        if is_ajax():
            return json_r(payload)
        return request.redirect('/my/proceso/%d' % proc.id)

    @http.route('/my/solicitud/<int:solicitud_id>/autorizar', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def autorizar_solicitud(self, solicitud_id, **post):
        sol = request.env['certum.rev.solicitud'].sudo().browse(int(solicitud_id))
        if not sol.exists():
            return json_err('Solicitud no encontrada.', 404)
        rol = _rol_en_proceso(sol.proceso_id)
        if rol != ROL_CLIENTE:
            return json_err('No tienes acceso a esta solicitud.', 403)
        nivel = _nivel_usuario()
        if not nivel or nivel > sol.autorizador_nivel:
            return json_err('Debes ser de un nivel superior para autorizar.', 403)
        decision = (post.get('decision') or 'autorizar').strip()
        if decision == 'rechazar':
            sol.rechazar(request.env.user.partner_id)
        else:
            sol.autorizar(request.env.user.partner_id, nivel)
        if is_ajax():
            return json_r({'ok': True, 'estado': sol.estado})
        return request.redirect('/my/proceso/%d' % sol.proceso_id.id)
