# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    rol_en_certum = fields.Selection(
        selection=[
            ('proveedor', 'Proveedor'),
            ('cliente', 'Cliente'),
            ('interno', 'Interno'),
        ],
        string='Rol en Certum Global',
        help='Rol de la empresa dentro del flujo de revisión y aceptación. '
             'Se resuelve siempre sobre el commercial_partner_id.',
    )
    # Clientes que un PROVEEDOR puede seleccionar al iniciar un proceso.
    # Lo asigna Certum interno desde el panel de Roles; si está vacío, el
    # proveedor no ve ningún cliente (evita mostrarle todos los del sistema).
    certum_cliente_ids = fields.Many2many(
        'res.partner', 'certum_proveedor_cliente_rel',
        'proveedor_id', 'cliente_id',
        string='Clientes asignados',
        domain="[('is_company', '=', True)]",
        help='Compañías cliente que este proveedor puede elegir al iniciar '
             'procesos de revisión.',
    )
