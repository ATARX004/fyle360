# -*- coding: utf-8 -*-
"""Portal proveedor: publicación/corrección de ítems (POST + AJAX)."""
import base64
import logging
import mimetypes

from odoo import http
from odoo.http import request

from ..helpers import (
    ROL_PROVEEDOR,
    _get_item_error,
    _safe_upload_filename,
    _validar_tamano_archivo,
    get_item_or_none,
    is_ajax,
    item_panel_data,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)


class CertumRevPublicar(http.Controller):

    @http.route('/my/item/<int:item_id>/publicar', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def item_publicar(self, item_id, **post):
        item, rol = get_item_or_none(item_id)
        if item is None:
            return json_err('Ítem no encontrado.', 404)
        error = _get_item_error(item, 'publicar', rol)
        if error:
            return json_err(error, 403)

        upload = request.httprequest.files.get('archivo')
        if upload is None or not upload.filename:
            return json_err('Adjunta un documento para publicar.')
        data = upload.read()
        if not data:
            return json_err('El archivo está vacío.')
        error = _validar_tamano_archivo(data)
        if error:
            return json_err(error, 413)

        filename = _safe_upload_filename(upload.filename)
        # Deriva el mimetype del nombre saneado (no del header del cliente).
        mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        attachment = request.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': base64.b64encode(data),
            'res_model': 'certum.rev.item',
            'res_id': item.id,
            'mimetype': mimetype,
        })
        # En la PRIMERA publicación el proveedor fija los días de revisión del
        # cliente; en las correcciones se reutiliza el valor ya guardado.
        dias_revision = None
        if not item.dias_revision:
            try:
                dias_revision = int(post.get('dias_revision') or 0)
            except (TypeError, ValueError):
                dias_revision = 0
            if dias_revision <= 0:
                return json_err('Indica cuántos días tendrá el cliente para revisar.')
        item.marcar_publicado(attachment, dias_revision=dias_revision)

        nota = (post.get('nota') or '').strip()
        if nota:
            request.env['certum.rev.comment'].sudo().create({
                'item_id': item.id,
                'author_id': request.env.user.partner_id.id,
                'rol': rol,
                'body': nota[:2000],
            })
        _logger.info('[AUDIT] portal_publicar user=%s item=%s file=%s',
                     request.env.user.id, item.id, filename)

        if is_ajax():
            return json_r(item_panel_data(item, rol))
        return request.redirect('/my/proceso/%d' % item.proceso_id.id)

    @http.route('/my/item/<int:item_id>/deshacer-publicacion', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def item_deshacer_publicacion(self, item_id, **post):
        """Retira la última versión publicada y restaura la anterior.

        Solo el proveedor: es quien publicó y quien puede haberse equivocado
        de archivo. El documento retirado se queda en el historial.
        """
        item, rol = get_item_or_none(item_id)
        if item is None:
            return json_err('Ítem no encontrado.', 404)
        if rol != ROL_PROVEEDOR:
            return json_err('Solo el proveedor puede deshacer una '
                            'publicación.', 403)
        try:
            item.revertir_publicacion(request.env.user.partner_id)
        except Exception as exc:  # noqa: BLE001 - el motivo se muestra al usuario
            return json_err(getattr(exc, 'name', None) or str(exc) or
                            'No se pudo deshacer la publicación.')
        _logger.info('[AUDIT] portal_deshacer_publicacion user=%s item=%s',
                     request.env.user.id, item.id)
        return json_r(item_panel_data(item, rol))

    @http.route('/my/item/<int:item_id>/borrar-documento', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def item_borrar_documento(self, item_id, **post):
        """Borra un archivo publicado que todavía nadie ha revisado.

        Sirve para dejar limpio un documento donde se subió lo que no era,
        antes de volver a publicar el correcto.
        """
        item, rol = get_item_or_none(item_id)
        if item is None:
            return json_err('Ítem no encontrado.', 404)
        if rol != ROL_PROVEEDOR:
            return json_err('Solo el proveedor puede borrar un archivo.', 403)
        att = request.env['ir.attachment'].sudo().browse(
            int(post.get('attachment_id') or 0))
        if not att.exists():
            return json_err('Archivo no encontrado.', 404)
        try:
            item.borrar_documento(att, request.env.user.partner_id)
        except Exception as exc:  # noqa: BLE001 - el motivo se muestra al usuario
            return json_err(getattr(exc, 'name', None) or str(exc) or
                            'No se pudo borrar el archivo.')
        _logger.info('[AUDIT] portal_borrar_documento user=%s item=%s att=%s',
                     request.env.user.id, item.id, att.id)
        return json_r(item_panel_data(item, rol))
