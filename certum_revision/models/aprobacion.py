# -*- coding: utf-8 -*-
from odoo import fields, models


class CertumRevAprobacion(models.Model):
    """Traza inmutable de cada acción de revisión sobre un ítem: quién, qué
    nivel, qué acción y CUÁNDO (fecha y hora). Es el registro de auditoría de
    negocio del flujo de aprobación por capas."""
    _name = 'certum.rev.aprobacion'
    _description = 'Traza de aprobación/observación de un ítem'
    _order = 'fecha desc, id desc'

    item_id = fields.Many2one('certum.rev.item', required=True,
                              ondelete='cascade', index=True)
    proceso_id = fields.Many2one(related='item_id.proceso_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Autor', required=True)
    user_id = fields.Many2one('res.users', string='Usuario')
    nivel = fields.Integer(string='Nivel', help='Nivel jerárquico con el que actuó (1 = máximo).')
    lado = fields.Selection([
        ('cliente', 'Cliente'),
        ('proveedor', 'Proveedor'),
        ('sistema', 'Sistema'),
    ], default='cliente')
    accion = fields.Selection([
        ('aprobado', 'Aprobado'),
        ('observado', 'Observado'),
        ('no_reviso', 'No revisó a tiempo'),
        ('auto_aprobado', 'Aprobado por vencimiento'),
        ('ampliacion', 'Ampliación de la ventana de revisión'),
        ('reanudado', 'Revisión reanudada tras corregir'),
        ('revertido', 'Turno devuelto al revisor'),
    ], required=True)
    fecha = fields.Datetime(required=True, default=fields.Datetime.now)
    comentario = fields.Text()

    def _label(self):
        self.ensure_one()
        etiquetas = dict(self._fields['accion'].selection)
        return etiquetas.get(self.accion, self.accion)
