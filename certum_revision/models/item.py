# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta

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

DEFAULT_DIAS_CORRECCION = 3   # días extra al proveedor tras una observación


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
    # Archivos que el CLIENTE adjunta al observar (documento con sus marcas).
    attachment_cliente_ids = fields.Many2many(
        'ir.attachment', 'certum_rev_item_att_cliente_rel',
        'item_id', 'attachment_id', string='Adjuntos del cliente')
    fecha_publicacion = fields.Datetime(readonly=True, copy=False)
    fecha_revision = fields.Datetime(readonly=True, copy=False)
    comment_ids = fields.One2many('certum.rev.comment', 'item_id',
                                  string='Comentarios')
    aprobacion_ids = fields.One2many('certum.rev.aprobacion', 'item_id',
                                     string='Trazabilidad')
    doc_template_code = fields.Char(string='Ref. plantilla (Módulo 2)')

    # ── Ventana de revisión y ciclo de corrección (feature C) ──────────
    dias_revision = fields.Integer(
        string='Días de revisión', copy=False,
        help='Días que el proveedor otorgó al cliente para revisar desde la '
             'publicación. Al vencer sin revisión, el ítem se auto-aprueba.')
    fecha_limite_revision = fields.Datetime(readonly=True, copy=False,
                                            string='Límite de revisión')
    fecha_limite_correccion = fields.Datetime(readonly=True, copy=False,
                                              string='Límite de corrección')
    # ── Aprobación por capas (feature A) ───────────────────────────────
    revision_nivel = fields.Integer(
        string='Nivel en revisión', copy=False,
        help='En modo secuencial, nivel del cliente que debe revisar ahora '
             '(cuenta hacia el 1). 0 = modo cualquiera o fuera de revisión.')

    proveedor_id = fields.Many2one(related='proceso_id.proveedor_id', store=True)
    cliente_id = fields.Many2one(related='proceso_id.cliente_id', store=True)

    # ─────────────────────────────────────────────────────────────────
    @api.model
    def _dias_correccion(self):
        icp = self.env['ir.config_parameter'].sudo()
        try:
            return int(icp.get_param('certum_revision.dias_correccion',
                                     DEFAULT_DIAS_CORRECCION))
        except (TypeError, ValueError):
            return DEFAULT_DIAS_CORRECCION

    def _tope_proceso(self):
        """Datetime tope = fin del plazo general del proceso (no se puede
        revisar más allá). None si el proceso no tiene fecha límite."""
        self.ensure_one()
        limite = self.proceso_id.fecha_limite  # Date
        if not limite:
            return None
        return datetime.combine(limite, datetime.max.time())

    def _registrar(self, accion, partner=None, nivel=0, lado='cliente',
                   comentario=None):
        self.ensure_one()
        self.env['certum.rev.aprobacion'].sudo().create({
            'item_id': self.id,
            'partner_id': (partner and partner.id) or self.env.user.partner_id.id,
            'user_id': self.env.user.id,
            'nivel': nivel,
            'lado': lado,
            'accion': accion,
            'fecha': fields.Datetime.now(),
            'comentario': comentario or False,
        })

    # ── Transiciones ───────────────────────────────────────────────────
    def _assert_proceso_activo(self):
        self.ensure_one()
        if self.proceso_id.state not in ('publicacion', 'revision'):
            raise UserError(_('El proceso no está activo.'))

    def _dias_por_nivel(self, nivel):
        """Días asignados a un nivel: reparto EQUITATIVO de dias_revision entre
        las capas; el remanente (días enteros) va a la mayor jerarquía
        (niveles 1..rem). Ej.: 10 días / 3 capas → nivel1=4, nivel2=3, nivel3=3."""
        self.ensure_one()
        capas = max(1, self.proceso_id.revision_capas or 1)
        base, rem = divmod(self.dias_revision or 0, capas)
        return base + (1 if nivel <= rem else 0)

    def _set_ventana_actual(self):
        """Fija la fecha límite del nivel actual (secuencial). Si un nivel no
        tiene días asignados (reparto insuficiente), lo salta registrando la
        traza y avanza; si nadie con días llega hasta el 1, auto-aprueba."""
        self.ensure_one()
        for _guard in range(100):
            nivel = self.revision_nivel or 1
            dias = self._dias_por_nivel(nivel)
            if dias > 0:
                limite = fields.Datetime.now() + timedelta(days=dias)
                tope = self._tope_proceso()
                if tope and limite > tope:
                    limite = tope
                self.fecha_limite_revision = limite
                return
            # Nivel sin días en el reparto → se registra y se pasa al siguiente.
            self._registrar('no_reviso', nivel=nivel, lado='sistema',
                            comentario='Sin días asignados en el reparto; pasa al siguiente nivel.')
            if nivel <= 1:
                self._aprobar_final(auto=True)
                return
            self.revision_nivel = nivel - 1

    def _aprobar_final(self, auto=False):
        """Cierra la aprobación del ítem (última capa cubierta o auto)."""
        self.write({
            'state': 'aprobado',
            'revision_nivel': 0,
            'fecha_revision': fields.Datetime.now(),
        })
        if auto:
            self._registrar('auto_aprobado', nivel=0, lado='sistema',
                            comentario='Aprobado automáticamente por vencimiento del plazo de revisión.')
        _logger.info('[AUDIT] item_aprobado_final item=%s auto=%s', self.id, auto)
        self.proceso_id._check_completado()
        notify_aprobado(self)

    def marcar_publicado(self, attachment, dias_revision=None):
        """El proveedor publica (o corrige) el documento del ítem y abre la
        ventana de revisión del cliente."""
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state == 'aprobado':
            raise UserError(_('Este ítem ya fue aprobado.'))

        # Días de revisión: se fijan en la primera publicación; en las
        # correcciones se reutiliza el valor ya guardado.
        if dias_revision and not self.dias_revision:
            self.dias_revision = max(1, min(365, int(dias_revision)))
        dias = self.dias_revision or 0
        ahora = fields.Datetime.now()
        secuencial = self.proceso_id.revision_modo == 'secuencial'

        self.write({
            'state': 'publicado',
            'fecha_publicacion': ahora,
            'fecha_limite_revision': False,
            'fecha_limite_correccion': False,
            'revision_nivel': max(1, self.proceso_id.revision_capas or 1) if secuencial else 0,
            'attachment_ids': [(4, attachment.id)],
            'attachment_final_id': attachment.id,
        })
        if self.proceso_id.state == 'publicacion':
            self.proceso_id.state = 'revision'

        if secuencial:
            # Reparte los días por nivel y abre la ventana del primero.
            self._set_ventana_actual()
        elif dias:
            limite = ahora + timedelta(days=dias)
            tope = self._tope_proceso()
            if tope and limite > tope:
                limite = tope
            self.fecha_limite_revision = limite

        _logger.info('[AUDIT] item_publicar user=%s item=%s att=%s dias_rev=%s',
                     self.env.user.id, self.id, attachment.id, dias)
        if self.state == 'publicado':  # pudo auto-aprobarse si el reparto era 0
            notify_publicado(self)

    def puede_aprobar_nivel(self, nivel):
        """¿Un revisor de `nivel` puede aprobar/observar ahora este ítem?"""
        self.ensure_one()
        if self.state != 'publicado':
            return False
        if self.proceso_id.revision_modo != 'secuencial':
            return True  # cualquiera aprueba
        return nivel and nivel == self.revision_nivel

    def marcar_aprobado(self, partner=None, nivel=0, lado='cliente'):
        """Aprueba la capa actual. En secuencial avanza al nivel superior;
        al cubrir el nivel 1 el ítem queda aprobado."""
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state != 'publicado':
            raise UserError(_('Solo se puede aprobar un ítem publicado.'))

        self._registrar('aprobado', partner=partner, nivel=nivel, lado=lado)

        secuencial = self.proceso_id.revision_modo == 'secuencial'
        if secuencial and (self.revision_nivel or 0) > 1:
            # Aún faltan capas: sube al siguiente nivel y abre su ventana.
            self.write({
                'revision_nivel': self.revision_nivel - 1,
                'fecha_revision': fields.Datetime.now(),
            })
            self._set_ventana_actual()
            _logger.info('[AUDIT] item_aprobar_capa user=%s item=%s nivel=%s '
                         'siguiente=%s', self.env.user.id, self.id, nivel,
                         self.revision_nivel)
            return False  # aún no aprobado del todo

        # Cualquiera, o secuencial en el nivel 1: aprobado definitivo.
        self.write({'fecha_revision': fields.Datetime.now()})
        self._aprobar_final(auto=False)
        _logger.info('[AUDIT] item_aprobar user=%s item=%s nivel=%s',
                     self.env.user.id, self.id, nivel)
        return True

    def marcar_observado(self, partner=None, nivel=0, comentario=None,
                         attachment=None, lado='cliente'):
        """Observa el ítem: vuelve al proveedor con +N días de corrección."""
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state != 'publicado':
            raise UserError(_('Solo se puede observar un ítem publicado.'))

        self._registrar('observado', partner=partner, nivel=nivel, lado=lado,
                        comentario=comentario)
        ahora = fields.Datetime.now()
        limite_corr = ahora + timedelta(days=self._dias_correccion())
        tope = self._tope_proceso()
        if tope and limite_corr > tope:
            limite_corr = tope
        vals = {
            'state': 'observado',
            'revision_nivel': 0,
            'fecha_revision': ahora,
            'fecha_limite_correccion': limite_corr,
        }
        if attachment:
            vals['attachment_cliente_ids'] = [(4, attachment.id)]
        self.write(vals)
        _logger.info('[AUDIT] item_observar user=%s item=%s nivel=%s',
                     self.env.user.id, self.id, nivel)
        notify_observado(self)

    def procesar_vencimiento_revision(self):
        """Cron: venció la ventana del nivel actual sin revisión.
        - Modo secuencial: se registra que ese nivel NO revisó y pasa al
          siguiente (hacia el 1); si el nivel 1 tampoco revisa → auto-aprobado.
        - Modo cualquiera: si nadie revisó en el plazo → auto-aprobado."""
        self.ensure_one()
        if self.state != 'publicado':
            return
        if self.proceso_id.revision_modo != 'secuencial':
            self._aprobar_final(auto=True)
            _logger.info('[AUDIT] item_auto_aprobar item=%s', self.id)
            return

        nivel = self.revision_nivel or 1
        # Trazabilidad: queda registrado que ESTE nivel no revisó a tiempo.
        self._registrar('no_reviso', nivel=nivel, lado='sistema',
                        comentario='No revisó dentro de su plazo; pasa al siguiente nivel.')
        _logger.info('[AUDIT] item_no_reviso item=%s nivel=%s', self.id, nivel)
        if nivel <= 1:
            # El nivel más alto tampoco revisó → aprobado automático.
            self._aprobar_final(auto=True)
            return
        self.revision_nivel = nivel - 1
        self._set_ventana_actual()

    @api.depends('name', 'proceso_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.proceso_id.name or ""} · {rec.name}'
