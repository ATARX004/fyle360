# -*- coding: utf-8 -*-
from odoo import fields, models


class CertumRevComment(models.Model):
    _name = 'certum.rev.comment'
    _description = 'Comentario del hilo de revisión de un ítem'
    _order = 'create_date asc, id asc'

    item_id = fields.Many2one('certum.rev.item', required=True,
                              ondelete='cascade')
    author_id = fields.Many2one('res.partner', string='Autor', required=True)
    rol = fields.Selection([
        ('proveedor', 'Proveedor'),
        ('cliente', 'Cliente'),
        ('interno', 'Interno'),
    ], required=True)
    body = fields.Text(required=True)
