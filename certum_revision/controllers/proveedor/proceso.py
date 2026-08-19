# -*- coding: utf-8 -*-
"""Portal proveedor: listado y detalle de sus procesos + descargas."""
import io
import json
import logging
import os
import re
import unicodedata
import zipfile

from markupsafe import Markup

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

DEFAULT_MAX_ZIP_MB = 200
_ZIP_SEPARADORES = re.compile(r'[/\\]+')
_ZIP_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


# ── Utilidades del paquete ZIP ───────────────────────────────────────
def _zip_safe(name, fallback='documento'):
    """Nombre seguro para una entrada de ZIP: sin separadores ni control.

    Los separadores de ruta se sustituyen por un guion en vez de borrarse, para
    que 'REV/2026/0001' quede legible como 'REV-2026-0001' y no como
    'REV20260001'.
    """
    name = _ZIP_SEPARADORES.sub('-', (name or '').strip())
    name = _ZIP_BAD_CHARS.sub('', name)
    name = name.replace('..', '.').strip('. ')
    return name[:120] or fallback


def _ascii(text):
    """Versión ASCII (sin tildes) para cabeceras HTTP."""
    norm = unicodedata.normalize('NFKD', text or '')
    out = norm.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^A-Za-z0-9._-]+', '_', out).strip('_') or 'documentos'


def _content_disposition(filename):
    """Cabecera con nombre ASCII y variante UTF-8 (RFC 5987)."""
    from urllib.parse import quote
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
        _ascii(filename), quote(filename))


def _zip_filename(proceso):
    return '%s - %s.zip' % (_zip_safe(proceso.name, 'Expediente'),
                            _zip_safe(proceso.proveedor_id.name, 'Proveedor'))


def _max_zip_bytes():
    icp = request.env['ir.config_parameter'].sudo()
    try:
        mb = int(icp.get_param('certum_revision.max_zip_mb', DEFAULT_MAX_ZIP_MB))
    except (TypeError, ValueError):
        mb = DEFAULT_MAX_ZIP_MB
    return max(1, mb) * 1024 * 1024


def _armar_zip(proceso, items):
    """Devuelve (bytes_zip, n_documentos) o (None, 0) si excede el tope.

    Estructura: una carpeta por carpeta del expediente y UN archivo por ítem
    (el vigente). Nunca dos versiones del mismo documento.
    """
    tope = _max_zip_bytes()
    acumulado = 0
    usados = set()
    buf = io.BytesIO()
    n = 0

    ordenados = items.sorted(key=lambda i: (
        i.carpeta_id.sequence if i.carpeta_id else 999, i.sequence, i.id))

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for it in ordenados:
            att = it.attachment_final_id.sudo()
            data = att.raw or b''
            if not data:
                continue                      # vigente sin contenido: se omite
            acumulado += len(data)
            if acumulado > tope:
                return None, 0

            n += 1
            # Extensión real del archivo publicado; nombre legible del ítem.
            # La numeración va sobre los archivos INCLUIDOS, para que no queden
            # huecos si alguno se omite.
            ext = os.path.splitext(att.name or '')[1][:12]
            base = '%02d - %s' % (n, _zip_safe(it.name, 'documento'))
            carpeta = _zip_safe(it.carpeta_id.name, '') if it.carpeta_id else ''
            arc = ('%s/%s%s' % (carpeta, base, ext)) if carpeta else (base + ext)

            # Red de seguridad ante nombres idénticos (el prefijo ya los separa).
            if arc in usados:
                arc = '%s/%s (%d)%s' % (carpeta, base, it.id, ext) if carpeta \
                    else '%s (%d)%s' % (base, it.id, ext)
            usados.add(arc)

            z.writestr(arc, data)

        z.writestr('LEEME.txt', _leeme(proceso, n).encode('utf-8'))

    return buf.getvalue(), n


def _leeme(proceso, n):
    """Nota incluida en el ZIP: qué contiene y por qué conviene conservarlo."""
    limite = proceso.fecha_limite.strftime('%d/%m/%Y') if proceso.fecha_limite else '-'
    return (
        'EXPEDIENTE %s\r\n'
        'Proveedor: %s\r\n'
        'Cliente:   %s\r\n'
        'Plazo limite: %s\r\n'
        'Documentos incluidos: %d\r\n'
        '\r\n'
        'QUE CONTIENE ESTE PAQUETE\r\n'
        'Unicamente los documentos APROBADOS del expediente, y de cada uno solo\r\n'
        'la version vigente. No se incluyen versiones anteriores ni documentos\r\n'
        'pendientes, publicados u observados.\r\n'
        '\r\n'
        'CONSERVE ESTA COPIA\r\n'
        'En el sistema solo permanece de forma indefinida el archivo final de\r\n'
        'cada documento. Las versiones superadas y los adjuntos de marcas se\r\n'
        'depuran automaticamente pasados unos dias: se borra el contenido del\r\n'
        'archivo, aunque queda registrado que existio, quien lo subio y cuando.\r\n'
        'Guarde este paquete en su equipo si necesita el respaldo completo.\r\n'
        % (proceso.name, proceso.proveedor_id.name or '-',
           proceso.cliente_id.name or '-', limite, n))


