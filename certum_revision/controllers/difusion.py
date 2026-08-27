# -*- coding: utf-8 -*-
"""Difusión de documentos aprobados y repositorio del proyecto.

Dos públicos muy distintos, y de ahí las dos entradas:

  - El **proveedor** (y Certum interno) difunde desde el proyecto: elige
    documentos aprobados y personas del cliente.
  - El **destinatario** entra a `/my/repositorio`, que es su propia vista: solo
    lo que se le ha difundido, aunque no haya participado en la revisión y no
    tenga acceso al proyecto.

El permiso sale siempre de `certum.rev.difusion.puede_ver()`. Una sola regla,
consultada por la vista y por la descarga, para que no puedan divergir.
"""
import logging

from odoo import http
from odoo.http import request

from .helpers import (
    ROL_INTERNO,
    ROL_PROVEEDOR,
    _content_disposition,
    _get_rol,
    _rol_en_proceso,
    fmt_lima,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)


class CertumRevDifusion(http.Controller):

    # ── Difundir (proveedor / interno) ─────────────────────────────────
    def _proceso_difundible(self, proceso_id):
        """Devuelve (proceso, rol) si quien pide puede difundir, o (None, None)."""
        proceso = request.env['certum.rev.proceso'].sudo().browse(int(proceso_id))
        if not proceso.exists():
            return None, None
        rol = _rol_en_proceso(proceso)
        if rol not in (ROL_PROVEEDOR, ROL_INTERNO):
            return None, None
        return proceso, rol

    @http.route('/my/proceso/<int:proceso_id>/difusion/datos', type='http',
                auth='user', website=True)
    def difusion_datos(self, proceso_id, **kw):
        """Qué se puede difundir y a quién. Alimenta el modal."""
        proceso, rol = self._proceso_difundible(proceso_id)
        if proceso is None:
            return json_err('No tienes acceso a este proyecto.', 403)

        aprobados = proceso.item_ids.filtered(
            lambda i: i.state == 'aprobado' and i.attachment_final_id)
        Difusion = request.env['certum.rev.difusion'].sudo()

        contactos = request.env['res.partner'].sudo().search([
            ('parent_id', '=', proceso.cliente_id.id),
            ('is_company', '=', False),
        ], order='name')
        Users = request.env['res.users'].sudo().with_context(active_test=False)
        personas = []
        for c in contactos:
            personas.append({
                'id': c.id,
                'name': c.display_name,
                'email': c.email or '',
                # Sin correo no se puede difundir: el modal lo marca en vez de
                # dejar que el envío falle al final con la lista ya elegida.
                'listo': bool(c.email),
                # Quien no tiene usuario lo recibirá al difundirle; avisarlo
                # antes evita la pregunta «¿por qué le llegaron dos correos?».
                'tiene_usuario': bool(Users.search_count(
                    [('partner_id', '=', c.id)])),
            })

        return json_r({
            'ok': True,
            'cliente': proceso.cliente_id.display_name,
            'documentos': [{
                'id': i.id,
                'name': i.name,
                'carpeta': i.carpeta_id.ruta or i.carpeta_id.name or '',
                'archivo': i.attachment_final_id.name or '',
                'difundido': len(Difusion.search(
                    [('item_ids', 'in', i.id)]).mapped('partner_ids')),
            } for i in aprobados.sorted('sequence')],
            'personas': personas,
            'historial': [{
                'fecha': fmt_lima(d.fecha),
                'quien': d.enviado_por_id.display_name or '—',
                'documentos': len(d.item_ids),
                'personas': ', '.join(d.partner_ids.mapped('display_name')),
            } for d in Difusion.search([('proceso_id', '=', proceso.id)],
                                       order='fecha desc', limit=15)],
        })

    @http.route('/my/proceso/<int:proceso_id>/difusion/enviar', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def difusion_enviar(self, proceso_id, **post):
        proceso, rol = self._proceso_difundible(proceso_id)
        if proceso is None:
            return json_err('Solo el proveedor puede difundir documentación.',
                            403)

        def ids(campo):
            crudo = post.get(campo) or ''
            return [int(x) for x in str(crudo).split(',') if x.strip().isdigit()]

        items = request.env['certum.rev.item'].sudo().browse(ids('item_ids'))
        partners = request.env['res.partner'].sudo().browse(ids('partner_ids'))
        items = items.exists()
        partners = partners.exists()

        try:
            difusion = request.env['certum.rev.difusion'].difundir(
                proceso, items, partners,
                mensaje=post.get('mensaje'),
                autor=request.env.user.partner_id)
        except Exception as exc:  # noqa: BLE001 - el motivo se muestra al usuario
            return json_err(getattr(exc, 'name', None) or str(exc) or
                            'No se pudo difundir.')

        return json_r({
            'ok': True,
            'personas': len(difusion.partner_ids),
            'documentos': len(difusion.item_ids),
            'usuarios_creados': difusion.usuarios_creados,
        })

    # ── Repositorio (el destinatario) ──────────────────────────────────
    @http.route('/my/repositorio', type='http', auth='user', website=True)
    def repositorio(self, **kw):
        """Lo que se me ha difundido, agrupado por proyecto.

        Es la puerta de entrada de quien no participa en la revisión: no tiene
        rol en el proyecto y no puede abrirlo, pero sí ver lo que le entregaron.
        """
        partner = request.env.user.partner_id
        Difusion = request.env['certum.rev.difusion']
        items = Difusion.items_para(partner)

        grupos = []
        for proc in items.mapped('proceso_id').sorted('fecha_inicio', reverse=True):
            propios = items.filtered(lambda i: i.proceso_id.id == proc.id)
            grupos.append({
                'proceso': proc,
                'items': propios.sorted('sequence'),
            })
        return request.render('certum_revision.portal_repositorio', {
            'grupos': grupos,
            'total': len(items),
            # Lo usa la barra de navegación del layout. Un destinatario de
            # difusión puede no tener rol: la nav se pinta sin sus enlaces.
            'rol': _get_rol(),
        })

    @http.route('/my/repositorio/<int:item_id>/descargar', type='http',
                auth='user', website=True)
    def repositorio_descargar(self, item_id, **kw):
        """Descarga de un documento difundido.

        La comprobación es la misma que pinta la lista: si aquí se relajara,
        bastaría con adivinar un id para llevarse documentación ajena.
        """
        item = request.env['certum.rev.item'].sudo().browse(item_id)
        if not item.exists():
            return request.redirect('/my/repositorio')
        partner = request.env.user.partner_id
        permitido = request.env['certum.rev.difusion'].puede_ver(partner, item)
        # Quien participa en el proyecto ya tenía acceso por su rol; negárselo
        # aquí sería confuso sin ganar nada.
        if not permitido and _rol_en_proceso(item.proceso_id) is None:
            _logger.info('[AUDIT] repositorio_denegado user=%s item=%s',
                         request.env.user.id, item.id)
            return request.redirect('/my/repositorio')
        att = item.attachment_final_id.sudo()
        if not att or not att.raw:
            return request.redirect('/my/repositorio')

        _logger.info('[AUDIT] repositorio_descarga user=%s item=%s',
                     request.env.user.id, item.id)
        return request.make_response(att.raw, headers=[
            ('Content-Type', att.mimetype or 'application/octet-stream'),
            ('Content-Disposition', _content_disposition(att.name or 'documento')),
            ('Content-Length', str(len(att.raw))),
        ])
