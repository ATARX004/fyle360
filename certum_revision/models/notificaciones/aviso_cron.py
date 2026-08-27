# -*- coding: utf-8 -*-
"""Avisos que dispara el reloj, no una acción de una persona.

Cubren el hueco más importante que tenía el sistema: hasta ahora **nadie
avisaba antes de que venciera una revisión**, y el documento se aprobaba solo
en silencio. El cliente se enteraba cuando ya no podía hacer nada.

Los tres avisos comparten forma: buscar lo que está a punto de vencer, agrupar
por destinatario y mandar **un solo correo**. Mandar uno por documento en un
proyecto de cuarenta requisitos es la manera más rápida de que el destinatario
cree una regla de filtrado y no vuelva a leer ninguno.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

from ..tz_utils import fmt_lima, today_lima

_logger = logging.getLogger(__name__)

TPL_PENDIENTES = 'certum_revision.template_pendientes_revision'
TPL_POR_VENCER = 'certum_revision.template_revision_por_vencer'
TPL_CORRECCION = 'certum_revision.template_correccion_por_vencer'


class CertumRevAvisoCron(models.AbstractModel):
    _name = 'certum.rev.aviso.cron'
    _description = 'Avisos por plazo (cron)'

    # ── Recordatorio diario de lo que falta por revisar ────────────────
    @api.model
    def cron_pendientes_revision(self):
        """Un correo al día por PROYECTO con lo que sigue esperando revisión.

        La clave de repetición lleva la fecha, así que se manda una vez al día
        aunque el cron corra varias veces; y no se manda nada si no hay nada
        pendiente, que es lo que evita el correo diario inútil.
        """
        aviso = self.env['certum.rev.aviso']
        hoy = today_lima().isoformat()
        Proceso = self.env['certum.rev.proceso'].sudo()
        for proc in Proceso.search([('state', '=', 'revision')]):
            pendientes = proc.item_ids.filtered(
                lambda i: i.state == 'publicado' and i.fecha_limite_revision)
            if not pendientes:
                continue
            aviso.enviar(
                'pendientes_revision', proc, TPL_PENDIENTES,
                aviso.correos_empresa(proc.cliente_id),
                clave='dia-%s' % hoy,
                contexto={'certum_pendientes': self._resumen(pendientes)})

    # ── A punto de vencer ──────────────────────────────────────────────
    @api.model
    def cron_por_vencer(self):
        """Avisa N días antes de que venza una ventana de revisión o un plazo
        de corrección. N sale de los ajustes (`aviso_dias_preaviso`)."""
        aviso = self.env['certum.rev.aviso']
        cfg = self.env['certum.rev.aviso.config']
        Item = self.env['certum.rev.item'].sudo()
        ahora = fields.Datetime.now()
        tope = ahora + timedelta(days=cfg.dias_preaviso())

        # Revisión del cliente: si vence, el documento se aprueba SOLO.
        for it in Item.search([('state', '=', 'publicado'),
                               ('fecha_limite_revision', '!=', False),
                               ('fecha_limite_revision', '>', ahora),
                               ('fecha_limite_revision', '<=', tope)]):
            if it.proceso_id.state not in ('publicacion', 'revision'):
                continue
            aviso.enviar('revision_por_vencer', it, TPL_POR_VENCER,
                         aviso.correos_turno(it),
                         clave='lim-%s' % it.fecha_limite_revision)

        # Corrección del proveedor sobre un observado.
        for it in Item.search([('state', '=', 'observado'),
                               ('fecha_limite_correccion', '!=', False),
                               ('fecha_limite_correccion', '>', ahora),
                               ('fecha_limite_correccion', '<=', tope)]):
            if it.proceso_id.state not in ('publicacion', 'revision'):
                continue
            aviso.enviar('correccion_por_vencer', it, TPL_CORRECCION,
                         aviso.correos_empresa(it.proceso_id.proveedor_id),
                         clave='corr-%s' % it.fecha_limite_correccion)

    # ── Utilidades ─────────────────────────────────────────────────────
    @api.model
    def _resumen(self, items):
        """Lista para la plantilla: nombre, carpeta, a quién le toca y hasta
        cuándo. Ordenada por urgencia, que es como se lee."""
        salida = []
        for it in items.sorted('fecha_limite_revision'):
            cadena = it._cadena()
            paso = it.revision_paso or 0
            quien = ''
            if cadena and 1 <= paso <= len(cadena):
                pid = cadena[paso - 1].get('partner_id')
                quien = (self.env['res.partner'].sudo().browse(pid).display_name
                         if pid else 'Nivel %s' % cadena[paso - 1].get('nivel'))
            salida.append({
                'nombre': it.name,
                'carpeta': it.carpeta_id.ruta or it.carpeta_id.name or '',
                'quien': quien,
                'limite': fmt_lima(it.fecha_limite_revision, '%d/%m/%Y'),
            })
        return salida
