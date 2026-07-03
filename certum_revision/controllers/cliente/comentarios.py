# -*- coding: utf-8 -*-
"""Hilo de comentarios + panel AJAX del ítem (compartido proveedor/cliente)."""
import logging

from odoo import http
from odoo.http import request

from ..helpers import (
    _get_item_error,
    get_item_or_none,
    is_ajax,
    item_panel_data,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)


class CertumRevComentarios(http.Controller):

    @http.route('/my/item/<int:item_id>/panel', type='http', auth='user',
                website=True)
    def item_panel(self, item_id, **kw):
        """JSON que alimenta el drawer del ítem (datos + hilo + acciones)."""
        item, rol = get_item_or_none(item_id)
        if item is None:
            return json_err('Ítem no encontrado.', 404)
        return json_r(item_panel_data(item, rol))

    @http.route('/my/item/<int:item_id>/comentar', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def item_comentar(self, item_id, **post):
        item, rol = get_item_or_none(item_id)
        if item is None:
            return json_err('Ítem no encontrado.', 404)
        error = _get_item_error(item, 'comentar', rol)
        if error:
            return json_err(error, 403)
        body = (post.get('body') or '').strip()
        if not body:
            return json_err('Escribe un comentario.')
        request.env['certum.rev.comment'].sudo().create({
            'item_id': item.id,
            'author_id': request.env.user.partner_id.id,
            'rol': rol,
            'body': body[:2000],
        })
        _logger.info('[AUDIT] portal_comentar user=%s item=%s',
                     request.env.user.id, item.id)
        if is_ajax():
            return json_r(item_panel_data(item, rol))
        return request.redirect('/my/proceso/%d' % item.proceso_id.id)
