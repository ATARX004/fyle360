# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .checklist import MAX_PROFUNDIDAD


class CertumRevCarpeta(models.Model):
    """Carpeta del expediente. Copia del árbol de carpetas de la plantilla,
    con la misma estructura anidada."""
    _name = 'certum.rev.carpeta'
    _description = 'Carpeta del proceso de revisión'
    _order = 'sequence, id'
    _parent_name = 'parent_id'
    _parent_store = True

    proceso_id = fields.Many2one('certum.rev.proceso', required=True,
                                 ondelete='cascade')
    # De qué carpeta de la plantilla salió esta. Vacío = creada después de
    # abrir el expediente. Sirve para comparar la estructura con la original.
    origen_id = fields.Many2one('certum.rev.checklist.folder',
                                string='Carpeta de origen', ondelete='set null',
                                copy=False)
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    item_ids = fields.One2many('certum.rev.item', 'carpeta_id', string='Ítems')

    # ── Árbol ─────────────────────────────────────────────────────────
    parent_id = fields.Many2one('certum.rev.carpeta', string='Carpeta padre',
                                ondelete='cascade', index=True)
    child_ids = fields.One2many('certum.rev.carpeta', 'parent_id',
                                string='Subcarpetas')
    parent_path = fields.Char(index=True, unaccent=False)
    nivel = fields.Integer(compute='_compute_ruta', string='Profundidad')
    ruta = fields.Char(compute='_compute_ruta', string='Ruta completa')
    raiz_id = fields.Many2one('certum.rev.carpeta', compute='_compute_ruta',
                              string='Carpeta raíz')

    # Estadísticas: incluyen las subcarpetas, para que una carpeta padre
    # refleje el avance real de todo lo que cuelga de ella.
    items_aprobados = fields.Integer(compute='_compute_stats')
    total_items = fields.Integer(compute='_compute_stats')

    @api.depends('name', 'parent_id.ruta')
    def _compute_ruta(self):
        for rec in self:
            partes, cur, guard = [], rec, 0
            raiz = rec
            while cur and guard <= MAX_PROFUNDIDAD + 2:
                partes.append(cur.name or '')
                raiz = cur
                cur = cur.parent_id
                guard += 1
            rec.ruta = ' / '.join(reversed(partes))
            rec.nivel = len(partes) - 1
            rec.raiz_id = raiz

    @api.constrains('parent_id')
    def _check_arbol(self):
        for rec in self:
            if not rec._check_recursion():
                raise ValidationError(_('Una carpeta no puede colgar de sí misma.'))
            if rec.parent_id and rec.parent_id.proceso_id != rec.proceso_id:
                raise ValidationError(_(
                    'La carpeta padre debe pertenecer al mismo proceso.'))

    def _descendientes(self):
        """La carpeta y todo lo que cuelga de ella."""
        return self.search([('id', 'child_of', self.ids)]) if self else self

    @api.depends('item_ids.state', 'child_ids.total_items',
                 'child_ids.items_aprobados')
    def _compute_stats(self):
        for rec in self:
            items = rec._descendientes().mapped('item_ids')
            rec.total_items = len(items)
            rec.items_aprobados = len(
                items.filtered(lambda i: i.state == 'aprobado'))
