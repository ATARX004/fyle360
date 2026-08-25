# -*- coding: utf-8 -*-
"""Helpers compartidos del portal de revisión (raíz de controllers/).

Otros módulos pueden importarlos de forma estable:
    from odoo.addons.certum_revision.controllers.helpers import _get_rol
"""
import json
import logging
import re
from odoo.http import request

# Fuente ÚNICA de zona horaria del módulo (America/Lima). Antes había aquí una
# copia de estos helpers que además nunca se usaba.
from odoo.addons.certum_revision.models.tz_utils import (  # noqa: F401
    fmt_lima,
    now_lima,
    today_lima,
)

_logger = logging.getLogger(__name__)

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
        return 'El proyecto aún no ha sido abierto.'
    if proc.state in ('completado', 'fuera_plazo') and accion != 'comentar':
        return 'El proyecto ya no está activo.'
    if rol is None:
        return 'No tienes acceso a este ítem.'

    if accion == 'publicar':
        if rol != ROL_PROVEEDOR:
            return 'Solo el proveedor puede publicar documentos.'
        if item.state == 'aprobado':
            return 'Este ítem ya fue aprobado; no admite cambios.'
        if proc.fase == 'vencida':
            return 'El plazo del proyecto ha vencido.'
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


# ── Avance de un ítem y turno del usuario ────────────────────────────
def item_avance(item, cadena=None):
    """Avance del ítem medido en REVISIONES CONSEGUIDAS sobre el total.

    La barra cuenta solo a los revisores: con una cadena de 3, va 0/3 hasta
    que alguien apruebe, 1/3 tras la primera aprobación y 3/3 al quedar
    aprobado. Publicar NO cuenta como avance: entregar no es revisar.

    En modo "cualquiera" no hay cadena, así que se toma como un único visto
    bueno: 0/1 mientras espera y 1/1 al aprobarse.
    """
    cadena = item._cadena() if cadena is None else cadena
    total = len(cadena) or 1

    if item.state == 'aprobado':
        hechas = total
    elif item.state == 'publicado':
        # `revision_paso` es el paso EN CURSO (1-based): las aprobaciones ya
        # conseguidas son las anteriores.
        hechas = max(0, min((item.revision_paso or 1) - 1, total))
    elif item.state == 'observado':
        # Observar NO borra lo ya aprobado: la corrección vuelve a quien
        # observó, y los pasos anteriores conservan su visto bueno. Si la barra
        # cayera a cero aquí, saltaría de vuelta al republicar y daría la
        # impresión de que el trabajo se perdió.
        hechas = max(0, min((item.revision_paso_observado or 1) - 1, total))
    else:
        # Pendiente: aún no ha empezado la revisión.
        hechas = 0

    if item.state == 'aprobado':
        tono, titulo = 'ok', 'Aprobado'
    elif item.state == 'observado':
        tono = 'warn'
        titulo = 'En corrección por el proveedor'
        if hechas:
            titulo += ' · al corregir vuelve al revisor %d, no al principio' % (
                hechas + 1)
    elif item.state == 'pendiente':
        tono, titulo = 'idle', 'Sin publicar'
    elif total == 1:
        tono, titulo = 'brand', 'Pendiente de revisión'
    else:
        tono = 'brand'
        titulo = '%d de %d revisores han aprobado' % (hechas, total)

    return {
        'pct': int(round(100.0 * hechas / total)),
        'label': '%d/%d' % (hechas, total),
        'titulo': titulo,
        'tono': tono,
    }


def item_es_mio(item, rol):
    """True si a ESTE usuario le toca revisar el ítem ahora mismo."""
    if rol != ROL_CLIENTE or item.state != 'publicado':
        return False
    return item.puede_revisar(request.env.user.partner_id, _nivel_usuario())


