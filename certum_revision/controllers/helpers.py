# -*- coding: utf-8 -*-
"""Helpers compartidos del portal de revisión (raíz de controllers/).

Otros módulos pueden importarlos de forma estable:
    from odoo.addons.certum_revision.controllers.helpers import _get_rol
"""
import json
import logging
import re
from datetime import datetime

from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    import pytz
    _TZ = pytz.timezone('America/Lima')
except Exception:  # pragma: no cover
    _TZ = None

# ── Roles ─────────────────────────────────────────────────────────────
ROL_PROVEEDOR = 'proveedor'
ROL_CLIENTE = 'cliente'
ROL_INTERNO = 'interno'

# ── Uploads ───────────────────────────────────────────────────────────
DEFAULT_MAX_UPLOAD_MB = 50
_FILENAME_BAD_CHARS = re.compile(r'[<>:"\'\\|?*\x00-\x1f]')

ITEM_STATE_LABELS = {
    'pendiente': 'Pendiente',
    'publicado': 'Publicado',
    'observado': 'Observado',
    'aprobado': 'Aprobado',
}


# ── Zona horaria de negocio ───────────────────────────────────────────
def _now_lima():
    if _TZ:
        return datetime.now(_TZ)
    return datetime.now()


def _today_lima():
    return _now_lima().date()


# ── Respuestas AJAX ───────────────────────────────────────────────────
def is_ajax():
    return request.httprequest.headers.get('X-Requested-With') == 'XMLHttpRequest'


def json_r(data, status=200):
    return request.make_response(
        json.dumps(data, default=str),
        headers=[('Content-Type', 'application/json')],
        status=status,
    )


def json_err(msg, status=400):
    return json_r({'ok': False, 'error': msg}, status=status)


# ── Roles y propiedad ─────────────────────────────────────────────────
def _empresa():
    """Partner-empresa del usuario. Nunca user.partner_id directo:
    los usuarios portal suelen ser contactos hijos de la empresa."""
    return request.env.user.partner_id.commercial_partner_id


def _get_rol():
    user = request.env.user
    if not user.share:
        return ROL_INTERNO
    # El rol vive SIEMPRE en la empresa (commercial_partner_id), coherente con
    # el panel admin que solo opera sobre is_company. Sin fallback al contacto.
    return _empresa().rol_en_certum or False


def _rol_en_proceso(proceso):
    """Rol del usuario actual RESPECTO a un proceso concreto (o None).

    Se resuelve por la EMPRESA del usuario primero: si su empresa es el
    proveedor o el cliente del proceso, actúa como tal —aunque sea usuario
    interno— para que pueda publicar/revisar cuando su empresa participa.
    Un interno sin relación directa queda como supervisor (solo comenta);
    un usuario portal sin relación no tiene acceso.
    """
    emp = _empresa()
    if proceso.proveedor_id.id == emp.id:
        return ROL_PROVEEDOR
    if proceso.cliente_id.id == emp.id:
        return ROL_CLIENTE
    if not request.env.user.share:
        return ROL_INTERNO
    return None


def _puede_ver_proceso(proceso):
    return _rol_en_proceso(proceso) is not None


def _nivel_usuario():
    """Nivel jerárquico del contacto-persona logueado (1 = máximo, 0 = ninguno)."""
    return request.env.user.partner_id.certum_nivel or 0


# ── Máquina de estados: validación central (§6 del plan) ─────────────
def _get_item_error(item, accion, rol):
    """Devuelve un mensaje de error si `rol` NO puede ejecutar `accion`
    sobre `item` en su estado/fase actual; None si puede.
    Publicar, aprobar, observar y comentar delegan aquí."""
    proc = item.proceso_id
    if proc.state == 'borrador':
        return 'El proceso aún no ha sido abierto.'
    if proc.state in ('completado', 'fuera_plazo') and accion != 'comentar':
        return 'El proceso ya no está activo.'
    if rol is None:
        return 'No tienes acceso a este ítem.'

    if accion == 'publicar':
        if rol != ROL_PROVEEDOR:
            return 'Solo el proveedor puede publicar documentos.'
        if item.state == 'aprobado':
            return 'Este ítem ya fue aprobado; no admite cambios.'
        if proc.fase == 'vencida':
            return 'El plazo del proceso ha vencido.'
    elif accion in ('aprobar', 'observar'):
        if rol != ROL_CLIENTE:
            return 'Solo el cliente puede revisar este ítem.'
        if item.state != 'publicado':
            return 'Solo se puede revisar un ítem publicado.'
    elif accion == 'comentar':
        if rol not in (ROL_PROVEEDOR, ROL_CLIENTE, ROL_INTERNO):
            return 'No tienes acceso a este ítem.'
    elif accion == 'descargar':
        pass  # basta la propiedad (rol ya validado arriba)
    else:
        return 'Acción desconocida.'
    return None


