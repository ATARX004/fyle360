# -*- coding: utf-8 -*-
"""Panel de configuración de los avisos por correo (solo Certum interno).

Qué se puede hacer aquí y qué no, y por qué:

  - **Sí**: elegir el servidor de correo saliente entre los ya creados, fijar
    el remitente y la copia global, activar o desactivar cada aviso, mandar
    una prueba y consultar el historial de envíos.
  - **No**: crear o editar el servidor SMTP (host, usuario, contraseña). Eso
    se hace una sola vez en Ajustes → Técnico → Servidores de correo saliente.
    Exponer credenciales SMTP en una pantalla web es superficie de ataque que
    no compensa por una tarea que se hace una vez.
"""
import logging

from odoo import http
from odoo.http import request

from ..helpers import _es_interno, is_ajax, json_err, json_r

_logger = logging.getLogger(__name__)

PREFIJO = 'certum_revision.aviso_'


class CertumRevCorreos(http.Controller):

    def _guard(self):
        """Solo Certum interno. Devuelve None si puede, o una respuesta si no."""
        if not _es_interno():
            return request.redirect('/my/certum')
        return None

    @http.route('/my/certum/admin/correos', type='http', auth='user',
                website=True)
    def panel(self, **kw):
        bloqueo = self._guard()
        if bloqueo:
            return bloqueo
        cfg = request.env['certum.rev.aviso.config']
        Log = request.env['certum.rev.aviso.log'].sudo()
        icp = request.env['ir.config_parameter'].sudo()

        eventos = cfg.eventos()
        for ev in eventos:
            ev['enviados'] = Log.search_count([('evento', '=', ev['code']),
                                               ('estado', '=', 'enviado')])
            ev['fallidos'] = Log.search_count([('evento', '=', ev['code']),
                                               ('estado', '=', 'fallido')])
            ultimo = Log.search([('evento', '=', ev['code']),
                                 ('estado', 'in', ('enviado', 'prueba'))],
                                order='fecha desc', limit=1)
            ev['ultimo'] = ultimo.fecha or False

        return request.render('certum_revision.admin_correos', {
            'eventos': eventos,
            'servidores': request.env['ir.mail_server'].sudo().search([]),
            'cfg': {
                'enviar': cfg.envio_general(),
                'from_email': icp.get_param(PREFIJO + 'from_email', '') or '',
                'from_name': icp.get_param(PREFIJO + 'from_name', '') or '',
                'cc': icp.get_param(PREFIJO + 'cc', '') or '',
                'mail_server_id': cfg.mail_server_id(),
                'dias_preaviso': cfg.dias_preaviso(),
                'prueba_a': (icp.get_param(PREFIJO + 'prueba_a', '')
                             or request.env.user.email or ''),
            },
            # Sin servidor saliente NINGUN correo sale, y se queda en la cola
            # como fallido sin que nadie se entere. Es el fallo mas silencioso
            # del sistema, asi que el panel lo avisa en grande.
            'hay_servidor': cfg.hay_servidor(),
            'ultimos': Log.search([], order='fecha desc', limit=25),
            'pendientes_cola': request.env['mail.mail'].sudo().search_count(
                [('state', '=', 'exception')]),
        })

    @http.route('/my/certum/admin/correos/guardar', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def guardar(self, **post):
        bloqueo = self._guard()
        if bloqueo:
            return bloqueo
        cfg = request.env['certum.rev.aviso.config']
        icp = request.env['ir.config_parameter'].sudo()

        correo = (post.get('from_email') or '').strip()
        if correo and not cfg.parsear(correo):
            return json_err('El correo del remitente no es válido.')
        cc = (post.get('cc') or '').strip()

        servidor = (post.get('mail_server_id') or '').strip()
        if servidor:
            if not servidor.isdigit() or not request.env['ir.mail_server'] \
                    .sudo().browse(int(servidor)).exists():
                return json_err('El servidor de correo indicado no existe.')

        try:
            dias = max(1, min(30, int(post.get('dias_preaviso') or 2)))
        except (TypeError, ValueError):
            dias = 2

        icp.set_param(PREFIJO + 'enviar',
                      '1' if post.get('enviar') == '1' else '0')
        icp.set_param(PREFIJO + 'from_email', correo)
        icp.set_param(PREFIJO + 'from_name', (post.get('from_name') or '').strip())
        icp.set_param(PREFIJO + 'cc', ', '.join(cfg.parsear(cc)))
        icp.set_param(PREFIJO + 'mail_server_id', servidor or '0')
        icp.set_param(PREFIJO + 'dias_preaviso', str(dias))

        # Interruptor por evento: llega la lista de los ACTIVOS.
        activos = set((post.get('activos') or '').split(','))
        for ev in cfg.eventos():
            icp.set_param('%sev_%s' % (PREFIJO, ev['code']),
                          '1' if ev['code'] in activos else '0')

        _logger.info('[AUDIT] correos_guardar user=%s enviar=%s servidor=%s',
                     request.env.user.id, post.get('enviar'), servidor)
        if is_ajax():
            return json_r({'ok': True})
        return request.redirect('/my/certum/admin/correos')

    @http.route('/my/certum/admin/correos/prueba', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def prueba(self, **post):
        """Manda un aviso real a una dirección de prueba.

        Usa un registro de verdad —el proyecto más reciente— porque una
        plantilla puede fallar precisamente al pintar los datos, y una prueba
        con datos inventados no lo detectaría.
        """
        bloqueo = self._guard()
        if bloqueo:
            return bloqueo
        cfg = request.env['certum.rev.aviso.config']
        destino = cfg.parsear(post.get('para') or '')
        if not destino:
            return json_err('Indica una dirección de correo válida.')
        request.env['ir.config_parameter'].sudo().set_param(
            PREFIJO + 'prueba_a', destino[0])

        proceso = request.env['certum.rev.proceso'].sudo().search(
            [], order='id desc', limit=1)
        if not proceso:
            return json_err('Todavía no hay ningún proyecto con el que probar.')

        log = request.env['certum.rev.aviso'].enviar(
            'publicado', proceso.item_ids[:1] or proceso,
            'certum_revision.template_item_publicado', destino,
            clave='prueba', forzar=True)
        if not log or log.estado == 'fallido':
            return json_err('No se pudo enviar: %s'
                            % ((log and log.error) or 'error desconocido'))
        if not cfg.hay_servidor():
            return json_err('El correo se encoló, pero NO hay servidor de '
                            'correo saliente configurado: no llegará a '
                            'ninguna parte hasta que se cree uno.', 200)
        return json_r({'ok': True,
                       'mensaje': 'Correo de prueba encolado a %s. Si no '
                                  'llega, revisa la cola en Ajustes → Técnico '
                                  '→ Correos electrónicos.' % destino[0]})
