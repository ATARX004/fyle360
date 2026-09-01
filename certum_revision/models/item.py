# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .notify import (notify_aprobado, notify_observado, notify_publicado,
                     notify_turno_devuelto)
from .tz_utils import fin_de_dia_utc, fmt_lima

_logger = logging.getLogger(__name__)

ITEM_STATES = [
    ('pendiente', 'Pendiente'),
    ('publicado', 'Publicado'),
    ('observado', 'Observado'),
    ('aprobado', 'Aprobado'),
]

DEFAULT_DIAS_CORRECCION = 3   # días extra al proveedor tras una observación
MAX_DIAS_REVERSION = 60       # tope al devolver un turno vencido
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
    # Dónde retomar la revisión tras una corrección. Una observación NO anula
    # las aprobaciones ya conseguidas: el documento corregido vuelve a manos de
    # QUIEN LO OBSERVÓ —con sus días otra vez— y sigue hacia el resto de la
    # cadena. Hacerlo empezar de cero obligaría a los anteriores a aprobar de
    # nuevo algo que ya habían dado por bueno.
    revision_paso_observado = fields.Integer(
        string='Paso que observó', copy=False,
        help='Paso de la cadena en el que se observó el documento. Al '
             'republicar, la revisión se retoma ahí.')
    observado_por_id = fields.Many2one(
        'res.partner', string='Observado por', copy=False,
        help='Quién observó. Se prefiere a la posición para retomar, por si '
             'la cadena cambió entre la observación y la corrección.')

    # ── Deshacer la última publicación ─────────────────────────────
    # Subir un archivo encima del vigente lo reemplaza y reinicia la revisión.
    # Si fue un error, sin esta foto no habría vuelta atrás: el documento
    # anterior seguiría en el historial, pero el estado del flujo se habría
    # perdido. Se guarda al publicar y se consume al deshacer.
    undo_fecha = fields.Datetime(string='Publicación deshacible', copy=False)
    undo_attachment_id = fields.Many2one('ir.attachment', copy=False,
                                         string='Documento anterior')
    undo_state = fields.Selection(ITEM_STATES, string='Estado anterior', copy=False)
    undo_paso = fields.Integer(string='Paso anterior', copy=False)
    undo_limite = fields.Datetime(string='Límite de revisión anterior', copy=False)
    undo_limite_corr = fields.Datetime(string='Límite de corrección anterior',
                                       copy=False)
    undo_paso_obs = fields.Integer(string='Paso observado anterior', copy=False)
    undo_observado_por_id = fields.Many2one('res.partner', copy=False,
                                            string='Observado por (anterior)')

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
            raise UserError(_('El proyecto no está activo.'))

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

    def _paso_de(self, partner):
        """Posición (1-based) de `partner` en la cadena, o 0 si no está.

        Solo tiene sentido en cadenas por PERSONAS: en las cadenas por nivel
        los pasos no apuntan a nadie concreto.
        """
        self.ensure_one()
        if not partner:
            return 0
        for i, paso in enumerate(self._cadena(), start=1):
            if paso.get('partner_id') == partner.id:
                return i
        return 0

    def _paso_reanudar(self, cadena):
        """Paso en el que retomar la revisión al publicar una corrección.

        Vuelve a QUIEN OBSERVÓ, no al principio: sus predecesores ya aprobaron
        y no tiene sentido pedirles que lo hagan otra vez. Se busca primero por
        PERSONA, porque la cadena pudo cambiar entre la observación y la
        corrección y la posición antigua apuntaría a otro revisor. Si no se la
        encuentra —cadena por niveles, o alguien que ya no participa— se usa la
        posición guardada, recortada a la cadena vigente.
        """
        self.ensure_one()
        if not cadena:
            return 0
        if self.observado_por_id:
            paso = self._paso_de(self.observado_por_id)
            if paso:
                return paso
        guardado = self.revision_paso_observado or 0
        if guardado:
            return max(1, min(guardado, len(cadena)))
        return 1

    def _consumir_dias_reservados(self, paso):
        """Días que el proveedor reservó para el revisor de `paso` y que aún
        no se han aplicado. Al devolverlos quedan marcados como aplicados."""
        self.ensure_one()
        cadena = self._cadena()
        if not (1 <= paso <= len(cadena)):
            return 0
        pid = cadena[paso - 1].get('partner_id')
        if not pid:
            return 0
        reservadas = self.ampliacion_ids.filtered(
            lambda a: (a.estado == 'concedida' and not a.aplicada
                       and a.beneficiario_id.id == pid))
        if not reservadas:
            return 0
        dias = sum(reservadas.mapped('dias_concedidos'))
        reservadas.write({'aplicada': True})
        _logger.info('[AUDIT] item_dias_reservados item=%s paso=%s dias=%s',
                     self.id, paso, dias)
        return dias

    def _limite_revision_lima(self, fmt='%d/%m/%Y'):
        """La fecha límite en hora de Lima, para las plantillas de correo.

        Formatearla en UTC mostraría el día siguiente: la ventana cierra a las
        23:59 de Lima, que son las 04:59 UTC del día de después.
        """
        self.ensure_one()
        if not self.fecha_limite_revision:
            return ''
        return fmt_lima(self.fecha_limite_revision, fmt)

    def _limite_correccion_lima(self, fmt='%d/%m/%Y'):
        """El plazo de corrección en hora de Lima. Mismo motivo que el de
        revisión: en UTC saldría el día siguiente."""
        self.ensure_one()
        if not self.fecha_limite_correccion:
            return ''
        return fmt_lima(self.fecha_limite_correccion, fmt)

    def _paso_de_traza(self, traza, cadena):
        """Paso al que corresponde una traza de la cadena, o 0.

        Por PERSONA cuando la cadena nombra revisores; por NIVEL cuando son
        capas, donde la traza no guarda a nadie concreto (el `no_reviso` de una
        capa lo firma el usuario del cron).
        """
        self.ensure_one()
        if cadena and cadena[0].get('partner_id'):
            return self._paso_de(traza.partner_id)
        for i, paso in enumerate(cadena, start=1):
            if traza.nivel and paso.get('nivel') == traza.nivel:
                return i
        return 0

    def _reversion_disponible(self):
        """¿Se le puede devolver el turno a un revisor que se quedó sin revisar?

        El sistema avanza solo cuando alguien deja vencer su ventana. A veces
        eso es un accidente —estuvo de baja, el correo se perdió— y el
        proveedor prefiere darle otra oportunidad antes que quedarse con una
        aprobación que nadie miró.

        El límite es firme: si DESPUÉS de esa omisión alguien aprobó u observó,
        no se revierte. Deshacerlo borraría una decisión ya tomada por una
        persona, y eso no es reabrir un turno sino anular a un revisor.

        Cuando la cadena encadena varias omisiones seguidas, se vuelve a la
        PRIMERA: son todas del sistema, nadie decidió nada, y devolver el turno
        al primero deja que la cadena fluya de nuevo por todos ellos.

        Devuelve siempre un dict; `puede` dice si se ofrece y `motivo` explica
        el bloqueo cuando no.
        """
        self.ensure_one()
        vacio = {'puede': False, 'motivo': '', 'paso': 0, 'quien': '',
                 'dias_sugeridos': 0, 'hubo_omision': False}
        cadena = self._cadena()
        if not cadena:
            return dict(vacio, motivo=_('Este documento no se revisa por cadena.'))

        # Omisiones acumuladas desde la última decisión REAL de una persona.
        # `auto_aprobado`, `ampliacion` y `reanudado` no son decisiones de
        # revisión, así que no cierran la ventana de reversión.
        tanda, hubo_alguna = [], False
        for t in self.aprobacion_ids.sorted(lambda t: (t.fecha, t.id)):
            if t.accion == 'no_reviso':
                tanda.append(t)
                hubo_alguna = True
            elif t.accion in ('aprobado', 'observado'):
                tanda = []
        # `hubo_omision` marca que en este ítem SÍ se saltó a alguien. Sirve
        # para explicar por qué la opción no está, en vez de esconderla y dejar
        # al proveedor buscando un botón que no aparece.
        hubo = dict(vacio, hubo_omision=hubo_alguna)
        if not tanda:
            return dict(hubo, motivo=_(
                'Un revisor posterior ya aprobó u observó el documento: '
                'devolver el turno anularía su decisión.') if hubo_alguna
                else _('No hay ningún turno vencido que devolver.'))
        if self.state == 'observado':
            return dict(hubo, motivo=_(
                'El documento está observado. Al publicar la corrección volverá '
                'a quien lo observó.'))
        if self.state == 'pendiente':
            return dict(hubo, motivo=_('El documento aún no está publicado.'))
        if self.proceso_id.state in ('borrador', 'fuera_plazo'):
            return dict(hubo, motivo=_(
                'El proyecto no admite cambios: primero hay que ampliar su '
                'plazo general.'))

        paso = self._paso_de_traza(tanda[0], cadena)
        if not paso:
            return dict(hubo, motivo=_(
                'No se pudo identificar a qué revisor devolverle el turno.'))
        step = cadena[paso - 1]
        if step.get('partner_id'):
            quien = self.env['res.partner'].sudo().browse(
                step['partner_id']).display_name
        else:
            quien = _('Nivel %s') % step.get('nivel')
        return {'puede': True, 'motivo': '', 'paso': paso, 'quien': quien,
                'dias_sugeridos': self._dias_por_paso(paso, len(cadena)) or 1,
                'hubo_omision': True}

    def revertir_no_reviso(self, dias, partner=None):
        """Devuelve el turno al revisor que dejó vencer su ventana, con `dias`.

        Si el ítem se había dado por aprobado al vencer el último paso, se
        reabre; y si esa aprobación había cerrado el expediente, el expediente
        vuelve a revisión. Reabrir es el sentido de la operación: lo contrario
        sería dejar por bueno un documento que nadie llegó a mirar.
        """
        self.ensure_one()
        disp = self._reversion_disponible()
        if not disp['puede']:
            raise UserError(disp['motivo'] or _('No se puede devolver el turno.'))
        try:
            dias = int(dias)
        except (TypeError, ValueError):
            dias = 0
        if dias <= 0 or dias > MAX_DIAS_REVERSION:
            raise UserError(_('Indica entre 1 y %s días.', MAX_DIAS_REVERSION))

        ahora = fields.Datetime.now()
        limite = ahora + timedelta(days=dias)
        tope = self._tope_proceso()
        if tope and limite > tope:
            limite = tope
        if limite <= ahora:
            raise UserError(_(
                'El plazo general del proyecto ya venció: amplíalo antes de '
                'devolver el turno.'))

        paso = disp['paso']
        reabierto = self.state == 'aprobado'
        self.write({
            'state': 'publicado',
            'revision_paso': paso,
            'fecha_limite_revision': limite,
        })
        self._sync_nivel()
        if reabierto and self.proceso_id.state == 'completado':
            self.proceso_id.state = 'revision'
            _logger.info('[AUDIT] proceso_reabierto proceso=%s por_item=%s',
                         self.proceso_id.id, self.id)
        self._registrar(
            'revertido', partner=partner, lado='proveedor',
            comentario=_('Turno devuelto a %(quien)s (paso %(paso)s) con '
                         '%(dias)s día(s) más para revisar.%(reabre)s',
                         quien=disp['quien'], paso=paso, dias=dias,
                         reabre=(_(' El documento estaba aprobado por '
                                   'vencimiento y se reabrió.') if reabierto
                                 else '')))
        _logger.info('[AUDIT] item_revertir_no_reviso user=%s item=%s paso=%s '
                     'dias=%s reabierto=%s', self.env.user.id, self.id, paso,
                     dias, reabierto)
        notify_turno_devuelto(self)
        return limite

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
            # Al reparto normal se le suman los días que el proveedor haya
            # reservado para ESTE revisor. Si el reparto le daba 0 y hay días
            # reservados, deja de saltarse: el proveedor le dio turno a propósito.
            dias = self._dias_por_paso(paso, n) + self._consumir_dias_reservados(paso)
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
        # Aprobar el último documento NO cierra el proyecto: queda «listo para
        # cerrar» y sigue admitiendo cambios hasta que el proveedor lo cierre.
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
        # Si esto es una CORRECCIÓN, la revisión se retoma donde se observó.
        # Hay que resolverlo ANTES del write, que borra esas marcas.
        corrigiendo = self.state == 'observado'
        paso = self._paso_reanudar(cadena) if chained else 0
        quien_observo = self.observado_por_id

        self.write({
            'state': 'publicado',
            'fecha_publicacion': ahora,
            'fecha_limite_revision': False,
            'fecha_limite_correccion': False,
            'revision_paso': paso,
            'revision_nivel': 0,
            # Las marcas de la observación se consumen aquí: ya cumplieron.
            'revision_paso_observado': 0,
            'observado_por_id': False,
            'attachment_ids': [(4, attachment.id)],
            'attachment_final_id': attachment.id,
            # Foto del estado previo, para poder deshacer esta publicación si
            # fue un error. Se toma de los valores de ANTES de este write.
            'undo_fecha': ahora,
            'undo_attachment_id': self.attachment_final_id.id or False,
            'undo_state': self.state,
            'undo_paso': self.revision_paso or 0,
            'undo_limite': self.fecha_limite_revision or False,
            'undo_limite_corr': self.fecha_limite_correccion or False,
            'undo_paso_obs': self.revision_paso_observado or 0,
            'undo_observado_por_id': self.observado_por_id.id or False,
        })
        if corrigiendo and paso > 1:
            # Que quede en el historial por qué la revisión no empieza de cero.
            self._registrar(
                'reanudado', partner=quien_observo or None, lado='sistema',
                comentario=_('Corrección publicada: la revisión se retoma en el '
                             'paso %(paso)s, con quien observó el documento. Las '
                             '%(previas)s aprobación(es) anteriores siguen '
                             'siendo válidas.',
                             paso=paso, previas=paso - 1))
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

    def reemplazar_final(self, attachment, partner=None, motivo=None):
        """Sustituye el documento de un ítem YA APROBADO, sin crear versión.

        Es la última red antes de entregar: el proveedor detecta que el archivo
        aprobado tiene una errata, una firma que falta o simplemente no es el
        que debía, y lo cambia por el bueno. NO reabre la revisión ni genera
        historial de versiones: el archivo anterior se borra y en su lugar
        queda este.

Queda **traza** con los dos archivos y el motivo: el ítem no
        se marca de ninguna forma visible, pero el registro de auditoría no
        puede quedarse sin explicar qué se aprobó.
        """
        self.ensure_one()
        if self.state != 'aprobado':
            raise UserError(_('Solo se reemplaza el documento final de un ítem '
                              'ya aprobado.'))
        if self.proceso_id.state == 'borrador':
            raise UserError(_('El proyecto aún no está abierto.'))
        anterior = self.attachment_final_id
        if anterior and anterior.id == attachment.id:
            raise UserError(_('Ese ya es el documento final.'))

        nombre_ant = anterior.name or _('el archivo anterior')
        # Fuera del conjunto y borrado: reemplazar es reemplazar, no acumular.
        if anterior:
            self.attachment_ids = [(3, anterior.id)]
            anterior.sudo().unlink()
        self.write({
            'attachment_ids': [(4, attachment.id)],
            'attachment_final_id': attachment.id,
            # Deshacer apuntaría a un archivo que acaba de desaparecer.
            'undo_fecha': False, 'undo_attachment_id': False,
            'undo_state': False, 'undo_paso': 0,
        })
        self._registrar(
            'final_reemplazado', partner=partner, lado='proveedor',
            comentario=_('Documento final sustituido: «%(antes)s» → '
                         '«%(ahora)s», sin reabrir la revisión.%(motivo)s',
                         antes=nombre_ant, ahora=attachment.name,
                         motivo=((' ' + motivo) if motivo else '')))
        _logger.info('[AUDIT] item_reemplazar_final user=%s item=%s antes=%s '
                     'ahora=%s', self.env.user.id, self.id,
                     anterior.id if anterior else 0, attachment.id)
        return True

    def _puede_limpiar(self):
        """¿Se pueden borrar los archivos publicados de este documento?

        Solo mientras NADIE lo haya revisado. En cuanto hay una aprobación o
        una observación, los archivos son la prueba de sobre qué se decidió y
        borrarlos dejaría la traza sin respaldo. Antes de eso no hay nada que
        respaldar: el proveedor se equivocó de archivo y quiere dejarlo limpio.
        """
        self.ensure_one()
        if self.state == 'aprobado':
            return False
        if self.proceso_id.state not in ('publicacion', 'revision'):
            return False
        return not self.aprobacion_ids.filtered(
            lambda t: t.accion in ('aprobado', 'observado'))

    def borrar_documento(self, attachment, partner=None):
        """Elimina un archivo publicado y, si era el último, deja el documento
        limpio y otra vez pendiente de publicar.

        Aquí sí se borra de verdad —archivo y registro—, al revés que la
        depuración por antigüedad: aquello retira versiones superadas de algo
        ya revisado y por eso conserva el rastro; esto retira un archivo que
        nunca debió estar y del que no hay nada que auditar.
        """
        self.ensure_one()
        if not self._puede_limpiar():
            raise UserError(_(
                'Este documento ya fue revisado: sus archivos son la prueba de '
                'sobre qué se decidió y no se pueden borrar.'))
        if attachment not in self.attachment_ids:
            raise UserError(_('Ese archivo no pertenece a este documento.'))
        nombre = attachment.name
        self.attachment_ids = [(3, attachment.id)]
        attachment.sudo().unlink()

        quedan = self.attachment_ids.sorted('create_date', reverse=True)
        vals = {'attachment_final_id': quedan[:1].id or False}
        if not quedan:
            # Sin archivos no hay nada que revisar: vuelve al punto de partida.
            vals.update({
                'state': 'pendiente', 'revision_paso': 0, 'revision_nivel': 0,
                'fecha_limite_revision': False, 'fecha_publicacion': False,
                'undo_fecha': False, 'undo_attachment_id': False,
                'undo_state': False, 'undo_paso': 0,
            })
        self.write(vals)
        self._registrar('documento_borrado', partner=partner, lado='proveedor',
                        comentario=_('Se eliminó «%(archivo)s» antes de que '
                                     'nadie lo revisara.%(vacio)s',
                                     archivo=nombre,
                                     vacio=('' if quedan else _(
                                         ' El documento vuelve a estar '
                                         'pendiente de publicación.'))))
        _logger.info('[AUDIT] item_borrar_documento user=%s item=%s archivo=%s '
                     'quedan=%s', self.env.user.id, self.id, nombre, len(quedan))
        return True

    def _undo_disponible(self):
        """¿Se puede deshacer la última publicación de este documento?

        Se bloquea en cuanto un revisor **decide sobre la versión nueva**: si
        alguien ya la aprobó u observó, retirarla a sus espaldas dejaría una
        decisión apuntando a un archivo que el revisor nunca vio. Hasta ese
        momento nadie ha mirado nada y deshacer no le quita nada a nadie.
        """
        self.ensure_one()
        vacio = {'puede': False, 'motivo': '', 'anterior': '', 'estado': '',
                 'hubo_publicacion': False}
        if not self.undo_fecha:
            return dict(vacio, motivo=_('No hay ninguna publicación reciente '
                                        'que deshacer.'))
        hubo = dict(vacio, hubo_publicacion=True)
        if self.proceso_id.state not in ('publicacion', 'revision'):
            return dict(hubo, motivo=_('El proyecto no admite cambios.'))
        decidida = self.aprobacion_ids.filtered(
            lambda t: (t.accion in ('aprobado', 'observado')
                       and t.fecha and t.fecha > self.undo_fecha))
        if decidida:
            return dict(hubo, motivo=_(
                'Un revisor ya se pronunció sobre esta versión: retirarla '
                'dejaría su decisión sobre un documento que no llegó a ver.'))
        etiquetas = dict(self._fields['state'].selection)
        return {
            'puede': True, 'motivo': '', 'hubo_publicacion': True,
            'anterior': self.undo_attachment_id.name or '',
            'estado': etiquetas.get(self.undo_state, self.undo_state or ''),
        }

    def revertir_publicacion(self, partner=None):
        """Deshace la última publicación y devuelve el documento a como estaba.

        El archivo retirado NO se borra: sigue en el historial, marcado como no
        vigente. Se borra el registro de que es el bueno, no el registro de que
        existió.
        """
        self.ensure_one()
        disp = self._undo_disponible()
        if not disp['puede']:
            raise UserError(disp['motivo'] or _('No se puede deshacer.'))
        retirado = self.attachment_final_id
        vals = {
            'state': self.undo_state or 'pendiente',
            'attachment_final_id': self.undo_attachment_id.id or False,
            'revision_paso': self.undo_paso or 0,
            'fecha_limite_revision': self.undo_limite or False,
            'fecha_limite_correccion': self.undo_limite_corr or False,
            'revision_paso_observado': self.undo_paso_obs or 0,
            'observado_por_id': self.undo_observado_por_id.id or False,
            # Deshacer es de un solo paso: la foto se consume aquí.
            'undo_fecha': False, 'undo_attachment_id': False,
            'undo_state': False, 'undo_paso': 0, 'undo_limite': False,
            'undo_limite_corr': False, 'undo_paso_obs': 0,
            'undo_observado_por_id': False,
        }
        self.write(vals)
        self._sync_nivel()
        self._registrar(
            'publicacion_revertida', partner=partner, lado='proveedor',
            comentario=_('Se retiró «%(archivo)s» y vuelve a regir '
                         '«%(vuelve)s». El documento queda como %(estado)s. El '
                         'archivo retirado permanece en el historial.',
                         archivo=(retirado.name or _('el último archivo')),
                         vuelve=(self.attachment_final_id.name
                                 or _('ningún documento')),
                         estado=disp['estado'].lower()))
        _logger.info('[AUDIT] item_revertir_publicacion user=%s item=%s '
                     'retirado=%s vuelve=%s', self.env.user.id, self.id,
                     retirado.id, self.attachment_final_id.id)
        return True

    def ampliar_revision(self, dias, partner=None, lado='proveedor'):
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
                'El plazo general del proyecto vence antes: no se pueden '
                'añadir más días a esta revisión sin ampliar primero el '
                'proyecto.'))

        self.fecha_limite_revision = nuevo
        self._registrar('ampliacion', partner=partner,
                        nivel=(partner.certum_nivel if partner else 0),
                        lado=lado,
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
            # Se recuerda dónde quedó la revisión para retomarla ahí cuando
            # llegue la corrección, en vez de empezar la cadena de nuevo.
            'revision_paso_observado': self.revision_paso or 0,
            'observado_por_id': partner.id if partner else False,
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
