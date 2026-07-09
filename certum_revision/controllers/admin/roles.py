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

        # Pool de compañías cliente (para el modal de "clientes asignados").
        clientes_all = Partner.search(
            base + [('rol_en_certum', '=', ROL_CLIENTE)], order='name')

        return request.render('certum_revision.admin_roles', {
            'rol': ROL_INTERNO,
            'companias': companias,
            'clientes_all': clientes_all,
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

    @http.route('/my/certum/admin/clientes', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def admin_set_clientes(self, partner_id=None, cliente_ids=None, **post):
        """Asigna a un PROVEEDOR las compañías cliente que podrá elegir."""
        if not _es_interno():
            if is_ajax():
                return json_err('Solo personal interno.', 403)
            return request.redirect('/my/certum')

        try:
            pid = int(partner_id)
        except (TypeError, ValueError):
            return json_err('Compañía no válida.', 400)

        empresa = request.env['res.partner'].sudo().browse(pid).commercial_partner_id
        if not empresa or not empresa.is_company:
            return json_err('Compañía no encontrada.', 404)
        # Solo tiene sentido asignar clientes a un PROVEEDOR.
        if empresa.rol_en_certum != ROL_PROVEEDOR:
            return json_err('Solo un proveedor puede tener clientes asignados.', 400)

        # Parsea los ids recibidos y valida que sean compañías con rol cliente.
        raw = cliente_ids if cliente_ids is not None else post.get('cliente_ids', '')
        pedidos = [int(x) for x in str(raw).split(',') if x.strip().isdigit()]
        validos = request.env['res.partner'].sudo().search([
            ('id', 'in', pedidos),
            ('is_company', '=', True),
            ('rol_en_certum', '=', ROL_CLIENTE),
        ])
        empresa.write({'certum_cliente_ids': [(6, 0, validos.ids)]})
        _logger.info('[AUDIT] admin_set_clientes user=%s empresa=%s n_clientes=%s',
                     request.env.user.id, empresa.id, len(validos))

        if is_ajax():
            return json_r({'ok': True, 'partner_id': empresa.id,
                           'cliente_ids': validos.ids, 'count': len(validos)})
        return request.redirect('/my/certum/admin')

    # ── Niveles del personal (jerarquía) ──────────────────────────────
    @http.route('/my/certum/admin/personal/<int:company_id>', type='http',
                auth='user', website=True)
    def admin_personal(self, company_id, **kw):
        """Devuelve los contactos-persona de una compañía con su nivel."""
        if not _es_interno():
            return json_err('Solo personal interno.', 403)
        company = request.env['res.partner'].sudo().browse(company_id)
        if not company.exists() or not company.is_company:
            return json_err('Compañía no encontrada.', 404)
        contactos = request.env['res.partner'].sudo().search([
            ('parent_id', '=', company.id),
            ('is_company', '=', False),
        ], order='certum_nivel, name')
        data = [{'id': c.id, 'name': c.name or c.email or 'Contacto',
                 'email': c.email or '', 'nivel': c.certum_nivel or 0}
                for c in contactos]
        return json_r({'ok': True, 'company': company.name, 'contactos': data})

    @http.route('/my/certum/admin/nivel', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def admin_set_nivel(self, partner_id=None, nivel=None, **post):
        """Fija el nivel jerárquico de un contacto-persona (1 = máximo)."""
        if not _es_interno():
            return json_err('Solo personal interno.', 403)
        try:
            pid = int(partner_id)
            niv = int(nivel)
        except (TypeError, ValueError):
            return json_err('Datos no válidos.', 400)
        if niv < 0 or niv > 20:
            return json_err('El nivel debe estar entre 0 y 20.', 400)
        contacto = request.env['res.partner'].sudo().browse(pid)
        if not contacto.exists() or contacto.is_company:
            return json_err('Contacto no válido.', 400)
        contacto.write({'certum_nivel': niv})
        _logger.info('[AUDIT] admin_set_nivel user=%s contacto=%s nivel=%s',
                     request.env.user.id, pid, niv)
        return json_r({'ok': True, 'partner_id': pid, 'nivel': niv})
