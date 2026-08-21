# -*- coding: utf-8 -*-
"""Gestión de la revisión: política del proceso, solicitudes de plazo y
cadena de revisores por ítem.

- La política del PROCESO (modo + capas + participantes) la fija el nivel 1
  del CLIENTE: es su gobierno interno.
- La cadena de un ÍTEM concreto la fija el PROVEEDOR, que es quien sabe qué
  especialidad necesita cada requisito. Los revisores designados siguen siendo
  personas del cliente: son quienes aprueban.
- Las solicitudes de ampliación de plazo se enrutan por jerarquía del cliente:
  nivel 1 → directo al proveedor; nivel inferior → autoriza el superior y sube.
"""
import logging

from odoo import http
from odoo.http import request

from odoo.addons.certum_revision.models.ampliacion import MAX_DIAS_AMPLIACION

from ..helpers import (
    ROL_CLIENTE,
    fmt_lima,
    ROL_PROVEEDOR,
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
        if modo not in ('cualquiera', 'secuencial', 'personas'):
            return json_err('Modo no válido.')
        try:
            capas = int(post.get('capas') or 1)
        except (TypeError, ValueError):
            capas = 1
        capas = max(1, min(20, capas))

        # En modo 'personas' la cadena no puede quedar vacía: sin participantes
        # el proceso se comportaría como 'cualquiera' sin decirlo.
        if modo == 'personas' and not proc.revisor_ids:
            return json_err('Designa al menos un participante antes de elegir '
                            'este modo.')

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

    # ── Participantes del proceso (modo 'personas') ───────────────────
    @http.route('/my/proceso/<int:proceso_id>/revisores', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def set_participantes(self, proceso_id, **post):
        """Designa quiénes participan en la revisión de ESTE proceso y en qué
        orden. Es la cadena por defecto de todos sus ítems.

        Se puede editar en cualquier momento: los ítems ya publicados
        conservan la cadena que se congeló al publicarlos, así que un cambio
        aquí solo afecta a lo que se publique a partir de ahora.
        """
        proc, rol = _proceso_or_none(proceso_id)
        if proc is None or rol != ROL_CLIENTE:
            return json_err('No tienes acceso a este proceso.', 403)
        if _nivel_usuario() != 1:
            return json_err('Solo el nivel 1 del cliente designa a los '
                            'participantes.', 403)

        raw = post.get('partner_ids') or ''
        ids = [int(x) for x in str(raw).split(',') if x.strip().isdigit()]
        # Solo contactos-persona de la empresa cliente; respeta el orden recibido.
        validos = request.env['res.partner'].sudo().search([
            ('id', 'in', ids),
            ('parent_id', '=', proc.cliente_id.id),
            ('is_company', '=', False),
        ])
        vset = set(validos.ids)
        ordenados = [i for i in ids if i in vset]

        proc.revisor_ids.sudo().unlink()
        Revisor = request.env['certum.rev.revisor'].sudo()
        for seq, pid in enumerate(ordenados, start=1):
            Revisor.create({'proceso_id': proc.id, 'partner_id': pid,
                            'sequence': seq * 10})
        # Quedarse en modo 'personas' sin participantes dejaría el proceso en
        # un estado ambiguo; se vuelve a 'cualquiera' de forma explícita.
        if not ordenados and proc.revision_modo == 'personas':
            proc.write({'revision_modo': 'cualquiera', 'revision_capas': 1})
        _logger.info('[AUDIT] set_participantes user=%s proceso=%s n=%s',
                     request.env.user.id, proc.id, len(ordenados))
        return json_r({'ok': True, 'count': len(ordenados),
                       'modo': proc.revision_modo})

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

    # ── Ampliación de la ventana de revisión de un ÍTEM ───────────────
    # El revisor del cliente pide más días para UN documento y los concede el
    # PROVEEDOR, que es quien fijó esos días al publicar. Si los concediera el
    # propio cliente se estaría dando tiempo a sí mismo sin contrapeso.
    @http.route('/my/item/<int:item_id>/ampliacion/pedir', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def ampliacion_pedir(self, item_id, **post):
        item = request.env['certum.rev.item'].sudo().browse(int(item_id))
        if not item.exists():
            return json_err('Ítem no encontrado.', 404)
        if _rol_en_proceso(item.proceso_id) != ROL_CLIENTE:
            return json_err('Solo el cliente pide más días para revisar.', 403)
        if item.state != 'publicado':
            return json_err('Este documento no está en revisión ahora mismo.', 400)
        try:
            dias = int(post.get('dias') or 0)
        except (TypeError, ValueError):
            dias = 0
        if dias <= 0 or dias > MAX_DIAS_AMPLIACION:
            return json_err('Indica entre 1 y %s días adicionales.'
                            % MAX_DIAS_AMPLIACION)

        amp = request.env['certum.rev.ampliacion'].sudo().create({
            'item_id': item.id,
            'solicitante_id': request.env.user.partner_id.id,
            'dias_pedidos': dias,
            'motivo': (post.get('motivo') or '').strip()[:2000] or False,
            'estado': 'pendiente',
        })
        _logger.info('[AUDIT] ampliacion_pedir user=%s item=%s dias=%s',
                     request.env.user.id, item.id, dias)
        return json_r({'ok': True, 'id': amp.id})

    @http.route('/my/item/<int:item_id>/ampliacion/conceder', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def ampliacion_conceder(self, item_id, **post):
        """El PROVEEDOR concede días. Sirve para resolver una solicitud
        (`ampliacion_id`) o para conceder por iniciativa propia, sin que nadie
        haya pedido nada."""
        item = request.env['certum.rev.item'].sudo().browse(int(item_id))
        if not item.exists():
            return json_err('Ítem no encontrado.', 404)
        if _rol_en_proceso(item.proceso_id) != ROL_PROVEEDOR:
            return json_err('Solo el proveedor concede días de revisión: es '
                            'quien fijó el plazo al publicar.', 403)
        try:
            dias = int(post.get('dias') or 0)
        except (TypeError, ValueError):
            dias = 0
        if dias <= 0 or dias > MAX_DIAS_AMPLIACION:
            return json_err('Indica entre 1 y %s días adicionales.'
                            % MAX_DIAS_AMPLIACION)

        Amp = request.env['certum.rev.ampliacion'].sudo()
        amp = Amp.browse(int(post.get('ampliacion_id') or 0))
        if not amp.exists() or amp.item_id.id != item.id:
            # Concesión directa: se deja registrada igual, sin solicitante.
            amp = Amp.create({'item_id': item.id, 'estado': 'pendiente',
                              'motivo': (post.get('motivo') or '').strip()[:2000]
                                        or False})
        try:
            limite = amp.conceder(dias, request.env.user.partner_id)
        except Exception as exc:  # noqa: BLE001 - el motivo se muestra al usuario
            return json_err(getattr(exc, 'name', None) or str(exc) or
                            'No se pudo ampliar la ventana.')
        return json_r({'ok': True, 'limite': fmt_lima(limite)})

    @http.route('/my/ampliacion/<int:ampliacion_id>/rechazar', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def ampliacion_rechazar(self, ampliacion_id, **post):
        amp = request.env['certum.rev.ampliacion'].sudo().browse(int(ampliacion_id))
        if not amp.exists():
            return json_err('Solicitud no encontrada.', 404)
        if _rol_en_proceso(amp.item_id.proceso_id) != ROL_PROVEEDOR:
            return json_err('Solo el proveedor resuelve estas solicitudes.', 403)
        amp.rechazar(request.env.user.partner_id)
        return json_r({'ok': True})

    # ── Cadena de revisores a medida de un ÍTEM (la fija el PROVEEDOR) ─
    @http.route('/my/item/<int:item_id>/revisores', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def set_revisores(self, item_id, **post):
        item = request.env['certum.rev.item'].sudo().browse(int(item_id))
        if not item.exists():
            return json_err('Ítem no encontrado.', 404)
        # Cambio 2026-08-18: la cadena POR ÍTEM la decide el PROVEEDOR.
        # (La política general del proceso sigue siendo del nivel 1 del cliente.)
        if _rol_en_proceso(item.proceso_id) != ROL_PROVEEDOR:
            return json_err('Solo el proveedor designa los revisores de un '
                            'requisito.', 403)
        if item.state not in ('pendiente', 'observado'):
            return json_err('No se puede cambiar la cadena mientras el ítem '
                            'está en revisión activa.', 400)

        raw = post.get('partner_ids') or ''
        ids = [int(x) for x in str(raw).split(',') if x.strip().isdigit()]
        # Solo contactos-persona de la empresa cliente; respeta el orden recibido.
        validos = request.env['res.partner'].sudo().search([
            ('id', 'in', ids),
            ('parent_id', '=', item.cliente_id.id),
            ('is_company', '=', False),
        ])
        vset = set(validos.ids)
        ordenados = [i for i in ids if i in vset]

        item.revisor_ids.sudo().unlink()
        Revisor = request.env['certum.rev.revisor'].sudo()
        for seq, pid in enumerate(ordenados, start=1):
            Revisor.create({'item_id': item.id, 'partner_id': pid,
                            'sequence': seq * 10})
        # Marca de excepción: distingue esta cadena de la heredada del proceso.
        item.revisores_propios = bool(ordenados)
        _logger.info('[AUDIT] set_revisores user=%s item=%s n=%s',
                     request.env.user.id, item.id, len(ordenados))
        return json_r({'ok': True, 'count': len(ordenados)})

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
