# -*- coding: utf-8 -*-
"""Zona horaria de negocio (America/Lima).

Copia local para models/ y crons: los modelos NO importan el controller.
Mantener en sync con controllers/helpers.py.
"""
from datetime import datetime

try:
    import pytz
    _TZ = pytz.timezone('America/Lima')
except Exception:  # pragma: no cover - fallback si falta pytz
    _TZ = None


def now_lima():
    if _TZ:
        return datetime.now(_TZ)
    return datetime.now()


def today_lima():
    return now_lima().date()