def _part_data_json(proceso):
    """Personal del cliente + participantes designados, para el editor JS.

    JSON válido embebido en <script>: se escapa '<' para que un nombre con
    '</script>' no pueda romper la etiqueta (mismo patrón que el editor de
    plantillas).
    """
    contactos = request.env['res.partner'].sudo().search([
        ('parent_id', '=', proceso.cliente_id.id),
        ('is_company', '=', False)], order='certum_nivel, name')
    data = {
        'contactos': [{'id': c.id, 'name': c.display_name,
                       'nivel': c.certum_nivel or 0} for c in contactos],
        'participantes': [r.partner_id.id
                          for r in proceso.revisor_ids.sorted('sequence')],
    }
    return Markup(json.dumps(data).replace('<', '\\u003c'))


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
    def proceso_detail(self, proceso_id, aviso=None, **kw):
        proceso = request.env['certum.rev.proceso'].sudo().browse(proceso_id)
        rol = _rol_en_proceso(proceso) if proceso.exists() else None
        if rol is None:
            return request.redirect('/my/certum')
        carpetas = proceso.folder_ids.sorted('sequence')
        items_ordenados = proceso.item_ids.sorted(
            key=lambda i: (i.carpeta_id.sequence if i.carpeta_id else 999,
                           i.sequence, i.id))
        avisos = {
            'sin_aprobados': 'Todavía no hay documentos aprobados que descargar.',
            'zip_grande': 'El paquete supera el tamaño máximo permitido. '
                          'Descargue los documentos por separado.',
            'purgado': 'Ese archivo ya fue depurado por antigüedad. Se conserva '
                       'el registro de que existió, pero no su contenido.',
        }
        return request.render('certum_revision.portal_proceso_detail', {
            'rol': rol,
            'proceso': proceso,
            'carpetas': carpetas,
            'items_ordenados': items_ordenados,
            'nivel': _nivel_usuario(),
            'solicitudes': proceso.solicitud_ids.sorted('create_date', reverse=True),
            'n_aprobados': len(items_ordenados.filtered(
                lambda i: i.state == 'aprobado' and i.attachment_final_id)),
            'participantes': proceso.revisor_ids.sorted('sequence'),
            'part_data_json': _part_data_json(proceso),
            'dias_purga': request.env['certum.rev.item'].sudo()._param_int_purga(),
            'aviso': avisos.get(aviso or ''),
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
        # Versión ya depurada: el registro existe pero el contenido se borró.
        if att.certum_purgado:
            return request.redirect('/my/proceso/%d?aviso=purgado' % item.proceso_id.id)
        _logger.info('[AUDIT] item_download user=%s item=%s att=%s',
                     request.env.user.id, item.id, att.id)
        return request.env['ir.binary']._get_stream_from(
            att.sudo(), 'raw', filename=att.name).get_response(as_attachment=True)

    # ── Paquete ZIP del expediente ────────────────────────────────────
    @http.route('/my/proceso/<int:proceso_id>/descargar', type='http',
                auth='user', website=True)
    def proceso_descargar_zip(self, proceso_id, **kw):
        """Descarga en un ZIP los documentos APROBADOS del expediente.

        Reglas (definidas con el negocio):
          - solo ítems en estado `aprobado`;
          - de cada uno, SOLO el archivo vigente → nunca dos versiones del
            mismo documento en el paquete;
          - lo pueden descargar ambas partes (proveedor y cliente) y el
            personal interno;
          - se permite también en expedientes fuera de plazo o completados.
        """
        proceso = request.env['certum.rev.proceso'].sudo().browse(proceso_id)
        rol = _rol_en_proceso(proceso) if proceso.exists() else None
        if rol is None:
            return request.redirect('/my/certum')
        if proceso.state == 'borrador':
            return request.redirect('/my/proceso/%d' % proceso.id)

        items = proceso.item_ids.filtered(
            lambda i: i.state == 'aprobado' and i.attachment_final_id)
        if not items:
            return request.redirect('/my/proceso/%d?aviso=sin_aprobados' % proceso.id)

        payload, n = _armar_zip(proceso, items)
        if payload is None:
            return request.redirect('/my/proceso/%d?aviso=zip_grande' % proceso.id)

        _logger.info('[AUDIT] proceso_zip user=%s proceso=%s rol=%s items=%s bytes=%s',
                     request.env.user.id, proceso.id, rol, n, len(payload))
        return request.make_response(payload, headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', _content_disposition(_zip_filename(proceso))),
            ('Content-Length', str(len(payload))),
        ])
