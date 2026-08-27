# -*- coding: utf-8 -*-
"""Avisos de las transiciones del flujo de revisión.

Funciones libres (NO un Model) que el orquestador cablea a las transiciones de
`certum.rev.item`: marcar_publicado → notify_publicado, marcar_aprobado →
notify_aprobado, marcar_observado → notify_observado, revertir_no_reviso →
notify_turno_devuelto.

Desde 2026-08-26 todas delegan en **`certum.rev.aviso`**, el despachador
único: de ahí salen el interruptor por evento, el remitente y el servidor
comunes, la copia global, el registro de lo enviado y la garantía de que un
fallo de correo nunca tumba la transición que lo disparó.

Los avisos ya no van al buzón genérico de la empresa: van a las **personas**,
y en los documentos con cadena, a **quien le toca revisar ahora**. Un buzón
que nadie mira es la forma más común de que un plazo se venza «sin que nadie
se enterara».
"""
import logging

_logger = logging.getLogger(__name__)

TPL_PUBLICADO = 'certum_revision.template_item_publicado'
TPL_APROBADO = 'certum_revision.template_item_aprobado'
TPL_OBSERVADO = 'certum_revision.template_item_observado'
TPL_TURNO_DEVUELTO = 'certum_revision.template_item_turno_devuelto'


def _aviso(item):
    return item.env['certum.rev.aviso']


def notify_publicado(item):
    """Documento publicado → a quien le toca revisarlo.

    La clave de repetición lleva el id del archivo vigente: cada versión
    publicada es un aviso nuevo, pero republicar la misma no duplica el
    correo.
    """
    try:
        env = _aviso(item)
        env.enviar('publicado', item, TPL_PUBLICADO,
                   env.correos_turno(item),
                   clave='att-%s' % (item.attachment_final_id.id or 0))
    except Exception:  # noqa: BLE001
        _logger.exception('notify_publicado: item=%s', getattr(item, 'id', '?'))


def notify_aprobado(item):
    """Documento aprobado → al proveedor."""
    try:
        env = _aviso(item)
        env.enviar('aprobado', item, TPL_APROBADO,
                   env.correos_empresa(item.proceso_id.proveedor_id),
                   clave='att-%s' % (item.attachment_final_id.id or 0))
    except Exception:  # noqa: BLE001
        _logger.exception('notify_aprobado: item=%s', getattr(item, 'id', '?'))


def notify_observado(item):
    """Documento observado → al proveedor, con el texto de la observación."""
    try:
        env = _aviso(item)
        # La fecha de la observación distingue una devolución de la siguiente:
        # el mismo documento puede observarse varias veces.
        env.enviar('observado', item, TPL_OBSERVADO,
                   env.correos_empresa(item.proceso_id.proveedor_id),
                   clave='obs-%s' % (item.fecha_revision or ''))
    except Exception:  # noqa: BLE001
        _logger.exception('notify_observado: item=%s', getattr(item, 'id', '?'))


def notify_turno_devuelto(item):
    """El proveedor reabrió un turno vencido → a quien lo recupera.

    Sin este aviso la reversión sería inútil: el revisor dejó pasar su plazo
    una vez, y si nadie le dice que lo tiene otra vez volverá a dejarlo pasar.
    """
    try:
        env = _aviso(item)
        env.enviar('turno_devuelto', item, TPL_TURNO_DEVUELTO,
                   env.correos_turno(item),
                   clave='turno-%s-%s' % (item.revision_paso or 0,
                                          item.fecha_limite_revision or ''))
    except Exception:  # noqa: BLE001
        _logger.exception('notify_turno_devuelto: item=%s',
                          getattr(item, 'id', '?'))
