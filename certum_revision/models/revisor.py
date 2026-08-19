# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CertumRevRevisor(models.Model):
    """Cadena de revisión por PERSONAS concretas, en orden.

    Se usa en dos alturas, con la misma estructura:
      - `proceso_id`: los participantes del proceso. Es la cadena por defecto
        de todos sus ítems y la fija el nivel 1 del cliente al configurar la
        política en modo 'personas'.
      - `item_id`: excepción para UN requisito concreto (p. ej. el médico
        ocupacional para los exámenes médicos). Manda sobre la del proceso.

    En ambos casos la ÚLTIMA persona de la lista es la máxima autoridad.
    """
    _name = 'certum.rev.revisor'
    _description = 'Revisor de la cadena de revisión'
    _order = 'sequence, id'

    item_id = fields.Many2one('certum.rev.item', ondelete='cascade', index=True)
    proceso_id = fields.Many2one('certum.rev.proceso', ondelete='cascade',
                                 index=True)
    partner_id = fields.Many2one('res.partner', string='Revisor', required=True)
    sequence = fields.Integer(default=10)

    @api.constrains('item_id', 'proceso_id')
    def _check_destino(self):
        """Cada revisor cuelga de un ítem O de un proceso, nunca de ambos."""
        for rec in self:
            if bool(rec.item_id) == bool(rec.proceso_id):
                raise ValidationError(_(
                    'Un revisor debe pertenecer a un ítem o a un proceso, '
                    'pero no a ambos ni a ninguno.'))
