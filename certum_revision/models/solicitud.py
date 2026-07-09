# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CertumRevSolicitud(models.Model):
    """Solicitud de ampliación del plazo general del proceso, pedida por el
    cliente. Enrutamiento por jerarquía:
      - la pide el nivel 1 (máximo) → va directo al proveedor;
      - la pide un nivel inferior → sube autorizándose nivel a nivel hasta el 1,
        y recién entonces pasa al proveedor.
    El proveedor aprueba/rechaza; si aprueba, se amplía plazo_dias del proceso.
    """
    _name = 'certum.rev.solicitud'
    _description = 'Solicitud de ampliación de plazo'
    _order = 'create_date desc, id desc'

    proceso_id = fields.Many2one('certum.rev.proceso', required=True,
                                 ondelete='cascade', index=True)
    solicitante_id = fields.Many2one('res.partner', string='Solicitante',
                                     required=True)
    solicitante_nivel = fields.Integer(string='Nivel del solicitante')
    dias_pedidos = fields.Integer(string='Días solicitados', required=True)
    motivo = fields.Text()
    estado = fields.Selection([
        ('pendiente_autorizacion', 'Pendiente de autorización interna'),
        ('pendiente_proveedor', 'Pendiente del proveedor'),
        ('aprobada', 'Aprobada'),
        ('rechazada', 'Rechazada'),
    ], default='pendiente_autorizacion', required=True, copy=False)
    # Nivel del cliente que debe autorizar ahora (mientras sube la cadena).
    # 0 cuando ya está en manos del proveedor o resuelta.
    autorizador_nivel = fields.Integer(string='Nivel que debe autorizar')
    resuelto_por_id = fields.Many2one('res.partner', string='Resuelto por')
    fecha_resolucion = fields.Datetime(readonly=True, copy=False)

    @api.constrains('dias_pedidos')
    def _check_dias(self):
        for s in self:
            if s.dias_pedidos <= 0 or s.dias_pedidos > 365:
                raise UserError(_('Los días solicitados deben estar entre 1 y 365.'))

    # ── API de negocio (los controllers validan rol/propiedad) ──────────
    def autorizar(self, partner, nivel):
        """Un nivel superior del cliente autoriza y la solicitud sube un peldaño.
        Al llegar al nivel 1, pasa al proveedor."""
        self.ensure_one()
        if self.estado != 'pendiente_autorizacion':
            raise UserError(_('La solicitud no está pendiente de autorización.'))
        if nivel >= self.autorizador_nivel and self.autorizador_nivel > 1:
            # Todavía no es el nivel más alto: sube al siguiente (nivel-1).
            self.autorizador_nivel = self.autorizador_nivel - 1
        else:
            # Autorizada por el nivel 1 (o superior) → al proveedor.
            self.write({'estado': 'pendiente_proveedor', 'autorizador_nivel': 0})
        _logger.info('[AUDIT] solicitud_autorizar user=%s solicitud=%s nivel=%s '
                     'estado=%s', self.env.user.id, self.id, nivel, self.estado)

    def aprobar_proveedor(self, partner):
        """El proveedor aprueba → se amplía el plazo del proceso."""
        self.ensure_one()
        if self.estado != 'pendiente_proveedor':
            raise UserError(_('La solicitud no está pendiente del proveedor.'))
        self.proceso_id.sudo().write({
            'plazo_dias': min(self.proceso_id._MAX_PLAZO_DIAS,
                              (self.proceso_id.plazo_dias or 0) + self.dias_pedidos),
        })
        self.write({
            'estado': 'aprobada',
            'resuelto_por_id': partner.id,
            'fecha_resolucion': fields.Datetime.now(),
        })
        _logger.info('[AUDIT] solicitud_aprobar_proveedor user=%s solicitud=%s '
                     'dias=%s', self.env.user.id, self.id, self.dias_pedidos)

    def rechazar(self, partner):
        self.ensure_one()
        if self.estado in ('aprobada', 'rechazada'):
            raise UserError(_('La solicitud ya fue resuelta.'))
        self.write({
            'estado': 'rechazada',
            'resuelto_por_id': partner.id,
            'fecha_resolucion': fields.Datetime.now(),
            'autorizador_nivel': 0,
        })
        _logger.info('[AUDIT] solicitud_rechazar user=%s solicitud=%s',
                     self.env.user.id, self.id)
