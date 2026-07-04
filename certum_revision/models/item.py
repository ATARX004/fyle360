# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .notify import notify_aprobado, notify_observado, notify_publicado

_logger = logging.getLogger(__name__)

ITEM_STATES = [
    ('pendiente', 'Pendiente'),
    ('publicado', 'Publicado'),
    ('observado', 'Observado'),
    ('aprobado', 'Aprobado'),
]


class CertumRevItem(models.Model):
    _name = 'certum.rev.item'
    _description = 'Ítem de revisión'
    _order = 'sequence, id'

    proceso_id = fields.Many2one('certum.rev.proceso', required=True,
                                 ondelete='cascade')
    carpeta_id = fields.Many2one('certum.rev.carpeta', string='Carpeta',
                                 ondelete='set null')
    name = fields.Char(required=True)
    description = fields.Text()
    required = fields.Boolean(string='Obligatorio', default=True)
    sequence = fields.Integer(default=10)
    state = fields.Selection(ITEM_STATES, default='pendiente', copy=False)

    attachment_ids = fields.Many2many(
        'ir.attachment', 'certum_rev_item_attachment_rel',
        'item_id', 'attachment_id', string='Documentos publicados',
        help='Historial de documentos publicados por el proveedor.')
    attachment_final_id = fields.Many2one(
        'ir.attachment', string='Documento vigente',
        help='El documento aprobado / última versión publicada.')
    fecha_publicacion = fields.Datetime(readonly=True, copy=False)
    fecha_revision = fields.Datetime(readonly=True, copy=False)
    comment_ids = fields.One2many('certum.rev.comment', 'item_id',
                                  string='Comentarios')
    doc_template_code = fields.Char(string='Ref. plantilla (Módulo 2)')

    proveedor_id = fields.Many2one(related='proceso_id.proveedor_id', store=True)
    cliente_id = fields.Many2one(related='proceso_id.cliente_id', store=True)

    # ── Transiciones (el controller valida rol/propiedad; aquí, estado) ──
    def _assert_proceso_activo(self):
        self.ensure_one()
        if self.proceso_id.state not in ('publicacion', 'revision'):
            raise UserError(_('El proceso no está activo.'))

    def marcar_publicado(self, attachment):
        """El proveedor publica (o corrige) el documento del ítem."""
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state == 'aprobado':
            raise UserError(_('Este ítem ya fue aprobado.'))
        # Datetime se guarda en UTC naive (convención Odoo); la TZ Lima
        # se usa solo para decisiones de negocio sobre fechas.
        self.write({
            'state': 'publicado',
            'fecha_publicacion': fields.Datetime.now(),
            'attachment_ids': [(4, attachment.id)],
            'attachment_final_id': attachment.id,
        })
        if self.proceso_id.state == 'publicacion':
            self.proceso_id.state = 'revision'
        _logger.info('[AUDIT] item_publicar user=%s item=%s att=%s',
                     self.env.user.id, self.id, attachment.id)
        notify_publicado(self)

    def marcar_aprobado(self):
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state != 'publicado':
            raise UserError(_('Solo se puede aprobar un ítem publicado.'))
        self.write({
            'state': 'aprobado',
            'fecha_revision': fields.Datetime.now(),
        })
        _logger.info('[AUDIT] item_aprobar user=%s item=%s',
                     self.env.user.id, self.id)
        self.proceso_id._check_completado()
        notify_aprobado(self)

    def marcar_observado(self):
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state != 'publicado':
            raise UserError(_('Solo se puede observar un ítem publicado.'))
        self.write({
            'state': 'observado',
            'fecha_revision': fields.Datetime.now(),
        })
        _logger.info('[AUDIT] item_observar user=%s item=%s',
                     self.env.user.id, self.id)
        notify_observado(self)

    @api.depends('name', 'proceso_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.proceso_id.name or ""} · {rec.name}'
