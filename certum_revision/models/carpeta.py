# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CertumRevCarpeta(models.Model):
    _name = 'certum.rev.carpeta'
    _description = 'Carpeta del proceso de revisión'
    _order = 'sequence, id'

    proceso_id = fields.Many2one('certum.rev.proceso', required=True,
                                 ondelete='cascade')
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    item_ids = fields.One2many('certum.rev.item', 'carpeta_id', string='Ítems')
    items_aprobados = fields.Integer(compute='_compute_stats')
    total_items = fields.Integer(compute='_compute_stats')

    @api.depends('item_ids.state')
    def _compute_stats(self):
        for rec in self:
            rec.total_items = len(rec.item_ids)
            rec.items_aprobados = len(
                rec.item_ids.filtered(lambda i: i.state == 'aprobado'))
