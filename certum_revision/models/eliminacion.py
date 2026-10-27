# -*- coding: utf-8 -*-
"""Eliminación de un proyecto, con código de confirmación por correo.

Borrar un proyecto no tiene vuelta atrás: se van sus carpetas, documentos,
archivos, revisiones y comentarios. Por eso no basta con un botón:

1. Quien elimina confirma en pantalla y escribe el código del proyecto.
2. FYLE 360 manda a **todos los usuarios internos** el correo «ELIMINACIÓN
   DE PROYECTO», que dice quién lo pide y qué proyecto, con un código de seis
   cifras. Nadie del equipo se entera tarde de que un proyecto desapareció.
3. Quien lo pidió escribe ese código y el proyecto se borra.

El código vale 15 minutos y admite 5 intentos. Pedir otro anula el anterior.
No se guarda: solo su huella (sha256 con sal), así que ni leyendo la base se
puede confirmar una eliminación ajena.

Cada solicitud queda registrada aunque el proyecto ya no exista: los datos
que lo identifican se copian aquí al pedirla.
"""
import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MINUTOS_VALIDEZ = 15
MAX_INTENTOS = 5


def _huella(sal, codigo):
    return hashlib.sha256(('%s:%s' % (sal, codigo)).encode()).hexdigest()


class CertumRevEliminacion(models.Model):
    _name = 'certum.rev.eliminacion'
    _description = 'Eliminación de proyecto'
    _order = 'create_date desc, id desc'
    _rec_name = 'proyecto'

    proceso_id = fields.Many2one('certum.rev.proceso', string='Proyecto',
                                 ondelete='set null', index=True)
    # Copia de lo que identifica al proyecto: queda aunque se borre.
    proyecto = fields.Char('Código del proyecto', required=True)
    referencia = fields.Char()
    proveedor = fields.Char()
    cliente = fields.Char()
    estado_proyecto = fields.Char('Estado del proyecto')
    solicitante_id = fields.Many2one('res.users', string='Solicitado por',
                                     required=True, ondelete='restrict')
    estado = fields.Selection([
        ('pendiente', 'Esperando el código'),
        ('eliminado', 'Proyecto eliminado'),
        ('vencida', 'Código vencido'),
        ('anulada', 'Anulada'),
    ], default='pendiente', required=True, index=True)
    sal = fields.Char(required=True, copy=False)
    codigo_hash = fields.Char(required=True, copy=False)
    vence = fields.Datetime(required=True)
    intentos = fields.Integer(default=0)
    avisados = fields.Integer('Usuarios avisados', default=0)
    fecha_eliminacion = fields.Datetime('Eliminado el')
    detalle = fields.Char(help='Qué se borró: documentos y archivos.')

    # ── Pedir el código ───────────────────────────────────────────────
    @api.model
    def solicitar(self, proceso):
        """Crea la solicitud y manda el código a todo el personal interno.

        Devuelve la solicitud. Si el correo no llega a nadie, la anula y
        avisa: sin código no hay forma de confirmar, y es mejor saberlo ya.
        """
        proceso = proceso.sudo()
        Elim = self.sudo()
        Elim.search([('proceso_id', '=', proceso.id), ('estado', '=', 'pendiente')]).write(
            {'estado': 'anulada'})
        codigo = '%06d' % secrets.randbelow(10 ** 6)
        sal = secrets.token_hex(8)
        estados = dict(proceso._fields['state'].selection)
        elim = Elim.create({
            'proceso_id': proceso.id,
            'proyecto': proceso.name,
            'referencia': proceso.referencia or False,
            'proveedor': proceso.proveedor_id.name or False,
            'cliente': proceso.cliente_id.name or False,
            'estado_proyecto': estados.get(proceso.state, proceso.state),
            'solicitante_id': self.env.user.id,
            'sal': sal,
            'codigo_hash': _huella(sal, codigo),
            'vence': fields.Datetime.now() + timedelta(minutes=MINUTOS_VALIDEZ),
        })
        _logger.info('[AUDIT] eliminacion_solicitada user=%s proceso=%s solicitud=%s',
                     self.env.user.id, proceso.id, elim.id)
        if not elim._avisar(codigo):
            elim.estado = 'anulada'
            raise UserError(_(
                'No se pudo enviar el código a ningún usuario interno. Revise el '
                'remitente en Administración → Correos y vuelva a intentarlo.'))
        return elim

    def _avisar(self, codigo):
        """Manda el correo de eliminación con el código a cada usuario
        interno. Sale al momento, sin pasar por la cola ni por la pausa: es
        un correo de seguridad, no un aviso del flujo."""
        self.ensure_one()
        Envio = self.env['certum.rev.correo.envio'].sudo()
        internos = self.env['res.users'].sudo().search([('share', '=', False)]).partner_id
        envios = Envio.browse()
        for partner in Envio._unicos(internos):
            envios |= Envio.encolar('eliminacion', self, partner, origen='seguridad')
        pendientes = envios.filtered(lambda e: e.estado == 'pendiente')
        pendientes.with_context(fyle_codigo=codigo)._procesar(forzar_envio=True)
        self.avisados = len(envios.filtered(lambda e: e.estado in ('en_cola', 'enviado')))
        return self.avisados

    # ── Confirmar ─────────────────────────────────────────────────────
    def vigente(self):
        self.ensure_one()
        return self.estado == 'pendiente' and self.vence > fields.Datetime.now()

    def confirmar(self, codigo):
        """Comprueba el código y, si es el bueno, elimina el proyecto.

        Solo confirma quien lo pidió. Un código equivocado gasta un intento;
        al quinto la solicitud se anula y hay que pedir otro. Devuelve el
        detalle de lo borrado.
        """
        self.ensure_one()
        elim = self.sudo()
        if elim.solicitante_id != self.env.user:
            raise UserError(_('Solo quien pidió la eliminación puede confirmarla.'))
        if elim.estado != 'pendiente':
            raise UserError(_('Esta solicitud ya no está vigente. Pida un código nuevo.'))
        if elim.vence <= fields.Datetime.now():
            elim.estado = 'vencida'
            raise UserError(_('El código venció. Pida uno nuevo.'))
        limpio = re.sub(r'\D', '', codigo or '')
        if not hmac.compare_digest(elim.codigo_hash, _huella(elim.sal, limpio)):
            elim.intentos += 1
            quedan = MAX_INTENTOS - elim.intentos
            _logger.warning('[AUDIT] eliminacion_codigo_erroneo user=%s solicitud=%s intentos=%s',
                            self.env.user.id, elim.id, elim.intentos)
            if quedan <= 0:
                elim.estado = 'anulada'
                raise UserError(_('Código incorrecto. Se agotaron los intentos: pida un código nuevo.'))
            raise UserError(_('Código incorrecto. Le quedan %s intento(s).', quedan))
        if not elim.proceso_id:
            elim.estado = 'anulada'
            raise UserError(_('El proyecto ya no existe.'))
        hecho = elim.proceso_id._eliminar()
        datos = next(iter(hecho.values()), {})
        elim.write({
            'estado': 'eliminado',
            'fecha_eliminacion': fields.Datetime.now(),
            'detalle': _('%(d)s documento(s) y %(a)s archivo(s)',
                         d=datos.get('documentos', 0), a=datos.get('archivos', 0)),
        })
        return elim.detalle
