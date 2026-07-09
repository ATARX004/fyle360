# -*- coding: utf-8 -*-
"""Crons del flujo de revisión: apertura automática y control de plazo.

AbstractModel + <ir.cron> en data/cron.xml (patrón de la skill). No importa
el controller; las duraciones se leen de ir.config_parameter igual que en
certum.rev.proceso.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

from .proceso import DEFAULT_DIAS_APERTURA
from .tz_utils import today_lima

_logger = logging.getLogger(__name__)


class CertumRevAuto(models.AbstractModel):
    _name = 'certum.rev.auto'
    _description = 'Automatizaciones del flujo de revisión'

    @api.model
    def cron_abrir_procesos(self):
        """Abre procesos en borrador cuando falta <= N días para el vencimiento."""
        Proceso = self.env['certum.rev.proceso'].sudo()
        dias = Proceso._param_int('certum_revision.dias_apertura',
                                  DEFAULT_DIAS_APERTURA)
        umbral = today_lima() + timedelta(days=dias)
        pendientes = Proceso.search([
            ('state', '=', 'borrador'),
            ('fecha_vencimiento', '!=', False),
            ('fecha_vencimiento', '<=', umbral),
        ])
        for proc in pendientes:
            try:
                proc.action_abrir()
                _logger.info('[AUDIT] cron_abrir proceso=%s', proc.id)
            except Exception:
                _logger.exception('cron_abrir_procesos: fallo proceso=%s', proc.id)

    @api.model
    def cron_control_plazo(self):
        """Marca fuera de plazo los procesos activos cuyo límite ya pasó."""
        Proceso = self.env['certum.rev.proceso'].sudo()
        activos = Proceso.search([('state', 'in', ('publicacion', 'revision'))])
        for proc in activos:
            if proc.fase == 'vencida':
                proc.action_marcar_fuera_plazo()
                _logger.info('[AUDIT] cron_fuera_plazo proceso=%s', proc.id)

    @api.model
    def cron_auto_aprobar_revision(self):
        """Ítems publicados cuya ventana de revisión venció sin que el cliente
        revise → se aprueban automáticamente (feature C)."""
        Item = self.env['certum.rev.item'].sudo()
        ahora = fields.Datetime.now()
        vencidos = Item.search([
            ('state', '=', 'publicado'),
            ('fecha_limite_revision', '!=', False),
            ('fecha_limite_revision', '<=', ahora),
            ('proceso_id.state', 'in', ('publicacion', 'revision')),
        ])
        for item in vencidos:
            try:
                item.auto_aprobar_por_vencimiento()
                _logger.info('[AUDIT] cron_auto_aprobar item=%s', item.id)
            except Exception:
                _logger.exception('cron_auto_aprobar_revision: fallo item=%s', item.id)
