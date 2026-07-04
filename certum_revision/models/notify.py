# -*- coding: utf-8 -*-
"""Notificaciones por correo del flujo de revisión.

Funciones libres (NO un Model nuevo) que el orquestador cablea a las
transiciones de certum.rev.item: marcar_publicado → notify_publicado,
marcar_aprobado → notify_aprobado, marcar_observado → notify_observado.

Cada función:
    - recibe el recordset `item` (certum.rev.item) y usa item.env;
    - resuelve la mail.template por xmlid con env.ref(..., raise_if_not_found=False);
    - envía con .send_mail(item.id, force_send=False) — la cola de correo se
      encarga del envío real, para no bloquear la transición;
    - es idempotente y NUNCA propaga una excepción hacia afuera (todo va
      envuelto en try/except con _logger.exception);
    - si falta el destinatario o la plantilla, loguea y retorna sin fallar.

No importa item.py ni añade dependencias; se apoya solo en `mail`.
"""
import logging

_logger = logging.getLogger(__name__)

# xmlids de las plantillas definidas en data/mail_templates.xml
TPL_PUBLICADO = 'certum_revision.template_item_publicado'
TPL_APROBADO = 'certum_revision.template_item_aprobado'
TPL_OBSERVADO = 'certum_revision.template_item_observado'


def _enviar(item, xmlid, destinatario_email, etiqueta):
    """Envía la plantilla `xmlid` para `item`. Nunca lanza hacia afuera.

    - Si no hay destinatario, loguea y retorna (no es un error).
    - Si la plantilla no existe (módulo mail sin datos cargados), loguea
      y retorna.
    - Cualquier fallo del envío se registra con _logger.exception.
    """
    try:
        if not destinatario_email:
            _logger.info(
                '[AUDIT] notify_omitido accion=%s item=%s motivo=sin_destinatario',
                etiqueta, item.id)
            return

        template = item.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning(
                'notify %s: plantilla %s no encontrada; se omite item=%s',
                etiqueta, xmlid, item.id)
            return

        template.sudo().send_mail(item.id, force_send=False)
        _logger.info('[AUDIT] notify_enviado accion=%s item=%s to=%s',
                     etiqueta, item.id, destinatario_email)
    except Exception:
        _logger.exception('notify %s: fallo enviando correo para item=%s',
                          etiqueta, getattr(item, 'id', '?'))


def notify_publicado(item):
    """Ítem publicado por el proveedor → avisa al CLIENTE del proceso."""
    try:
        destinatario = item.proceso_id.cliente_id.email
    except Exception:
        _logger.exception('notify_publicado: no se pudo leer el destinatario '
                          'item=%s', getattr(item, 'id', '?'))
        return
    _enviar(item, TPL_PUBLICADO, destinatario, 'publicado')


def notify_aprobado(item):
    """Ítem aprobado por el cliente → avisa al PROVEEDOR del proceso."""
    try:
        destinatario = item.proceso_id.proveedor_id.email
    except Exception:
        _logger.exception('notify_aprobado: no se pudo leer el destinatario '
                          'item=%s', getattr(item, 'id', '?'))
        return
    _enviar(item, TPL_APROBADO, destinatario, 'aprobado')


def notify_observado(item):
    """Ítem observado por el cliente → avisa al PROVEEDOR (con último comentario)."""
    try:
        destinatario = item.proceso_id.proveedor_id.email
    except Exception:
        _logger.exception('notify_observado: no se pudo leer el destinatario '
                          'item=%s', getattr(item, 'id', '?'))
        return
    _enviar(item, TPL_OBSERVADO, destinatario, 'observado')
