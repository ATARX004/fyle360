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
    item_avance,
    item_es_mio,
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


def _ruta_zip(carpeta):
    """Ruta anidada de una carpeta dentro del ZIP ('Padre/Hija/Nieta').

    Cada tramo se sanea por separado, asi un nombre con una barra no puede
    inventar un nivel de carpeta que no existe.
    """
    partes, cur, guard = [], carpeta, 0
    while cur and guard < 12:
        tramo = _zip_safe(cur.name, '')
        if tramo:
            partes.append(tramo)
        cur = cur.parent_id
        guard += 1
    return '/'.join(reversed(partes))


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

    # Orden del paquete = orden del arbol: la ruta completa ordena de forma
    # natural padres antes que hijas, y los sueltos al final (chr(0xffff)).
    ordenados = items.sorted(key=lambda i: (
        i.carpeta_id.ruta if i.carpeta_id else chr(0xffff), i.sequence, i.id))

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
            carpeta = _ruta_zip(it.carpeta_id) if it.carpeta_id else ''
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


def _destinos_json(proceso):
    """Carpetas del expediente como destinos posibles, para el JS del modo
    edición. Mismo escape que el resto: '<' no puede romper la etiqueta."""
    data = [{'id': c.id, 'ruta': c.ruta or c.name, 'nivel': c.nivel,
             'rama': c.parent_path or ''}
            for c in proceso.folder_ids.sorted(lambda c: (c.ruta or '', c.id))]
    return Markup(json.dumps(data).replace('<', '\\u003c'))


def _resumen_diff(d):
    """Frase corta con las diferencias frente a la plantilla."""
    if not d or not d.get('total'):
        return ''
    partes = []
    for clave, sing, plur in (('nuevas', 'carpeta nueva', 'carpetas nuevas'),
                              ('nuevos', 'documento nuevo', 'documentos nuevos'),
                              ('movidos', 'movido', 'movidos'),
                              ('renombrados', 'renombrado', 'renombrados'),
                              ('quitados', 'quitado', 'quitados')):
        n = len(d.get(clave) or [])
        if n:
            partes.append('%d %s' % (n, sing if n == 1 else plur))
    return ' · '.join(partes) + '.'


def _clave_natural(texto):
    """Clave de orden como la de un explorador de archivos.

    Cada tramo de dígitos se rellena con ceros a la izquierda y luego se
    compara todo como texto corrido. Así "2." va antes que "10." (por valor,
    no alfabéticamente) y además "1. Legal" queda antes que "1.1 Laboral",
    porque la comparación sigue siendo carácter a carácter: el espacio va
    antes que el dígito, igual que en el explorador.

    Trocear el texto en partes y comparar por tramos NO sirve: al partir
    ".1 Laboral" el tramo de texto queda en "." y, siendo prefijo de
    ". Legal", ordenaba la subcarpeta antes que su carpeta madre.
    """
    t = (texto or '').strip().lower()
    return re.sub(r'\d+', lambda m: m.group(0)[:12].zfill(12), t)


ORDENES = ('plantilla', 'nombre')
FORMATOS = ('directorio', 'tarjetas', 'tabla')


def _contexto_arbol(proceso, rol, orden='plantilla', formato='directorio'):
    """Valores que necesita la plantilla del árbol. Los comparten el render de
    la página y el refresco AJAX, para que no puedan divergir."""
    nodos = _arbol_nodos(proceso, rol, orden)
    items = proceso.item_ids
    conteo = {'all': len(items), 'mios': 0}
    for est in ('pendiente', 'publicado', 'observado', 'aprobado'):
        conteo[est] = len(items.filtered(lambda i: i.state == est))
    conteo['mios'] = sum(1 for n in nodos if n['tipo'] == 'item' and n['mio'])
    es_prov = rol == ROL_PROVEEDOR
    diff = proceso.diff_estructura() if es_prov else None
    return {
        'proceso': proceso,
        'rol': rol,
        'nodos': nodos,
        'conteo': conteo,
        'puede_editar': es_prov and proceso.puede_reestructurar(),
        'diff': diff,
        'diff_resumen': _resumen_diff(diff),
        'destinos_json': _destinos_json(proceso),
        'orden': orden,
        'formato': formato,
        'n_aprobados': len(items.filtered(
            lambda i: i.state == 'aprobado' and i.attachment_final_id)),
    }


