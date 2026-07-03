# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CertumRevChecklist(models.Model):
    _name = 'certum.rev.checklist'
    _description = 'Checklist maestro de revisión'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(string='Código', required=True, copy=False)
    active = fields.Boolean(default=True)
    sector = fields.Char(string='Sector / rubro',
                         help='Opcional: sector al que aplica esta plantilla.')
    description = fields.Text()
    folder_ids = fields.One2many('certum.rev.checklist.folder', 'checklist_id',
                                 string='Carpetas')
    item_ids = fields.One2many('certum.rev.checklist.item', 'checklist_id',
                               string='Ítems')
    item_count = fields.Integer(compute='_compute_item_count')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'El código del checklist debe ser único.'),
    ]

    @api.depends('item_ids')
    def _compute_item_count(self):
        for rec in self:
            rec.item_count = len(rec.item_ids)


class CertumRevChecklistFolder(models.Model):
    _name = 'certum.rev.checklist.folder'
    _description = 'Carpeta del checklist maestro'
    _order = 'sequence, id'

    checklist_id = fields.Many2one('certum.rev.checklist', required=True,
                                   ondelete='cascade')
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    item_ids = fields.One2many('certum.rev.checklist.item', 'folder_id',
                               string='Ítems')


class CertumRevChecklistItem(models.Model):
    _name = 'certum.rev.checklist.item'
    _description = 'Ítem del checklist maestro'
    _order = 'sequence, id'

    checklist_id = fields.Many2one('certum.rev.checklist', required=True,
                                   ondelete='cascade')
    folder_id = fields.Many2one('certum.rev.checklist.folder',
                                string='Carpeta', ondelete='set null',
                                domain="[('checklist_id', '=', checklist_id)]")
    name = fields.Char(required=True)
    description = fields.Text(help='Qué se espera exactamente de este documento.')
    required = fields.Boolean(string='Obligatorio', default=True)
    sequence = fields.Integer(default=10)
    # Gancho para el Módulo 2 (generador de documentos). Char para no
    # depender de un modelo que todavía no existe.
    doc_template_code = fields.Char(
        string='Ref. plantilla (Módulo 2)',
        help='Código de la plantilla del generador de documentos que '
             'pre-armará este ítem cuando el Módulo 2 esté disponible.')
