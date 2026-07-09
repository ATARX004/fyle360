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
    # Nivel jerárquico de un contacto-PERSONA dentro de su empresa
    # (1 = máxima jerarquía). 0 = sin nivel asignado. Aplica a personal de
    # cliente y de proveedor; rige la aprobación por capas y las autorizaciones.
    certum_nivel = fields.Integer(
        string='Nivel Certum', default=0,
        help='Nivel jerárquico dentro de la empresa (1 = máximo). Se asigna '
             'desde el panel de Roles.')
