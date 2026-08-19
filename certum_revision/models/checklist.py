# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CertumRevChecklist(models.Model):
    _name = 'certum.rev.checklist'
    _description = 'Checklist maestro de revisión'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(string='Código', required=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code(
                           'certum.rev.checklist') or '/')
    active = fields.Boolean(default=True)
    sector = fields.Char(string='Sector / rubro',
                         help='Opcional: sector al que aplica esta plantilla.')
    description = fields.Text()
    # Dueño de la plantilla. El proveedor crea y administra las suyas desde el
    # portal web; vacío = plantilla global de Certum (interno).
    proveedor_id = fields.Many2one(
        'res.partner', string='Proveedor (dueño)', index=True,
        help='Empresa proveedora dueña de esta plantilla.')
    plazo_dias = fields.Integer(
        string='Plazo sugerido (días)', default=30,
        help='Días para publicar; se copia al proceso al iniciarlo.')
    folder_ids = fields.One2many('certum.rev.checklist.folder', 'checklist_id',
                                 string='Carpetas')
    item_ids = fields.One2many('certum.rev.checklist.item', 'checklist_id',
                               string='Ítems')
    item_count = fields.Integer(compute='_compute_item_count')
    folder_count = fields.Integer(compute='_compute_item_count')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'El código del checklist debe ser único.'),
    ]

    @api.depends('item_ids', 'folder_ids')
    def _compute_item_count(self):
        for rec in self:
            rec.item_count = len(rec.item_ids)
            rec.folder_count = len(rec.folder_ids)


# Profundidad máxima del árbol de carpetas. Acota la longitud de las rutas
# dentro del ZIP y mantiene el editor legible.
MAX_PROFUNDIDAD = 5


class CertumRevChecklistFolder(models.Model):
    _name = 'certum.rev.checklist.folder'
    _description = 'Carpeta del checklist maestro'
    _order = 'sequence, id'
    _parent_name = 'parent_id'
    _parent_store = True

    checklist_id = fields.Many2one('certum.rev.checklist', required=True,
                                   ondelete='cascade')
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    item_ids = fields.One2many('certum.rev.checklist.item', 'folder_id',
                               string='Ítems')
    # ── Árbol: una carpeta puede colgar de otra ───────────────────────
    parent_id = fields.Many2one(
        'certum.rev.checklist.folder', string='Carpeta padre',
        ondelete='cascade', index=True,
        domain="[('checklist_id', '=', checklist_id)]")
    child_ids = fields.One2many('certum.rev.checklist.folder', 'parent_id',
                                string='Subcarpetas')
    parent_path = fields.Char(index=True, unaccent=False)
    nivel = fields.Integer(compute='_compute_ruta', string='Profundidad')
    ruta = fields.Char(compute='_compute_ruta', string='Ruta completa')

    @api.depends('name', 'parent_id.ruta')
    def _compute_ruta(self):
        for rec in self:
            partes, cur, guard = [], rec, 0
            while cur and guard <= MAX_PROFUNDIDAD + 2:
                partes.append(cur.name or '')
                cur = cur.parent_id
                guard += 1
            rec.ruta = ' / '.join(reversed(partes))
            rec.nivel = len(partes) - 1

    @api.constrains('parent_id')
    def _check_arbol(self):
        for rec in self:
            if not rec._check_recursion():
                raise ValidationError(_('Una carpeta no puede colgar de sí misma.'))
            if rec.parent_id and rec.parent_id.checklist_id != rec.checklist_id:
                raise ValidationError(_(
                    'La carpeta padre debe pertenecer a la misma plantilla.'))
            if rec.nivel >= MAX_PROFUNDIDAD:
                raise ValidationError(_(
                    'No se pueden anidar más de %s niveles de carpetas.',
                    MAX_PROFUNDIDAD))


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
