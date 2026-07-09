# -*- coding: utf-8 -*-
"""Portal cliente: revisiones pendientes + aprobar/observar (POST + AJAX).

Aprobación por capas (feature A): en modo secuencial solo el nivel que toca
puede revisar; al observar, el cliente puede adjuntar su documento con marcas.
"""
import base64
import logging
import mimetypes

from odoo import http
from odoo.http import request

from ..helpers import (
    ROL_CLIENTE,
    _empresa,
    _get_item_error,
    _nivel_usuario,
    _safe_upload_filename,
    _validar_tamano_archivo,
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

        # Aprobación por capas: valida que el nivel del usuario sea el que toca.
        nivel = _nivel_usuario()
        if not item.puede_aprobar_nivel(nivel):
            if item.proceso_id.revision_modo == 'secuencial':
                return json_err(
                    'Ahora corresponde revisar al nivel %s. Tu nivel es %s.'
                    % (item.revision_nivel or '—', nivel or 'sin asignar'), 403)
            return json_err('No puedes revisar este ítem.', 403)

        # El comentario se crea ANTES de la transición para que la
        # notificación de "observado" incluya el texto de la observación.
        comentario = (post.get('comentario') or '').strip()
        if comentario:
            request.env['certum.rev.comment'].sudo().create({
                'item_id': item.id,
                'author_id': request.env.user.partner_id.id,
                'rol': rol,
                'body': comentario[:2000],
            })

        partner = request.env.user.partner_id
        if accion == 'aprobar':
            item.marcar_aprobado(partner=partner, nivel=nivel, lado='cliente')
        else:
            # El cliente puede adjuntar su documento con marcas al observar.
            attachment = self._adjuntar_cliente(item)
            item.marcar_observado(partner=partner, nivel=nivel,
                                  comentario=comentario, attachment=attachment,
                                  lado='cliente')
        _logger.info('[AUDIT] portal_%s user=%s item=%s nivel=%s',
                     accion, request.env.user.id, item.id, nivel)

        if is_ajax():
            data = item_panel_data(item, rol)
            data['proceso_state'] = item.proceso_id.state
            data['avance'] = item.proceso_id.avance
            return json_r(data)
        return request.redirect('/my/proceso/%d' % item.proceso_id.id)

    def _adjuntar_cliente(self, item):
        """Guarda (si viene) el archivo que el cliente sube al observar."""
        upload = request.httprequest.files.get('archivo')
        if upload is None or not upload.filename:
            return None
        data = upload.read()
        if not data:
            return None
        if _validar_tamano_archivo(data):
            return None
        filename = _safe_upload_filename(upload.filename)
        mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        return request.env['ir.attachment'].sudo().create({
            'name': 'CLIENTE - ' + filename,
            'datas': base64.b64encode(data),
            'res_model': 'certum.rev.item',
            'res_id': item.id,
            'mimetype': mimetype,
        })
