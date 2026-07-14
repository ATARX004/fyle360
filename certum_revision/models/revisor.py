# -*- coding: utf-8 -*-
from odoo import fields, models


class CertumRevRevisor(models.Model):
    """Cadena de revisión A MEDIDA de un ítem (feature 2). Cuando un ítem tiene
    revisores propios, estos reemplazan la cadena por niveles: la revisión pasa
    por estas personas en orden (la última es la máxima autoridad). Lo configura
    el nivel 1 del cliente desde el panel lateral del ítem."""
    _name = 'certum.rev.revisor'
    _description = 'Revisor a medida de un ítem'
    _order = 'sequence, id'

    item_id = fields.Many2one('certum.rev.item', required=True,
                              ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Revisor', required=True)
    sequence = fields.Integer(default=10)
