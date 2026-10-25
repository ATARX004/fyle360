# -*- coding: utf-8 -*-
"""Landing pública de FYLE 360: /fyle360.

Puerta de entrada al producto, con la misma familia visual que las de
Hygiene 360 (/hygiene360) y Nuestros productos (/Myproducts): página propia,
héroe navy de Certum, Montserrat. Dos caminos siempre a la vista:

  - Ir a la plataforma: al Inicio (/my/certum) si ya hay sesión, o al login
    con vuelta al Inicio si no la hay.
  - Contratar el servicio: WhatsApp comercial, con el mensaje ya escrito.

El número y el correo comercial se cambian en Administración → Ajustes, sin
desplegar (parámetros PARAM_WHATSAPP y PARAM_EMAIL).
"""
from urllib.parse import quote

from odoo import http
from odoo.http import request

PARAM_WHATSAPP = 'certum_revision.whatsapp'
PARAM_EMAIL = 'certum_revision.email_comercial'
WHATSAPP_DEFAULT = '51946766702'            # comercial de Certum (Brochure 2026)
EMAIL_DEFAULT = 'comercial@certumglobal.pe'
MENSAJE = 'Hola, quiero contratar FYLE 360 para la revisión documental con mis proveedores.'
INICIO = '/my/certum'


def contacto(env):
    """{wa_url, wa_texto, email, email_url} con lo guardado en Ajustes."""
    Param = env['ir.config_parameter'].sudo()
    numero = ''.join(c for c in (Param.get_param(PARAM_WHATSAPP) or '') if c.isdigit())
    numero = numero or WHATSAPP_DEFAULT
    if len(numero) == 9:                     # local peruano: se antepone el 51
        numero = '51' + numero
    email = (Param.get_param(PARAM_EMAIL) or '').strip() or EMAIL_DEFAULT
    if len(numero) == 11 and numero.startswith('51'):
        texto = '+51 %s %s %s' % (numero[2:5], numero[5:8], numero[8:])
    else:
        texto = '+' + numero
    return {
        'wa_numero': numero,
        'wa_url': 'https://wa.me/%s?text=%s' % (numero, quote(MENSAJE)),
        'wa_texto': texto,
        'email': email,
        'email_url': 'mailto:%s?subject=%s' % (email, quote('Quiero contratar FYLE 360')),
    }


class Fyle360Landing(http.Controller):

    @http.route(['/fyle360', '/fyle360/', '/Fyle360'], type='http', auth='public',
                website=False, sitemap=True)
    def landing(self, **kw):
        logueado = not request.env.user._is_public()
        vals = {
            'logueado': logueado,
            'plataforma_url': INICIO if logueado else '/web/login?redirect=%s' % quote(INICIO),
        }
        vals.update(contacto(request.env))
        return request.render('certum_revision.landing', vals)