# ── Validación de uploads ─────────────────────────────────────────────
def _max_upload_bytes():
    icp = request.env['ir.config_parameter'].sudo()
    try:
        mb = int(icp.get_param('certum_revision.max_upload_mb',
                               DEFAULT_MAX_UPLOAD_MB))
    except (TypeError, ValueError):
        mb = DEFAULT_MAX_UPLOAD_MB
    return mb * 1024 * 1024


def _validar_tamano_archivo(data):
    """None si ok; mensaje de error si excede el máximo."""
    limite = _max_upload_bytes()
    if len(data or b'') > limite:
        _logger.warning('[AUDIT] upload_rechazado user=%s size=%s limite=%s',
                        request.env.user.id, len(data or b''), limite)
        return 'El archivo supera el tamaño máximo de %d MB.' % (
            limite // (1024 * 1024))
    return None


def _safe_upload_filename(name):
    name = (name or 'documento').strip().replace('\\', '/')
    name = name.rsplit('/', 1)[-1]              # sin path traversal
    name = _FILENAME_BAD_CHARS.sub('', name)    # sin caracteres XSS/raros
    name = name.replace('..', '.')
    return name[:200] or 'documento'


# ── Serialización del panel de ítem (compartido proveedor/cliente) ───
def _fmt_dt(dt):
    return dt.strftime('%d/%m/%Y %H:%M') if dt else ''


def item_panel_data(item, rol):
    """JSON del drawer del ítem: datos + hilo + acciones según rol/estado."""
    comments = [{
        'id': c.id,
        'autor': c.author_id.display_name,
        'rol': c.rol,
        'body': c.body,
        'fecha': _fmt_dt(c.create_date),
        'propio': c.author_id.id == request.env.user.partner_id.id,
    } for c in item.comment_ids]
    attachments = [{
        'id': a.id,
        'name': a.name,
        'fecha': _fmt_dt(a.create_date),
        'vigente': a.id == item.attachment_final_id.id,
        # Depurado: el registro existe pero el contenido ya se borró.
        'purgado': bool(a.certum_purgado),
        'purgado_fecha': _fmt_dt(a.certum_purgado_fecha),
        'url': '/my/item/%d/download/%d' % (item.id, a.id),
    } for a in item.attachment_ids.sorted('create_date', reverse=True)]
    attachments_cliente = [{
        'id': a.id,
        'name': a.name,
        'fecha': _fmt_dt(a.create_date),
        'purgado': bool(a.certum_purgado),
        'purgado_fecha': _fmt_dt(a.certum_purgado_fecha),
        'url': '/my/item/%d/download/%d' % (item.id, a.id),
    } for a in item.attachment_cliente_ids.sorted('create_date', reverse=True)]
    accion_labels = {'aprobado': 'Aprobó', 'observado': 'Observó',
                     'no_reviso': 'No revisó a tiempo',
                     'auto_aprobado': 'Aprobado por vencimiento'}
    trazas = [{
        'autor': t.partner_id.display_name,
        'nivel': t.nivel,
        'lado': t.lado,
        'accion': t.accion,
        'accion_label': accion_labels.get(t.accion, t.accion),
        'fecha': _fmt_dt(t.fecha),
        'comentario': t.comentario or '',
    } for t in item.aprobacion_ids.sorted('fecha', reverse=True)]

    proc = item.proceso_id
    nivel = _nivel_usuario()
    puede_rev = (_get_item_error(item, 'aprobar', rol) is None
                 and item.puede_revisar(request.env.user.partner_id, nivel))

    # Paso / revisor actual (de quién se espera la revisión ahora)
    cadena = item._cadena()
    paso = item.revision_paso or 0
    revisor_actual = ''
    if cadena and 1 <= paso <= len(cadena):
        step = cadena[paso - 1]
        if step.get('partner_id'):
            revisor_actual = request.env['res.partner'].sudo().browse(
                step['partner_id']).display_name
        else:
            revisor_actual = 'Nivel %s' % step.get('nivel')

    # Cadena a medida POR ÍTEM: la decide el PROVEEDOR, que es quien sabe qué
    # especialidad necesita cada requisito. Los revisores siguen siendo personas
    # del CLIENTE (son quienes aprueban). Solo se puede tocar mientras el ítem
    # no está en revisión activa: pendiente u observado.
    puede_config = (rol == ROL_PROVEEDOR
                    and item.state in ('pendiente', 'observado'))
    contactos, revisores = [], []
    if rol in (ROL_PROVEEDOR, ROL_CLIENTE):
        # El cliente la ve en solo lectura (para saber por quién pasa su ítem);
        # el proveedor además puede editarla.
        contactos = [{'id': c.id, 'name': c.display_name,
                      'nivel': c.certum_nivel or 0}
                     for c in request.env['res.partner'].sudo().search([
                         ('parent_id', '=', item.cliente_id.id),
                         ('is_company', '=', False)], order='certum_nivel, name')]
        revisores = [{'id': r.partner_id.id, 'name': r.partner_id.display_name}
                     for r in item.revisor_ids.sorted('sequence')]
    return {
        'ok': True,
        'item': {
            'id': item.id,
            'name': item.name,
            'description': item.description or '',
            'required': item.required,
            'state': item.state,
            'state_label': ITEM_STATE_LABELS.get(item.state, item.state),
            'carpeta': item.carpeta_id.name or 'General',
            'fecha_publicacion': _fmt_dt(item.fecha_publicacion),
            'fecha_revision': _fmt_dt(item.fecha_revision),
            'attachments': attachments,
            'attachments_cliente': attachments_cliente,
            'comments': comments,
            'trazas': trazas,
        },
        'rol': rol,
        'nivel': nivel,
        'revision': {
            'modo': proc.revision_modo,
            'capas': proc.revision_capas,
            'nivel_actual': item.revision_nivel,
            'revisor_actual': revisor_actual,
            'paso_actual': paso,
            'total_pasos': len(cadena),
            'a_medida': bool(item.revisor_ids),
            # De dónde sale la cadena que rige este ítem: excepción propia,
            # participantes heredados del proceso, capas por nivel o nadie.
            'origen_cadena': ('propia' if item.revisores_propios
                              else 'heredada' if item.revisor_ids
                              else 'proceso' if (proc.revision_modo == 'personas'
                                                 and proc.revisor_ids)
                              else 'niveles' if proc.revision_modo == 'secuencial'
                              else 'cualquiera'),
            'dias_revision': item.dias_revision,
            'limite_revision': _fmt_dt(item.fecha_limite_revision),
            'limite_correccion': _fmt_dt(item.fecha_limite_correccion),
        },
        'config_revisores': {
            'puede': puede_config,
            'contactos': contactos,
            'revisores': revisores,
        },
        'acciones': {
            'publicar': _get_item_error(item, 'publicar', rol) is None,
            'primera_publicacion': not item.dias_revision,
            'aprobar': puede_rev,
            'observar': puede_rev,
            'comentar': _get_item_error(item, 'comentar', rol) is None,
        },
    }


def get_item_or_none(item_id):
    """Ítem con sudo + verificación de propiedad. (item, rol) o (None, None)."""
    item = request.env['certum.rev.item'].sudo().browse(int(item_id))
    if not item.exists():
        return None, None
    rol = _rol_en_proceso(item.proceso_id)
    if rol is None:
        return None, None
    return item, rol


# ── Interno (backend web) ─────────────────────────────────────────────
def _es_interno():
    """True si el usuario es interno de Certum (no portal)."""
    return not request.env.user.share


def _rol_de_partner(partner):
    """Rol declarado de una compañía (proveedor/cliente/interno) o ''."""
    p = partner.commercial_partner_id if partner else partner
    return (p.rol_en_certum or '') if p else ''


# ── Plantillas (checklist) — propiedad del proveedor ─────────────────
def _checklist_or_none(checklist_id):
    """Checklist con sudo + verificación de acceso.

    Devuelve (checklist, rol) donde rol es 'interno' o 'proveedor' (dueño);
    (None, None) si no existe o el usuario no tiene acceso.
    """
    ch = request.env['certum.rev.checklist'].sudo().browse(int(checklist_id))
    if not ch.exists():
        return None, None
    if _es_interno():
        return ch, ROL_INTERNO
    if ch.proveedor_id and ch.proveedor_id.id == _empresa().id:
        return ch, ROL_PROVEEDOR
    return None, None


def _mis_checklists():
    """Checklists visibles para el usuario actual (sudo)."""
    Checklist = request.env['certum.rev.checklist'].sudo()
    if _es_interno():
        return Checklist.search([])
    return Checklist.search([('proveedor_id', '=', _empresa().id)])


def _companias_por_rol(rol=None):
    """Compañías (is_company) filtradas por rol_en_certum; para el admin."""
    dom = [('is_company', '=', True)]
    if rol:
        dom.append(('rol_en_certum', '=', rol))
    return request.env['res.partner'].sudo().search(dom, order='name')


def _clientes_seleccionables(proveedor):
    """Clientes que un proveedor puede elegir: los asignados por Certum.

    Si el proveedor no tiene clientes asignados, devuelve un recordset vacío
    (no se le muestran todos los clientes del sistema).
    """
    if not proveedor:
        return request.env['res.partner'].sudo().browse()
    return proveedor.sudo().certum_cliente_ids.filtered('is_company')
