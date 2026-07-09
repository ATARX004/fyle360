# -*- coding: utf-8 -*-
"""Portal proveedor: listado y detalle de sus procesos + descargas."""
import logging

from odoo import http
from odoo.http import request

from ..helpers import (
    ROL_PROVEEDOR,
    _empresa,
    _get_item_error,
    _nivel_usuario,
    _rol_en_proceso,
    get_item_or_none,
    is_ajax,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)


class CertumRevProveedor(http.Controller):

    @http.route('/my/solicitud/<int:solicitud_id>/decidir', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def decidir_solicitud(self, solicitud_id, **post):
        """El proveedor aprueba/rechaza una solicitud de ampliación de plazo."""
        sol = request.env['certum.rev.solicitud'].sudo().browse(int(solicitud_id))
        if not sol.exists():
            return json_err('Solicitud no encontrada.', 404)
        if _rol_en_proceso(sol.proceso_id) != ROL_PROVEEDOR:
            return json_err('Solo el proveedor puede decidir esta solicitud.', 403)
        if sol.estado != 'pendiente_proveedor':
            return json_err('La solicitud no está pendiente del proveedor.', 400)
        decision = (post.get('decision') or 'aprobar').strip()
        if decision == 'rechazar':
            sol.rechazar(request.env.user.partner_id)
        else:
            sol.aprobar_proveedor(request.env.user.partner_id)
        _logger.info('[AUDIT] proveedor_decide_solicitud user=%s solicitud=%s '
                     'decision=%s', request.env.user.id, sol.id, decision)
        if is_ajax():
            return json_r({'ok': True, 'estado': sol.estado})
        return request.redirect('/my/proceso/%d' % sol.proceso_id.id)

    @http.route('/my/procesos', type='http', auth='user', website=True)
    def procesos_list(self, **kw):
        emp = _empresa()
        procesos = request.env['certum.rev.proceso'].sudo().search([
            ('proveedor_id', '=', emp.id),
            ('state', '!=', 'borrador'),
        ])
        return request.render('certum_revision.portal_procesos', {
            'rol': ROL_PROVEEDOR,
            'procesos': procesos,
        })

    @http.route('/my/proceso/<int:proceso_id>', type='http', auth='user',
                website=True)
    def proceso_detail(self, proceso_id, **kw):
        proceso = request.env['certum.rev.proceso'].sudo().browse(proceso_id)
        rol = _rol_en_proceso(proceso) if proceso.exists() else None
        if rol is None:
            return request.redirect('/my/certum')
        carpetas = proceso.folder_ids.sorted('sequence')
        items_ordenados = proceso.item_ids.sorted(
            key=lambda i: (i.carpeta_id.sequence if i.carpeta_id else 999,
                           i.sequence, i.id))
        return request.render('certum_revision.portal_proceso_detail', {
            'rol': rol,
            'proceso': proceso,
            'carpetas': carpetas,
            'items_ordenados': items_ordenados,
            'nivel': _nivel_usuario(),
            'solicitudes': proceso.solicitud_ids.sorted('create_date', reverse=True),
        })

    @http.route('/my/item/<int:item_id>/download/<int:att_id>', type='http',
                auth='user', website=True)
    def item_download(self, item_id, att_id, **kw):
        item, rol = get_item_or_none(item_id)
        if item is None:
            return request.redirect('/my/certum')
        error = _get_item_error(item, 'descargar', rol)
        if error:
            return request.redirect('/my/certum')
        att = (item.attachment_ids | item.attachment_cliente_ids).filtered(
            lambda a: a.id == int(att_id))
        if not att:
            return request.not_found()
        _logger.info('[AUDIT] item_download user=%s item=%s att=%s',
                     request.env.user.id, item.id, att.id)
        return request.env['ir.binary']._get_stream_from(
            att.sudo(), 'raw', filename=att.name).get_response(as_attachment=True)
