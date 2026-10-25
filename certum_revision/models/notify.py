# -*- coding: utf-8 -*-
"""Avisos de las transiciones del flujo de revisión.

Funciones libres (NO un Model) que el orquestador cablea a las transiciones de
`certum.rev.item`: marcar_publicado y el paso de turno → notify_publicado,
marcar_aprobado → notify_aprobado, marcar_observado → notify_observado,
revertir_no_reviso → notify_turno_devuelto.

Todas se limitan a ENCOLAR en `certum.rev.correo.envio` (models/correo.py):
la cola los manda al momento por su cron, con la plantilla, el remitente y el
servidor que se eligen en el panel. Un disparador nunca espera al servidor de
correo ni puede tumbar la transición que lo llamó.

La referencia de cada aviso es la misma que usa la Recuperación del panel
(`ref_*` en correo.py): si un disparador no llegó, el panel lo propone; si sí
llegó, nunca sale dos veces.
"""


def _correo(item):
    return item.env['certum.rev.correo.envio']


def notify_publicado(item):
    """Documento esperando revisión → a quien le toca revisarlo AHORA.

    La referencia lleva el archivo vigente y el paso de la cadena: cada
    versión publicada y cada cambio de turno es un aviso nuevo, pero volver a
    llamar con lo mismo no duplica el correo.
    """
    correo = _correo(item)
    correo.avisar('publicado', item, correo.ref_publicado(item))


def notify_aprobado(item):
    """Documento aprobado → al proveedor."""
    correo = _correo(item)
    correo.avisar('aprobado', item, correo.ref_aprobado(item))


def notify_observado(item):
    """Documento observado → al proveedor, con el texto de la observación.

    La fecha de la observación distingue una devolución de la siguiente: el
    mismo documento puede observarse varias veces.
    """
    correo = _correo(item)
    correo.avisar('observado', item, correo.ref_observado(item))


def notify_turno_devuelto(item):
    """El proveedor reabrió un turno vencido → a quien lo recupera.

    Sin este aviso la reversión sería inútil: el revisor dejó pasar su plazo
    una vez, y si nadie le dice que lo tiene otra vez volverá a dejarlo pasar.
    """
    _correo(item).avisar('turno_devuelto', item, 'turno-%s-%s' % (
        item.revision_paso or 0, item.fecha_limite_revision or ''))
