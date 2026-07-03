# -*- coding: utf-8 -*-
"""Portal cliente: revisiones pendientes + aprobar/observar (POST + AJAX)."""
import logging

from odoo import http
from odoo.http import request

from ..helpers import (
    ROL_CLIENTE,
    _empresa,
    _get_item_error,
    get_item_or_none,
    is_ajax,
    item_panel_data,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)


class CertumRevCliente(http.Controller):

    @http.route('/my/revisiones', type='http', auth='user', website=True)
    def revisiones_list(self, **kw):
        emp = _empresa()
        procesos = request.env['certum.rev.proceso'].sudo().search([
            ('cliente_id', '=', emp.id),
            ('state', '!=', 'borrador'),
        ])
        return request.render('certum_revision.portal_revisiones', {
            'rol': ROL_CLIENTE,
            'procesos': procesos,
        })

    @http.route('/my/item/<int:item_id>/aprobar', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def item_aprobar(self, item_id, **post):
        return self._revisar(item_id, 'aprobar', post)

    @http.route('/my/item/<int:item_id>/observar', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def item_observar(self, item_id, **post):
        comentario = (post.get('comentario') or '').strip()
        if not comentario:
            return json_err('Indica qué debe corregir el proveedor.')
        return self._revisar(item_id, 'observar', post)

    def _revisar(self, item_id, accion, post):
        item, rol = get_item_or_none(item_id)
        if item is None:
            return json_err('Ítem no encontrado.', 404)
        error = _get_item_error(item, accion, rol)
        if error:
            return json_err(error, 403)

        if accion == 'aprobar':
            item.marcar_aprobado()
        else:
            item.marcar_observado()

        comentario = (post.get('comentario') or '').strip()
        if comentario:
            request.env['certum.rev.comment'].sudo().create({
                'item_id': item.id,
                'author_id': request.env.user.partner_id.id,
                'rol': rol,
                'body': comentario[:2000],
            })
        _logger.info('[AUDIT] portal_%s user=%s item=%s',
                     accion, request.env.user.id, item.id)

        if is_ajax():
            data = item_panel_data(item, rol)
            data['proceso_state'] = item.proceso_id.state
            data['avance'] = item.proceso_id.avance
            return json_r(data)
        return request.redirect('/my/proceso/%d' % item.proceso_id.id)
