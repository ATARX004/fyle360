# -*- coding: utf-8 -*-
"""Zona horaria de negocio: America/Lima. FUENTE ÚNICA del módulo.

Regla del proyecto: **Odoo guarda los Datetime en UTC** (convención del ORM, no
se toca) y **todo lo que ve o decide el negocio va en hora de Lima**. Este
módulo es el único sitio donde se convierte entre ambos mundos; controllers y
modelos lo importan en vez de reimplementarlo.

Perú está en UTC-5 **todo el año** (no aplica horario de verano desde 1994), así
que el respaldo sin `pytz` usa un desfase fijo de -5 h y es igual de exacto que
la base de datos de zonas horarias.

Cómo usarlo:
  - `today_lima()` / `now_lima()` → para DECIDIR (qué día es hoy en Lima).
  - `fmt_lima(dt)`               → para MOSTRAR un Datetime de Odoo al usuario.
  - `fin_de_dia_utc(fecha)`      → para GUARDAR "el final de ese día en Lima".
"""
from datetime import datetime, time, timedelta, timezone

TZ_NEGOCIO = 'America/Lima'
_UTC = timezone.utc
# Perú no aplica horario de verano: el desfase es constante.
_OFFSET_FIJO = timezone(timedelta(hours=-5))

try:
    import pytz
    _TZ = pytz.timezone(TZ_NEGOCIO)
except Exception:  # pragma: no cover - respaldo si falta pytz
    _TZ = None


def _localizar(dt_naive):
    """Datetime naive interpretado como hora de LIMA → datetime con zona."""
    if _TZ is not None:
        return _TZ.localize(dt_naive)
    return dt_naive.replace(tzinfo=_OFFSET_FIJO)


def now_lima():
    """Ahora mismo, en hora de Lima (con zona)."""
    return datetime.now(_TZ or _OFFSET_FIJO)


def today_lima():
    """El día de hoy SEGÚN LIMA.

    Importante para las decisiones de fecha: entre las 19:00 y la medianoche de
    Lima, en UTC ya es el día siguiente.
    """
    return now_lima().date()


def a_lima(dt_utc):
    """Datetime de Odoo (naive, en UTC) → datetime con zona de Lima."""
    if not dt_utc:
        return None
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=_UTC)
    return dt_utc.astimezone(_TZ or _OFFSET_FIJO)


def fmt_lima(dt_utc, fmt='%d/%m/%Y %H:%M'):
    """Formatea para el usuario un Datetime de Odoo en hora de Lima.

    Sin esto, un `strftime` directo sobre el valor almacenado muestra UTC, que
    en Lima se ve 5 horas adelantado.
    """
    local = a_lima(dt_utc)
    return local.strftime(fmt) if local else ''


def a_utc(dt_lima):
    """Datetime naive en hora de Lima → naive en UTC (formato de guardado)."""
    if not dt_lima:
        return None
    if dt_lima.tzinfo is None:
        dt_lima = _localizar(dt_lima)
    return dt_lima.astimezone(_UTC).replace(tzinfo=None)


def fin_de_dia_utc(fecha):
    """Último instante de `fecha` EN LIMA, listo para guardar en Odoo (UTC).

    Se usa como tope de los plazos: un vencimiento "el 30 de septiembre" debe
    agotarse a las 23:59:59 de Lima, no a las 23:59:59 UTC (que son las 18:59
    de Lima y recortaría cinco horas al plazo).
    """
    if not fecha:
        return None
    return a_utc(datetime.combine(fecha, time(23, 59, 59)))
