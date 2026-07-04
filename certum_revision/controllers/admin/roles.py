# -*- coding: utf-8 -*-
"""Panel de administración general (Certum interno): asignar roles a las
compañías desde la web.

Solo personal interno. Toda la escritura se hace con sudo sobre el
commercial_partner_id, con validación de rol EN CÓDIGO y auditoría.
"""
import logging

from odoo import http
from odoo.http import request

from ..helpers import (
    ROL_CLIENTE,
    ROL_INTERNO,
    ROL_PROVEEDOR,
    _es_interno,
    is_ajax,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)

# Roles asignables desde el panel ('' = quitar el rol).
_ROLES_VALIDOS = {ROL_PROVEEDOR, ROL_CLIENTE, ROL_INTERNO, ''}


class CertumRevAdminRoles(http.Controller):

    @http.route('/my/certum/admin', type='http', auth='user', website=True)
    def admin_roles(self, q=None, **kw):
        if not _es_interno():
            return request.redirect('/my/certum')

        Partner = request.env['res.partner'].sudo()
        dom = [('is_company', '=', True)]
        q = (q or '').strip()
        if q:
            dom.append(('name', 'ilike', q))
        companias = Partner.search(dom, order='name')

        # KPIs por rol (contadores globales, sin el filtro de búsqueda).
        base = [('is_company', '=', True)]
        n_prov = Partner.search_count(base + [('rol_en_certum', '=', ROL_PROVEEDOR)])
        n_cli = Partner.search_count(base + [('rol_en_certum', '=', ROL_CLIENTE)])
        n_int = Partner.search_count(base + [('rol_en_certum', '=', ROL_INTERNO)])
        n_sin = Partner.search_count(base + [('rol_en_certum', 'in', (False, ''))])

        kpis = [
            {'icon': 'i-folder', 'label': 'Proveedores', 'tone': 'brand', 'value': n_prov},
            {'icon': 'i-eye', 'label': 'Clientes', 'tone': 'ok', 'value': n_cli},
            {'icon': 'i-shield', 'label': 'Internos', 'tone': 'warn', 'value': n_int},
            {'icon': 'i-alert', 'label': 'Sin rol', 'tone': 'danger', 'value': n_sin},
        ]

        return request.render('certum_revision.admin_roles', {
            'rol': ROL_INTERNO,
            'companias': companias,
            'kpis': kpis,
            'q': q,
        })

    @http.route('/my/certum/admin/rol', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def admin_set_rol(self, partner_id=None, rol=None, **post):
        if not _es_interno():
            if is_ajax():
                return json_err('Solo personal interno.', 403)
            return request.redirect('/my/certum')

        # Normaliza y valida el rol.
        rol = (rol or '').strip()
        if rol not in _ROLES_VALIDOS:
            return json_err('Rol no válido.', 400)

        # Localiza la compañía (siempre sobre el commercial_partner_id).
        try:
            pid = int(partner_id)
        except (TypeError, ValueError):
            return json_err('Compañía no válida.', 400)

        partner = request.env['res.partner'].sudo().browse(pid)
        if not partner.exists():
            return json_err('Compañía no encontrada.', 404)
        empresa = partner.commercial_partner_id
        if not empresa or not empresa.is_company:
            return json_err('Solo se puede asignar rol a una compañía.', 400)

        empresa.write({'rol_en_certum': rol or False})
        _logger.info('[AUDIT] admin_set_rol user=%s partner=%s rol=%s',
                     request.env.user.id, empresa.id, rol or '(sin rol)')

        if is_ajax():
            return json_r({'ok': True, 'partner_id': empresa.id, 'rol': rol})
        return request.redirect('/my/certum/admin')
