# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .notify import notify_aprobado, notify_observado, notify_publicado
from .tz_utils import fin_de_dia_utc

_logger = logging.getLogger(__name__)

ITEM_STATES = [
    ('pendiente', 'Pendiente'),
    ('publicado', 'Publicado'),
    ('observado', 'Observado'),
    ('aprobado', 'Aprobado'),
]

DEFAULT_DIAS_CORRECCION = 3   # días extra al proveedor tras una observación
DEFAULT_DIAS_PURGA = 10       # días que sobreviven las versiones superadas


class CertumRevItem(models.Model):
    _name = 'certum.rev.item'
    _description = 'Ítem de revisión'
    _order = 'sequence, id'

    proceso_id = fields.Many2one('certum.rev.proceso', required=True,
                                 ondelete='cascade')
    carpeta_id = fields.Many2one('certum.rev.carpeta', string='Carpeta',
                                 ondelete='set null')
    # De qué ítem de la plantilla salió este. Vacío = añadido después de abrir.
    origen_id = fields.Many2one('certum.rev.checklist.item',
                                string='Ítem de origen', ondelete='set null',
                                copy=False)
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
    ampliacion_ids = fields.One2many('certum.rev.ampliacion', 'item_id',
                                     string='Ampliaciones de la revisión')
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
        help='Compat: nivel del paso actual en la cadena por niveles. 0 si el '
             'paso actual es una persona a medida o fuera de revisión.')
    # Cadena de revisores A MEDIDA (feature 2). Si tiene elementos, reemplaza la
    # cadena por niveles: la revisión pasa por estas personas en orden.
    revisor_ids = fields.One2many('certum.rev.revisor', 'item_id',
                                  string='Revisores a medida', copy=False)
    # True solo cuando el cliente configuró la cadena PARA ESTE ítem. Si la
    # cadena se heredó del proceso al publicar, queda en False: así la interfaz
    # distingue una excepción real de una copia de los participantes.
    revisores_propios = fields.Boolean(
        string='Cadena propia del ítem', default=False, copy=False)
    # Cursor unificado: paso actual (1-based) dentro de la cadena de revisión
    # (sea por niveles o a medida). 0 = modo cualquiera o fuera de revisión.
    revision_paso = fields.Integer(string='Paso de revisión', copy=False)

    proveedor_id = fields.Many2one(related='proceso_id.proveedor_id', store=True)
    cliente_id = fields.Many2one(related='proceso_id.cliente_id', store=True)

    # ─────────────────────────────────────────────────────────────────
    @api.model
    def _param_int_purga(self):
        """Días que se conservan las versiones superadas antes de depurarlas."""
        icp = self.env['ir.config_parameter'].sudo()
        try:
            return max(1, int(icp.get_param('certum_revision.dias_purga_versiones',
                                            DEFAULT_DIAS_PURGA)))
        except (TypeError, ValueError):
            return DEFAULT_DIAS_PURGA

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
        limite = self.proceso_id.fecha_limite  # Date (día de negocio, Lima)
        if not limite:
            return None
        # 23:59:59 DE LIMA convertido a UTC. Antes se combinaba con la hora
        # máxima y se guardaba tal cual, así que el plazo moría a las 18:59
        # hora de Lima.
        return fin_de_dia_utc(limite)

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

    def _cadena(self):
        """Lista ordenada de pasos de revisión. Cada paso es un dict
        {'partner_id': id|False, 'nivel': int}; el ÚLTIMO paso es la máxima
        autoridad. Vacía en modo 'cualquiera'.

        Precedencia, de mayor a menor:
          1. Cadena PROPIA del ítem (excepción para ese requisito).
          2. Participantes del PROCESO (modo 'personas'). Al publicar se
             congelan sobre el ítem, así que aquí solo se usan como vista
             previa mientras el ítem no se ha publicado.
          3. Capas por NIVEL (modo 'secuencial').
          4. Vacía → cualquiera del cliente aprueba.
        """
        self.ensure_one()
        proc = self.proceso_id
        if self.revisor_ids:
            return [{'partner_id': r.partner_id.id, 'nivel': 0}
                    for r in self.revisor_ids.sorted('sequence')]
        if proc.revision_modo == 'personas' and proc.revisor_ids:
            return [{'partner_id': r.partner_id.id, 'nivel': 0}
                    for r in proc.revisor_ids.sorted('sequence')]
        if proc.revision_modo == 'secuencial':
            capas = max(1, proc.revision_capas or 1)
            # Paso 1 = nivel más bajo (capas) … último = nivel 1 (top).
            return [{'partner_id': False, 'nivel': capas - i} for i in range(capas)]
        return []

    def _congelar_cadena_proceso(self):
        """Copia los participantes del proceso sobre el ítem al publicarlo.

        Congelar la cadena en el momento de publicar tiene dos efectos que
        interesan: la revisión en curso no cambia si después se editan los
        participantes del proceso, y queda registrado en el propio documento
        por quiénes debía pasar.
        """
        self.ensure_one()
        proc = self.proceso_id
        if self.revisor_ids or proc.revision_modo != 'personas':
            return
        Revisor = self.env['certum.rev.revisor'].sudo()
        for r in proc.revisor_ids.sorted('sequence'):
            Revisor.create({'item_id': self.id, 'partner_id': r.partner_id.id,
                            'sequence': r.sequence})
        if proc.revisor_ids:
            self.revisores_propios = False   # heredada, no es excepción
            self.invalidate_recordset(['revisor_ids'])

    def _dias_por_paso(self, paso, n):
        """Reparto EQUITATIVO de dias_revision entre n pasos; el remanente
        (días enteros) va a la MAYOR jerarquía (los ÚLTIMOS pasos de la cadena)."""
        self.ensure_one()
        if n <= 0:
            return 0
        base, rem = divmod(self.dias_revision or 0, n)
        return base + (1 if paso > n - rem else 0)

    def _registrar_no_reviso(self, step, motivo):
        self._registrar(
            'no_reviso',
            partner=(self.env['res.partner'].sudo().browse(step['partner_id'])
                     if step.get('partner_id') else None),
            nivel=step.get('nivel') or 0, lado='sistema', comentario=motivo)

    def _sync_nivel(self):
        """Compat/visualización: revision_nivel = nivel del paso actual (0 si es
        una persona a medida o fuera de revisión)."""
        cadena = self._cadena()
        paso = self.revision_paso or 0
        self.revision_nivel = (cadena[paso - 1]['nivel']
                               if 1 <= paso <= len(cadena) else 0)

    def _set_ventana_actual(self):
        """Fija la fecha límite del PASO actual. Salta pasos con 0 días
        (registrando 'no revisó'); si se pasa del final, auto-aprueba."""
        self.ensure_one()
        cadena = self._cadena()
        n = len(cadena)
        if n == 0:
            return  # modo cualquiera: ventana única (la fija marcar_publicado)
        for _guard in range(200):
            paso = self.revision_paso or 1
            if paso > n:
                self._aprobar_final(auto=True)
                return
            dias = self._dias_por_paso(paso, n)
            if dias > 0:
                limite = fields.Datetime.now() + timedelta(days=dias)
                tope = self._tope_proceso()
                if tope and limite > tope:
                    limite = tope
                self.fecha_limite_revision = limite
                self._sync_nivel()
                return
            self._registrar_no_reviso(
                cadena[paso - 1],
                'Sin días asignados en el reparto; pasa al siguiente revisor.')
            self.revision_paso = paso + 1

    def _aprobar_final(self, auto=False):
        """Cierra la aprobación del ítem (última capa cubierta o auto)."""
        self.write({
            'state': 'aprobado',
            'revision_nivel': 0,
            'revision_paso': 0,
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
        # Congela los participantes del proceso sobre el ítem ANTES de calcular
        # la cadena: a partir de aquí la revisión en curso es inmune a que se
        # editen los participantes del proceso.
        self._congelar_cadena_proceso()
        cadena = self._cadena()          # niveles o personas designadas
        chained = bool(cadena)

        self.write({
            'state': 'publicado',
            'fecha_publicacion': ahora,
            'fecha_limite_revision': False,
            'fecha_limite_correccion': False,
            'revision_paso': 1 if chained else 0,
            'revision_nivel': 0,
            'attachment_ids': [(4, attachment.id)],
            'attachment_final_id': attachment.id,
        })
        if self.proceso_id.state == 'publicacion':
            self.proceso_id.state = 'revision'

        if chained:
            # Reparte los días por paso y abre la ventana del primero.
            self._set_ventana_actual()
        elif dias:
            # Modo cualquiera: ventana única para todo el cliente.
            limite = ahora + timedelta(days=dias)
            tope = self._tope_proceso()
            if tope and limite > tope:
                limite = tope
            self.fecha_limite_revision = limite

        _logger.info('[AUDIT] item_publicar user=%s item=%s att=%s dias_rev=%s',
                     self.env.user.id, self.id, attachment.id, dias)
        if self.state == 'publicado':  # pudo auto-aprobarse si el reparto era 0
            notify_publicado(self)

    def ampliar_revision(self, dias, partner=None):
        """Empuja la fecha límite de revisión del PASO ACTUAL en `dias`.

        El tope sigue siendo el plazo general del expediente: una revisión no
        puede sobrevivir al expediente que la contiene. Si al recortar por ese
        tope no se gana ni un minuto, se avisa en vez de fingir que sí.
        """
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state != 'publicado':
            raise UserError(_('Solo se puede ampliar la ventana de un ítem '
                              'publicado y en revisión.'))
        try:
            dias = int(dias)
        except (TypeError, ValueError):
            dias = 0
        if dias <= 0:
            raise UserError(_('Indica cuántos días adicionales conceder.'))

        base = self.fecha_limite_revision or fields.Datetime.now()
        nuevo = base + timedelta(days=dias)
        tope = self._tope_proceso()
        if tope and nuevo > tope:
            nuevo = tope
        if self.fecha_limite_revision and nuevo <= self.fecha_limite_revision:
            raise UserError(_(
                'El plazo general del expediente vence antes: no se pueden '
                'añadir más días a esta revisión sin ampliar primero el '
                'expediente.'))

        self.fecha_limite_revision = nuevo
        self._registrar('ampliacion', partner=partner,
                        nivel=(partner.certum_nivel if partner else 0),
                        lado='cliente',
                        comentario=_('Ventana de revisión ampliada %s día(s).',
                                     dias))
        _logger.info('[AUDIT] item_ampliar_revision user=%s item=%s dias=%s',
                     self.env.user.id, self.id, dias)
        return nuevo

    def puede_revisar(self, partner, nivel):
        """¿Este usuario (partner + nivel) puede revisar el PASO actual?"""
        self.ensure_one()
        if self.state != 'publicado':
            return False
        cadena = self._cadena()
        if not cadena:
            return True  # modo cualquiera: cualquier contacto del cliente
        paso = self.revision_paso or 1
        if paso < 1 or paso > len(cadena):
            return False
        step = cadena[paso - 1]
        if step.get('partner_id'):
            return bool(partner) and partner.id == step['partner_id']
        return bool(nivel) and nivel == step.get('nivel')

    def marcar_aprobado(self, partner=None, nivel=0, lado='cliente'):
        """Aprueba el paso actual. Si quedan pasos, avanza al siguiente y abre
        su ventana; al cubrir el último (máxima autoridad) queda aprobado."""
        self.ensure_one()
        self._assert_proceso_activo()
        if self.state != 'publicado':
            raise UserError(_('Solo se puede aprobar un ítem publicado.'))

        self._registrar('aprobado', partner=partner, nivel=nivel, lado=lado)

        cadena = self._cadena()
        if cadena and (self.revision_paso or 1) < len(cadena):
            self.write({
                'revision_paso': (self.revision_paso or 1) + 1,
                'fecha_revision': fields.Datetime.now(),
            })
            self._set_ventana_actual()
            _logger.info('[AUDIT] item_aprobar_paso user=%s item=%s paso=%s',
                         self.env.user.id, self.id, self.revision_paso)
            return False  # aún no aprobado del todo

        # Modo cualquiera, o último paso de la cadena: aprobado definitivo.
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
            'revision_paso': 0,
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
        """Cron: venció la ventana del PASO actual sin revisión.
        - Con cadena (niveles o a medida): se registra que ESE revisor NO
          revisó a tiempo y pasa al siguiente; si el último tampoco → auto.
        - Modo cualquiera: si nadie revisó en el plazo → auto-aprobado."""
        self.ensure_one()
        if self.state != 'publicado':
            return
        cadena = self._cadena()
        if not cadena:  # modo cualquiera
            self._aprobar_final(auto=True)
            _logger.info('[AUDIT] item_auto_aprobar item=%s', self.id)
            return

        paso = self.revision_paso or 1
        step = cadena[paso - 1] if 1 <= paso <= len(cadena) else cadena[-1]
        # Trazabilidad: queda registrado quién no revisó a tiempo.
        self._registrar_no_reviso(
            step, 'No revisó dentro de su plazo; pasa al siguiente revisor.')
        _logger.info('[AUDIT] item_no_reviso item=%s paso=%s', self.id, paso)
        if paso >= len(cadena):
            self._aprobar_final(auto=True)
            return
        self.revision_paso = paso + 1
        self._set_ventana_actual()

    @api.depends('name', 'proceso_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.proceso_id.name or ""} · {rec.name}'