def _arbol_nodos(proceso, rol, orden='plantilla'):
    """Aplana el árbol de carpetas en ORDEN DE LECTURA para pintarlo como un
    directorio: cada nodo lleva su profundidad y su rama.

    Dentro de una carpeta van primero SUS documentos y después sus subcarpetas.
    Para un expediente de requisitos se lee mejor así que al revés: lo que la
    carpeta exige queda pegado a su título.
    """
    carpetas = proceso.folder_ids
    items = proceso.item_ids
    # 'plantilla' respeta el orden que traía el checklist; 'nombre' ordena como
    # un explorador de archivos, con los números por valor.
    if orden == 'nombre':
        clave_c = lambda c: _clave_natural(c.name)
        clave_i = lambda i: _clave_natural(i.name)
    else:
        clave_c = lambda c: (c.sequence, c.id)
        clave_i = lambda i: (i.sequence, i.id)

    por_carpeta = {}
    for it in items:
        por_carpeta.setdefault(it.carpeta_id.id or 0, []).append(it)
    for lista in por_carpeta.values():
        lista.sort(key=clave_i)

    nodos = []

    def _item_nodo(it, nivel, rama):
        cadena = it._cadena()
        return {
            'tipo': 'item', 'nivel': nivel, 'rama': rama, 'item': it,
            'avance': item_avance(it, cadena),
            'mio': item_es_mio(it, rol),
        }

    def _bajar(padre_id, nivel, rama):
        hijas = carpetas.filtered(
            lambda c: c.parent_id.id == padre_id).sorted(clave_c)
        for c in hijas:
            sub = c.parent_path or ''
            nodos.append({'tipo': 'carpeta', 'nivel': nivel, 'rama': rama,
                          'carpeta': c, 'sub': sub})
            for it in por_carpeta.get(c.id, []):
                nodos.append(_item_nodo(it, nivel + 1, sub))
            _bajar(c.id, nivel + 1, sub)

    _bajar(False, 0, '')

    # Documentos que no cuelgan de ninguna carpeta, al final.
    sueltos = por_carpeta.get(0, [])
    if sueltos:
        nodos.append({'tipo': 'carpeta', 'nivel': 0, 'rama': '',
                      'carpeta': None, 'sub': 'sueltos/'})
        for it in sueltos:
            nodos.append(_item_nodo(it, 1, 'sueltos/'))
    return nodos


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

    @http.route('/my/proceso/<int:proceso_id>/arbol', type='http', auth='user',
                website=True)
    def proceso_arbol(self, proceso_id, orden=None, formato=None, **kw):
        """Árbol re-renderizado + contadores, para refrescar tras reorganizar
        sin recargar la página entera."""
        proceso = request.env['certum.rev.proceso'].sudo().browse(proceso_id)
        rol = _rol_en_proceso(proceso) if proceso.exists() else None
        if rol is None:
            return json_err('No tienes acceso a este expediente.', 403)
        ctx = _contexto_arbol(
            proceso, rol,
            orden if orden in ORDENES else 'plantilla',
            formato if formato in FORMATOS else 'directorio')
        html = request.env['ir.ui.view'].sudo()._render_template(
            'certum_revision.sr_proceso_arbol', ctx)
        return json_r({
            'ok': True,
            'html': str(html),
            'conteo': ctx['conteo'],
            'diff': ctx['diff'],
            'diff_resumen': ctx['diff_resumen'],
            'avance': int(proceso.avance),
            'n_aprobados': ctx['n_aprobados'],
        })

    @http.route('/my/proceso/<int:proceso_id>', type='http', auth='user',
                website=True)
    def proceso_detail(self, proceso_id, aviso=None, orden=None, formato=None, **kw):
        proceso = request.env['certum.rev.proceso'].sudo().browse(proceso_id)
        rol = _rol_en_proceso(proceso) if proceso.exists() else None
        if rol is None:
            return request.redirect('/my/certum')
        avisos = {
            'sin_aprobados': 'Todavía no hay documentos aprobados que descargar.',
            'zip_grande': 'El paquete supera el tamaño máximo permitido. '
                          'Descargue los documentos por separado.',
            'purgado': 'Ese archivo ya fue depurado por antigüedad. Se conserva '
                       'el registro de que existió, pero no su contenido.',
        }
        # El contexto del árbol se comparte con el refresco AJAX (/arbol), así
        # la página y la recarga parcial no pueden divergir.
        valores = dict(_contexto_arbol(
            proceso, rol,
            orden if orden in ORDENES else 'plantilla',
            formato if formato in FORMATOS else 'directorio'), **{
            'items_ordenados': proceso.item_ids,
            'nivel': _nivel_usuario(),
            'solicitudes': proceso.solicitud_ids.sorted('create_date', reverse=True),
            'participantes': proceso.revisor_ids.sorted('sequence'),
            'part_data_json': _part_data_json(proceso),
            'dias_purga': request.env['certum.rev.item'].sudo()._param_int_purga(),
            'aviso': avisos.get(aviso or ''),
        })
        return request.render('certum_revision.portal_proceso_detail', valores)

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
