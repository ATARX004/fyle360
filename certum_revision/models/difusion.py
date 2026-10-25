# -*- coding: utf-8 -*-
"""Difusión de documentos aprobados a personas del cliente.

Es lo contrario de un aviso de flujo: no notifica un cambio de estado, sino
que **entrega** documentación terminada a gente que puede no haber
participado en la revisión —el jefe de obra, el área legal, quien va a usar
de verdad el certificado—.

Dos decisiones de diseño que conviene tener claras:

  - **No hay correos sueltos.** El destinatario es siempre un **contacto del
    cliente**, y si no tiene usuario de portal se le crea uno. Así el permiso
    del repositorio se apoya en un usuario autenticado y no en un enlace que
    puede reenviarse a cualquiera.
  - **El correo no lleva adjunto, lleva enlace.** El documento se sirve desde
    el repositorio del proyecto. Un adjunto se reenvía, envejece y se
    desincroniza; un enlace siempre entrega la versión vigente y deja
    registro de quién lo abrió.

Este modelo es además **la fuente del permiso**: alguien ve un documento en
el repositorio si, y solo si, existe una difusión que le incluya a él y al
documento.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CertumRevDifusion(models.Model):
    _name = 'certum.rev.difusion'
    _description = 'Difusión de documentos aprobados'
    _order = 'fecha desc, id desc'

    proceso_id = fields.Many2one('certum.rev.proceso', required=True,
                                 ondelete='cascade', index=True)
    item_ids = fields.Many2many('certum.rev.item', 'certum_rev_difusion_item_rel',
                                'difusion_id', 'item_id',
                                string='Documentos difundidos')
    partner_ids = fields.Many2many('res.partner', 'certum_rev_difusion_partner_rel',
                                   'difusion_id', 'partner_id',
                                   string='Destinatarios')
    mensaje = fields.Text(string='Mensaje')
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now,
                            required=True, index=True)
    enviado_por_id = fields.Many2one('res.partner', string='Enviada por')
    # Cuántos usuarios de portal hubo que crear. Interesa al soporte: explica
    # por qué alguien recibió además un correo de invitación de Odoo.
    usuarios_creados = fields.Integer(string='Usuarios creados', default=0)

    def name_get(self):
        return [(d.id, '%s · %s documento(s) a %s persona(s)'
                 % (d.proceso_id.name or '', len(d.item_ids), len(d.partner_ids)))
                for d in self]

    # ── Quién puede ver qué ────────────────────────────────────────────
    @api.model
    def items_para(self, partner):
        """Documentos que este contacto puede ver en el repositorio.

        Es la ÚNICA respuesta a «¿puede ver esto?». Todo lo demás —la vista,
        la descarga— se apoya aquí, para que no haya dos reglas de permiso que
        puedan divergir.
        """
        if not partner:
            return self.env['certum.rev.item']
        difusiones = self.sudo().search([('partner_ids', 'in', partner.id)])
        # Un documento pudo dejar de estar aprobado después de difundirse
        # (una reversión de turno lo reabre): en el repositorio solo se sirve
        # documentación terminada.
        return difusiones.mapped('item_ids').filtered(
            lambda i: i.state == 'aprobado' and i.attachment_final_id)

    @api.model
    def puede_ver(self, partner, item):
        """¿Este contacto tiene difundido este documento concreto?"""
        if not partner or not item:
            return False
        return bool(self.sudo().search_count([
            ('partner_ids', 'in', partner.id), ('item_ids', 'in', item.id),
        ]))

    @api.model
    def procesos_para(self, partner):
        """Proyectos en los que este contacto tiene algo difundido."""
        items = self.items_para(partner)
        return items.mapped('proceso_id')

    # ── Crear la difusión ──────────────────────────────────────────────
    @api.model
    def difundir(self, proceso, items, partners, mensaje=None, autor=None):
        """Registra la difusión, crea los usuarios que falten y avisa.

        Devuelve el registro creado. Valida en serio: difundir es dar acceso
        permanente a documentación, así que un destinatario colado no es un
        detalle estético.
        """
        if not items:
            raise UserError(_('Elige al menos un documento que difundir.'))
        sin_aprobar = items.filtered(
            lambda i: i.state != 'aprobado' or not i.attachment_final_id)
        if sin_aprobar:
            raise UserError(_(
                'Solo se difunden documentos aprobados. Revisa: %s',
                ', '.join(sin_aprobar.mapped('name'))))
        if any(i.proceso_id.id != proceso.id for i in items):
            raise UserError(_('Hay documentos que no son de este proyecto.'))

        if not partners:
            raise UserError(_('Elige al menos una persona a quien difundir.'))
        # El destinatario es SIEMPRE un contacto del cliente. Sin esta
        # comprobación, difundir sería una forma de dar acceso a cualquiera.
        ajenos = partners.filtered(
            lambda p: p.commercial_partner_id.id != proceso.cliente_id.id)
        if ajenos:
            raise UserError(_(
                'Estas personas no pertenecen a %(cliente)s: %(quien)s',
                cliente=proceso.cliente_id.display_name,
                quien=', '.join(ajenos.mapped('display_name'))))
        sin_correo = partners.filtered(lambda p: not p.email)
        if sin_correo:
            raise UserError(_(
                'Falta el correo de: %s. Complétalo en el contacto antes de '
                'difundir.', ', '.join(sin_correo.mapped('display_name'))))

        creados = self._asegurar_usuarios(partners)
        difusion = self.sudo().create({
            'proceso_id': proceso.id,
            'item_ids': [(6, 0, items.ids)],
            'partner_ids': [(6, 0, partners.ids)],
            'mensaje': (mensaje or '').strip()[:2000] or False,
            'enviado_por_id': autor.id if autor else False,
            'usuarios_creados': creados,
        })
        _logger.info('[AUDIT] difusion user=%s proceso=%s items=%s personas=%s '
                     'usuarios_creados=%s', self.env.user.id, proceso.id,
                     len(items), len(partners), creados)
        difusion._avisar()
        return difusion

    def _asegurar_usuarios(self, partners):
        """Crea usuario de portal a quien no lo tenga, y le manda la invitación.

        Sin usuario no hay repositorio: el correo llevaría a una pantalla de
        acceso que esa persona no puede pasar. Se crea con
        `no_reset_password` y luego se dispara la invitación explícitamente,
        para controlar el momento en que se envía.
        """
        Users = self.env['res.users'].sudo()
        grupo = self.env.ref('base.group_portal', raise_if_not_found=False)
        if not grupo:
            return 0
        creados = 0
        for p in partners:
            if Users.with_context(active_test=False).search_count(
                    [('partner_id', '=', p.id)]):
                continue
            try:
                usuario = Users.with_context(no_reset_password=True).create({
                    'login': p.email,
                    'partner_id': p.id,
                    'groups_id': [(6, 0, [grupo.id])],
                })
                usuario.action_reset_password()
                creados += 1
                _logger.info('[AUDIT] difusion_usuario_creado partner=%s login=%s',
                             p.id, p.email)
            except Exception:  # noqa: BLE001
                # Un login repetido u otro fallo no puede impedir la difusión
                # al resto: esa persona recibirá el correo y pedirá acceso.
                _logger.exception('difusion: no se pudo crear usuario para '
                                  'partner=%s', p.id)
        return creados

    def _avisar(self):
        """Encola el correo de difusión, uno por destinatario.

        Uno por persona y no uno con todos en copia: el enlace lleva al
        repositorio de quien lo abre, y poner a treinta personas en el mismo
        «Para» reparte además sus direcciones entre desconocidos.
        """
        self.ensure_one()
        self.env['certum.rev.correo.envio'].avisar('difusion', self)
