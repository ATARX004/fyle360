# -*- coding: utf-8 -*-
"""Base del panel de administración de FYLE 360 (solo Certum interno).

Toda la administración vive aquí, en la web: el módulo ya no tiene menús ni
vistas en el backend de Odoo. Cada pantalla del panel hereda de `AdminBase`,
que da tres cosas:

* `_guard()`: solo personal interno; el resto vuelve al inicio.
* `_ctx(seccion, **valores)`: lo que necesita el marco común (el aviso que
  llega en la URL).
* `responder(...)`: la misma respuesta para un formulario normal (redirige
  con el aviso en la URL) y para uno enviado por AJAX (JSON con el aviso, los
  errores por campo y los trozos de pantalla que cambian).
"""
import logging
from urllib.parse import quote

from odoo import http
from odoo.http import request

from ..helpers import ROL_INTERNO, _es_interno, is_ajax, json_r

_logger = logging.getLogger(__name__)

RUTA_ADMIN = '/my/certum/admin'

def auditar(evento, **datos):
    """Una línea [AUDIT] con quién hizo qué desde el panel."""
    detalle = ' '.join('%s=%s' % (k, v) for k, v in datos.items())
    _logger.info('[AUDIT] admin_%s user=%s %s', evento, request.env.user.id, detalle)


def responder(url, ok=None, error=None, errores=None, fragmentos=None):
    """Respuesta común de las acciones del panel.

    Con AJAX: JSON {ok, mensaje|error, errores, fragmentos}. `fragmentos` es
    una función (para no pintar nada si la acción falló) que devuelve
    {nombre: html} con lo que hay que repintar.
    Sin AJAX: redirige a `url` con el aviso en la URL, antes del #.
    """
    if is_ajax():
        datos = {'ok': not error}
        if error:
            datos['error'] = error
        if ok:
            datos['mensaje'] = ok
        if errores:
            datos['errores'] = errores
        if fragmentos and not error:
            datos['fragmentos'] = fragmentos()
        return json_r(datos, 200 if not error else 400)
    ruta, _sep, ancla = url.partition('#')
    aviso = ('error=%s' % quote(error)) if error else ('ok=%s' % quote(ok or ''))
    destino = '%s%s%s' % (ruta, '&' if '?' in ruta else '?', aviso)
    return request.redirect(destino + ('#' + ancla if ancla else ''))


class AdminBase(http.Controller):

    def _guard(self):
        """Solo Certum interno. None si puede pasar; si no, la respuesta."""
        if _es_interno():
            return None
        if is_ajax():
            return json_r({'ok': False, 'error': 'Solo personal interno de Certum.'}, 403)
        return request.redirect('/my/certum')

    def _ctx(self, seccion, **valores):
        """Contexto del marco del panel + los valores de la pantalla.

        La navegación (con sus contadores) la pone el menú lateral común
        (certum.rev.proceso.fyle_menu); aquí solo va lo de la pantalla.
        """
        args = request.httprequest.args
        ctx = {
            'rol': ROL_INTERNO,
            'seccion': seccion,
            'aviso_ok': args.get('ok') or '',
            'aviso_error': args.get('error') or '',
        }
        ctx.update(valores)
        return ctx
