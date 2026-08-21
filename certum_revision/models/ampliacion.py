# -*- coding: utf-8 -*-
"""Ampliación de la VENTANA DE REVISIÓN de un documento.

No confundir con `certum.rev.solicitud`, que amplía el PLAZO GENERAL del
expediente. Aquí el que necesita más tiempo es un revisor del cliente para un
documento concreto.

**Quien concede es el PROVEEDOR**, igual que es él quien fija los días de
revisión al publicar. Si concediera el propio cliente, se estaría dando tiempo
a sí mismo sin contrapeso y el plazo dejaría de significar nada.

Dos caminos, ambos previstos:
  - El revisor **pide** días y el proveedor concede o rechaza.
  - El proveedor **concede** días por iniciativa propia, sin que nadie pida
    nada (por ejemplo, si sabe que envió el documento tarde).

En los dos casos el tope sigue siendo el plazo general del expediente: la
revisión de un documento nunca puede sobrevivir al expediente que la contiene.
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_DIAS_AMPLIACION = 60


class CertumRevAmpliacion(models.Model):
    _name = 'certum.rev.ampliacion'
    _description = 'Ampliación de la ventana de revisión de un ítem'
    _order = 'create_date desc, id desc'

    item_id = fields.Many2one('certum.rev.item', required=True,
                              ondelete='cascade', index=True)
    proceso_id = fields.Many2one(related='item_id.proceso_id', store=True)
    # Vacío cuando la concede el proveedor sin que nadie la haya pedido.
    solicitante_id = fields.Many2one('res.partner', string='Solicitante')
    dias_pedidos = fields.Integer(string='Días solicitados')
    dias_concedidos = fields.Integer(string='Días concedidos')
    motivo = fields.Text()
    estado = fields.Selection([
        ('pendiente', 'Pendiente del proveedor'),
        ('concedida', 'Concedida'),
        ('rechazada', 'Rechazada'),
    ], default='pendiente', required=True, copy=False)
    resuelto_por_id = fields.Many2one('res.partner', string='Resuelta por')
    fecha_resolucion = fields.Datetime(readonly=True, copy=False)
    # Se guarda el límite resultante para poder auditar qué se concedió.
    limite_resultante = fields.Datetime(readonly=True, copy=False)

    @api.constrains('dias_pedidos', 'dias_concedidos')
    def _check_dias(self):
        for a in self:
            for valor in (a.dias_pedidos, a.dias_concedidos):
                if valor and (valor < 0 or valor > MAX_DIAS_AMPLIACION):
                    raise UserError(_(
                        'Los días deben estar entre 1 y %s.',
                        MAX_DIAS_AMPLIACION))

    # ── API de negocio (los controllers validan rol y nivel) ───────────
    def conceder(self, dias, partner):
        """Concede `dias` y empuja la fecha límite de revisión del ítem."""
        self.ensure_one()
        if self.estado != 'pendiente':
            raise UserError(_('Esta solicitud ya fue resuelta.'))
        limite = self.item_id.ampliar_revision(dias, partner, lado='proveedor')
        self.write({
            'estado': 'concedida',
            'dias_concedidos': dias,
            'resuelto_por_id': partner.id,
            'fecha_resolucion': fields.Datetime.now(),
            'limite_resultante': limite,
        })
        _logger.info('[AUDIT] ampliacion_conceder user=%s ampliacion=%s item=%s '
                     'dias=%s', self.env.user.id, self.id, self.item_id.id, dias)
        return limite

    def rechazar(self, partner):
        self.ensure_one()
        if self.estado != 'pendiente':
            raise UserError(_('Esta solicitud ya fue resuelta.'))
        self.write({
            'estado': 'rechazada',
            'resuelto_por_id': partner.id,
            'fecha_resolucion': fields.Datetime.now(),
        })
        _logger.info('[AUDIT] ampliacion_rechazar user=%s ampliacion=%s',
                     self.env.user.id, self.id)