# ── Serialización del panel de ítem (compartido proveedor/cliente) ───
def _fmt_dt(dt):
    """Datetime de Odoo (UTC) → texto en hora de Lima.

    Un strftime directo sobre el valor almacenado mostraba UTC, es decir 5 horas
    adelantado para el usuario.
    """
    return fmt_lima(dt)


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
                     'auto_aprobado': 'Aprobado por vencimiento',
                     'ampliacion': 'Días de revisión',
                     'reanudado': 'Revisión reanudada',
                     'revertido': 'Turno devuelto',
                     'publicacion_revertida': 'Publicación deshecha',
                     'documento_borrado': 'Archivo eliminado'}
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

    # Mientras está observado, a quién volverá el documento al corregirlo. El
    # proveedor necesita saberlo antes de subir la corrección, porque no vuelve
    # al principio de la cadena sino a quien puso la observación.
    reanuda_en, reanuda_quien = 0, ''
    if item.state == 'observado' and cadena:
        reanuda_en = item._paso_reanudar(cadena)
        step = cadena[reanuda_en - 1] if 1 <= reanuda_en <= len(cadena) else None
        if step and step.get('partner_id'):
            reanuda_quien = request.env['res.partner'].sudo().browse(
                step['partner_id']).display_name
        elif step:
            reanuda_quien = 'Nivel %s' % step.get('nivel')

    # Deshacer la última publicación: cosa del proveedor, que es quien pudo
    # equivocarse de archivo. `publicar_reinicia` avisa de que subir encima de
    # un documento EN REVISIÓN tira abajo lo aprobado y empieza la cadena de
    # cero: no es una corrección, es una versión nueva.
    undo = {'hubo_publicacion': False}
    if rol == ROL_PROVEEDOR:
        d_undo = item._undo_disponible()
        if d_undo['hubo_publicacion']:
            undo = d_undo
    # Borrar archivos: solo el proveedor y solo mientras nadie los haya
    # revisado. Despues son la prueba de sobre que se decidio.
    puede_limpiar = rol == ROL_PROVEEDOR and item._puede_limpiar()
    publicar_reinicia = item.state == 'publicado'
    aprobaciones_en_juego = (max(0, (item.revision_paso or 1) - 1)
                             if publicar_reinicia else 0)

    # Devolver un turno vencido: solo se ofrece a quien puede ejecutarlo, y
    # solo si en este ítem hubo alguna omisión que comentar.
    reversion = {'hubo_omision': False}
    if rol in (ROL_PROVEEDOR, ROL_INTERNO):
        disp = item._reversion_disponible()
        if disp['hubo_omision']:
            reversion = disp

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
        'avance': item_avance(item, cadena),
        'ampliaciones': _ampliaciones_data(item, rol, nivel),
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
            # Sólo con el ítem observado: dónde se retomará la revisión.
            'reanuda_en': reanuda_en,
            'reanuda_quien': reanuda_quien,
            # Turno vencido que el proveedor puede devolver (o el motivo por
            # el que ya no se puede).
            'reversion': reversion,
            # Deshacer la última publicación, y aviso de lo que cuesta
            # publicar encima de un documento que ya se está revisando.
            'undo': undo,
            'publicar_reinicia': publicar_reinicia,
            'puede_limpiar': puede_limpiar,
            'aprobaciones_en_juego': aprobaciones_en_juego,
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


def _ampliaciones_data(item, rol, nivel):
    """Ampliaciones de la ventana de revisión de este ítem, y qué puede hacer
    el usuario con ellas."""
    # El proveedor y el interno también las ven: el primero porque las
    # concede, el segundo porque supervisa.
    if rol not in (ROL_CLIENTE, ROL_PROVEEDOR, ROL_INTERNO):
        return {'puede_pedir': False, 'puede_conceder': False, 'lista': []}
    ETIQUETAS = {'pendiente': 'Pendiente', 'concedida': 'Concedida',
                 'rechazada': 'Rechazada'}
    lista = [{
        'id': a.id,
        'solicitante': a.solicitante_id.display_name or 'Concesión directa',
        'solicitante_id': a.solicitante_id.id or False,
        'beneficiario': a.beneficiario_id.display_name or '',
        'reservada': a.estado == 'concedida' and not a.aplicada,
        'dias_pedidos': a.dias_pedidos,
        'dias_concedidos': a.dias_concedidos,
        'motivo': a.motivo or '',
        'estado': a.estado,
        'estado_label': ETIQUETAS.get(a.estado, a.estado),
        'fecha': _fmt_dt(a.create_date),
    } for a in item.ampliacion_ids.sorted('create_date', reverse=True)]
    # Revisores elegibles como beneficiarios: los de la cadena cuyo turno no
    # ha pasado. En cadenas por NIVEL los pasos no apuntan a nadie concreto,
    # así que ahí solo cabe "el turno actual".
    cadena = item._cadena()
    actual = item.revision_paso or 0
    beneficiarios = []
    for i, paso in enumerate(cadena, start=1):
        pid = paso.get('partner_id')
        if not pid or (actual and i < actual):
            continue
        p = request.env['res.partner'].sudo().browse(pid)
        beneficiarios.append({
            'id': pid,
            'name': p.display_name,
            'paso': i,
            'actual': bool(actual) and i == actual,
        })

    en_revision = item.state == 'publicado'
    return {
        'beneficiarios': beneficiarios,
        # Cualquier persona del cliente pide más días mientras el documento
        # esté en revisión; conceder es potestad del PROVEEDOR, que es quien
        # fijó esos días al publicar.
        'puede_pedir': en_revision and rol == ROL_CLIENTE,
        'puede_conceder': en_revision and rol == ROL_PROVEEDOR,
        'lista': lista,
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
