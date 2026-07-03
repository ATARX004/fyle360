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
