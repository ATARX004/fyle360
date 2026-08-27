# -*- coding: utf-8 -*-
"""El despachador: un único sitio por el que salen todos los correos.

Que todo pase por aquí es lo que permite tener, de una vez y para todos los
avisos: interruptor por evento, remitente y servidor comunes, copia global,
registro de lo enviado, idempotencia y —lo más importante— que **un fallo de
correo nunca tumbe la operación**. Publicar un documento tiene que funcionar
aunque el servidor SMTP esté caído.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class CertumRevAvisoEnvio(models.AbstractModel):
    _name = 'certum.rev.aviso'
    _description = 'Envío de avisos por correo'

    @api.model
    def enviar(self, evento, registro, xmlid_plantilla, destinatarios,
               clave=None, forzar=False, contexto=None, adjuntos=None):
        """Envía el aviso `evento` sobre `registro`. NUNCA lanza hacia fuera.

        `destinatarios` es una lista de correos ya resuelta. `clave` distingue
        avisos repetibles del mismo evento sobre el mismo registro (por
        ejemplo, la fecha para un recordatorio diario). `forzar` salta el
        interruptor y la idempotencia: es para el botón de prueba.

        Devuelve el registro de `certum.rev.aviso.log` creado, o `False` si no
        se intentó nada.
        """
        cfg = self.env['certum.rev.aviso.config']
        Log = self.env['certum.rev.aviso.log'].sudo()
        try:
            if not forzar and not cfg.activo(evento):
                return self._anotar(Log, evento, registro, clave, [],
                                    'omitido', 'Aviso desactivado')

            destinatarios = cfg.parsear(','.join(destinatarios or []))
            if not destinatarios:
                return self._anotar(Log, evento, registro, clave, [],
                                    'omitido', 'Sin destinatarios con correo')

            if not forzar and Log._ya_enviado(evento, registro._name,
                                              registro.id, clave):
                return False

            plantilla = self.env.ref(xmlid_plantilla, raise_if_not_found=False)
            if not plantilla:
                _logger.warning('aviso %s: falta la plantilla %s',
                                evento, xmlid_plantilla)
                return self._anotar(Log, evento, registro, clave, destinatarios,
                                    'fallido', 'Plantilla no encontrada: %s'
                                    % xmlid_plantilla)

            copia = cfg.copia_global()
            valores = {
                'email_to': ', '.join(destinatarios),
                'email_cc': ', '.join(copia) if copia else False,
                'auto_delete': False,
            }
            remitente = cfg.remitente()
            if remitente:
                valores['email_from'] = remitente
            servidor = cfg.mail_server_id()
            if servidor:
                valores['mail_server_id'] = servidor

            correo = plantilla.sudo().with_context(**(contexto or {})).send_mail(
                registro.id, force_send=False, email_values=valores)
            correo = self.env['mail.mail'].sudo().browse(correo)
            if adjuntos:
                correo.write({'attachment_ids': [(6, 0, adjuntos.ids)]})

            log = self._anotar(
                Log, evento, registro, clave, destinatarios,
                'prueba' if forzar else 'enviado', None,
                asunto=correo.subject, copia=copia, remitente=remitente,
                mail_id=correo.id)
            _logger.info('[AUDIT] aviso_enviado evento=%s modelo=%s id=%s to=%s',
                         evento, registro._name, registro.id,
                         ', '.join(destinatarios))
            return log
        except Exception as exc:  # noqa: BLE001
            # Un fallo de correo no puede tumbar la transición que lo disparó:
            # publicar un documento tiene que funcionar con el SMTP caído.
            _logger.exception('aviso %s: fallo enviando sobre %s:%s',
                              evento, getattr(registro, '_name', '?'),
                              getattr(registro, 'id', '?'))
            try:
                return self._anotar(Log, evento, registro, clave,
                                    destinatarios or [], 'fallido', str(exc))
            except Exception:  # noqa: BLE001
                return False

    @api.model
    def _anotar(self, Log, evento, registro, clave, destinatarios, estado,
                error, asunto=None, copia=None, remitente=None, mail_id=None):
        proceso = self._proceso_de(registro)
        return Log.create({
            'evento': evento,
            'res_model': registro._name,
            'res_id': registro.id,
            'clave': clave or False,
            'destinatarios': ', '.join(destinatarios) or False,
            'copia': ', '.join(copia or []) or False,
            'remitente': remitente or False,
            'asunto': asunto or False,
            'estado': estado,
            'error': error or False,
            'mail_id': mail_id or False,
            'proceso_id': proceso.id if proceso else False,
        })

    @api.model
    def _proceso_de(self, registro):
        """El proyecto al que pertenece el registro, para poder filtrar el
        historial de avisos por proyecto."""
        if registro._name == 'certum.rev.proceso':
            return registro
        return getattr(registro, 'proceso_id', None) or None

    # ── Destinatarios ──────────────────────────────────────────────────
    @api.model
    def correos_de(self, partners):
        """Correos válidos de un conjunto de contactos, sin repetir."""
        cfg = self.env['certum.rev.aviso.config']
        return cfg.parsear(','.join(p.email or '' for p in partners))

    @api.model
    def correos_empresa(self, company, incluir_empresa=True):
        """Correos de una empresa participante: sus contactos-persona y, si se
        pide, el buzón de la propia empresa.

        Se avisa a las personas, no solo a la empresa: un buzón genérico que
        nadie mira es la forma más común de que un plazo se venza «sin que
        nadie se enterara».
        """
        if not company:
            return []
        personas = self.env['res.partner'].sudo().search([
            ('parent_id', '=', company.id), ('is_company', '=', False),
        ])
        correos = self.correos_de(personas)
        if incluir_empresa and company.email:
            for c in self.env['certum.rev.aviso.config'].parsear(company.email):
                if c not in correos:
                    correos.append(c)
        return correos

    @api.model
    def correos_turno(self, item):
        """A quién le toca revisar AHORA este documento.

        Si la cadena nombra personas, solo a esa persona: avisar a los cinco
        contactos de que le toca a uno es la mejor manera de que ninguno haga
        nada. Si es por niveles o no hay cadena, a toda la empresa cliente.
        """
        cadena = item._cadena()
        paso = item.revision_paso or 0
        if cadena and 1 <= paso <= len(cadena):
            pid = cadena[paso - 1].get('partner_id')
            if pid:
                p = self.env['res.partner'].sudo().browse(pid)
                correos = self.correos_de(p)
                if correos:
                    return correos
        return self.correos_empresa(item.proceso_id.cliente_id)
