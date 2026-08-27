# -*- coding: utf-8 -*-
"""Registro de cada correo que el sistema intenta enviar.

Sirve para tres cosas distintas, y conviene no confundirlas:

  - **Auditoría**: responder a «¿me lo mandaron?» con una fecha y un
    destinatario, que es la única respuesta que sirve.
  - **Idempotencia**: que un cron que se ejecuta dos veces no mande el mismo
    aviso dos veces. Lo garantiza un índice único PARCIAL en base de datos
    (solo sobre los enviados), no una comprobación en Python: entre el
    `search` y el `create` cabe otro proceso.
  - **Diagnóstico**: cuando alguien dice «no me llegó», el estado `fallido`
    con su mensaje de error dice si el problema fue del sistema o del buzón.
"""
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class CertumRevAvisoLog(models.Model):
    _name = 'certum.rev.aviso.log'
    _description = 'Registro de avisos por correo'
    _order = 'fecha desc, id desc'

    evento = fields.Char(string='Evento', required=True, index=True)
    res_model = fields.Char(string='Modelo', required=True, index=True)
    res_id = fields.Integer(string='ID del registro', required=True, index=True)
    # Clave de repetición: distingue avisos del MISMO evento sobre el MISMO
    # registro que sí deben poder repetirse (un recordatorio diario, un envío
    # a otro destinatario). Vacía = uno solo para siempre.
    clave = fields.Char(string='Clave de repetición', index=True)

    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now,
                            required=True, index=True)
    destinatarios = fields.Char(string='Para')
    copia = fields.Char(string='Copia')
    remitente = fields.Char(string='De')
    asunto = fields.Char(string='Asunto')
    estado = fields.Selection([
        ('enviado', 'Enviado'),
        ('fallido', 'Fallido'),
        ('omitido', 'Omitido'),
        ('prueba', 'Prueba'),
    ], string='Estado', required=True, default='enviado', index=True)
    error = fields.Text(string='Error')
    mail_id = fields.Many2one('mail.mail', string='Correo de Odoo',
                              ondelete='set null')
    proceso_id = fields.Many2one('certum.rev.proceso', string='Proyecto',
                                 ondelete='cascade', index=True)

    def _auto_init(self):
        """Índice único PARCIAL: un solo envío conseguido por evento+registro.

        Parcial a propósito: las pruebas, los omitidos y los fallidos deben
        poder repetirse —de hecho un fallido tiene que poder reintentarse—,
        pero un aviso ya entregado no se manda dos veces. Hacer esta
        comprobación en Python no bastaría: entre el `search` y el `create`
        cabe perfectamente otra ejecución del mismo cron.
        """
        res = super()._auto_init()
        self._cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS certum_rev_aviso_log_uniq_enviado
            ON certum_rev_aviso_log (evento, res_model, res_id,
                                     COALESCE(clave, ''))
            WHERE estado = 'enviado'
        """)
        return res

    def _ya_enviado(self, evento, res_model, res_id, clave=None):
        return bool(self.sudo().search_count([
            ('evento', '=', evento), ('res_model', '=', res_model),
            ('res_id', '=', res_id), ('clave', '=', clave or False),
            ('estado', '=', 'enviado'),
        ]))
