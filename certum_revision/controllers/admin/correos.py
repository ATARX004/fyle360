# -*- coding: utf-8 -*-
"""Correos del panel de administración (solo Certum interno).

Rutas:

    GET   /my/certum/admin/correos                        -> pantalla, 5 pestañas
    GET   /my/certum/admin/correos/caso/<id>/vista-previa -> el correo pintado
    POST  /my/certum/admin/correos/caso/<id>/guardar      -> plantilla
    POST  /my/certum/admin/correos/caso/<id>/probar       -> correo de prueba
    POST  /my/certum/admin/correos/copias/<id>/guardar    -> copias de un cliente
    POST  /my/certum/admin/correos/remitente/guardar      -> servidor, nombre, pausa
    POST  /my/certum/admin/correos/envio/<id>/reintentar  -> uno fallido o atascado
    POST  /my/certum/admin/correos/reintentar-fallidos    -> todos los fallidos
    POST  /my/certum/admin/correos/recuperar              -> lo que el cron no mandó

El motor está en models/correo.py; aquí solo se enseña y se edita. Misma
metodología que los correos del e-learning (dv_custom_website_slides, T-30).

Las plantillas son iguales para toda la plataforma: salen de FYLE 360. Lo que
cambia por cliente son las copias (CC) de los correos de sus proyectos.

El servidor SMTP no se crea ni se edita aquí: se ELIGE uno de los ya
configurados en Odoo. Exponer credenciales SMTP en una pantalla web es
superficie de ataque que no compensa por una tarea que se hace una vez.

Recuperación nunca se fía de lo que llega del formulario: las claves marcadas
se cruzan con los candidatos que el servidor calcula en ese momento. Una
clave inventada o que ya se mandó no encola nada.
"""
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import fields, http
from odoo.http import request

from ...models.correo import (CONTACTO_POR_DEFECTO, CRON_COLA, CRON_DIARIO,
                              NOMBRE_POR_DEFECTO, PARAM_CONTACTO, PARAM_NOMBRE,
                              PARAM_PAUSA, PARAM_SERVIDOR, VARIABLES)
from ..helpers import ROL_CLIENTE
from .base import RUTA_ADMIN, AdminBase, auditar, responder

RUTA_CORREOS = RUTA_ADMIN + '/correos'
POR_PAGINA = 50

ESTADOS_ENVIO = [
    ('pendiente', 'Pendiente', 'neutro'),
    ('en_cola', 'En cola', 'neutro'),
    ('enviado', 'Enviado', 'ok'),
    ('fallido', 'Fallido', 'error'),
    ('cancelado', 'No se envió', 'alerta'),
]
ORIGENES = {'automatico': 'Automático', 'recuperacion': 'Recuperación', 'prueba': 'Prueba',
            'seguridad': 'Seguridad'}


def _entero(valor, defecto=0):
    try:
        return int(str(valor or '').strip())
    except (TypeError, ValueError):
        return defecto


def _fecha(momento):
    """Datetime UTC -> «23/10/2026 14:05» en hora de Lima."""
    if not momento:
        return ''
    return fields.Datetime.context_timestamp(
        request.env.user.with_context(tz='America/Lima'), momento).strftime('%d/%m/%Y %H:%M')


def _url_caso(caso, accion):
    return '%s/caso/%s/%s' % (RUTA_CORREOS, caso.id, accion)


def _fila_caso(caso, enviados):
    return {
        'id': caso.id,
        'codigo': caso.codigo,
        'nombre': caso.name,
        'cuando': caso.cuando or '',
        'para': caso.para or '',
        'activo': caso.activo,
        'obligatorio': caso.obligatorio,
        'asunto': caso.asunto or '',
        'texto': caso.texto or '',
        'boton': caso.boton or '',
        'dias': caso.dias or '',
        'dias_ayuda': caso.dias_ayuda or '',
        'enviados': enviados.get(caso.id, 0),
        'url_guardar': _url_caso(caso, 'guardar'),
        'url_previa': _url_caso(caso, 'vista-previa'),
        'url_probar': _url_caso(caso, 'probar'),
    }


def _fila_envio(envio):
    estados = {e[0]: e for e in ESTADOS_ENVIO}
    estado = estados.get(envio.estado, (envio.estado, envio.estado, 'neutro'))
    return {
        'id': envio.id,
        'fecha': _fecha(envio.fecha_envio or envio.create_date),
        'caso': envio.caso_id.name or '',
        'persona': envio.partner_id.name or '—',
        'email': envio.email or '',
        'cc': envio.email_cc or '',
        'proyecto': envio.proceso_id.name or envio.eliminacion_id.proyecto or '',
        'documento': envio.item_id.name or '',
        'estado': estado[1],
        'tono': estado[2],
        'motivo': envio.motivo or '',
        'origen': ORIGENES.get(envio.origen, envio.origen),
        'url_reintentar': ('%s/envio/%s/reintentar' % (RUTA_CORREOS, envio.id)
                           if envio.estado in ('fallido', 'pendiente', 'en_cola') else ''),
    }


def _cron(xmlid):
    cron = request.env.ref(xmlid, raise_if_not_found=False)
    if not cron:
        return {'existe': False}
    cron = cron.sudo()
    return {
        'existe': True,
        'activo': cron.active,
        'ultima': _fecha(cron.lastcall) or 'nunca',
        'proxima': _fecha(cron.nextcall),
        # Si la próxima pasada lleva más de dos horas en el pasado, el cron
        # no está corriendo: es lo primero que hay que mirar en Recuperación.
        'atrasado': bool(cron.active and cron.nextcall
                         and fields.Datetime.now() - cron.nextcall > timedelta(hours=2)),
    }


class AdminCorreos(AdminBase):

    # ─── Contexto ────────────────────────────────────────────────────────
    def _ctx_historial(self, kw):
        Envio = request.env['certum.rev.correo.envio'].sudo()
        dominio = []
        estado = kw.get('estado') or ''
        caso_id = _entero(kw.get('caso'))
        q = (kw.get('q') or '').strip()
        if estado in {e[0] for e in ESTADOS_ENVIO}:
            dominio.append(('estado', '=', estado))
        if caso_id:
            dominio.append(('caso_id', '=', caso_id))
        if q:
            dominio += ['|', '|', '|', ('partner_id.name', 'ilike', q), ('email', 'ilike', q),
                        ('proceso_id.name', 'ilike', q), ('item_id.name', 'ilike', q)]
        total = Envio.search_count(dominio)
        paginas_total = max((total + POR_PAGINA - 1) // POR_PAGINA, 1)
        pagina = min(max(_entero(kw.get('pagina'), 1), 1), paginas_total)
        envios = Envio.search(dominio, limit=POR_PAGINA, offset=(pagina - 1) * POR_PAGINA)
        envios.filtered(lambda e: e.estado == 'en_cola')._sincronizar()
        base = {'estado': estado, 'caso': caso_id or '', 'q': q}
        paginas = []
        if paginas_total > 1:
            for numero in range(1, paginas_total + 1):
                params = dict(base, pagina=numero)
                consulta = '&'.join('%s=%s' % (k, v) for k, v in params.items() if v)
                paginas.append({'numero': numero, 'activa': numero == pagina,
                                'url': '%s?%s#historial' % (RUTA_CORREOS, consulta)})
        return {
            'historial': [_fila_envio(e) for e in envios],
            'historial_total': total,
            'historial_paginas': paginas,
            'filtro_estado': estado,
            'filtro_caso': caso_id,
            'filtro_q': q,
            'estados_envio': ESTADOS_ENVIO,
        }

    def _ctx_recuperacion(self):
        Envio = request.env['certum.rev.correo.envio'].sudo()
        ahora = fields.Datetime.now()
        fallidos = Envio.search([('estado', '=', 'fallido'), ('origen', 'not in', ('prueba', 'seguridad'))], limit=200)
        atascados = Envio.search(['|',
                                  '&', ('estado', '=', 'pendiente'), ('create_date', '<', ahora - timedelta(minutes=30)),
                                  '&', ('estado', '=', 'en_cola'), ('write_date', '<', ahora - timedelta(hours=2))],
                                 limit=200)
        candidatos = []
        for c in Envio._candidatos()[:300]:
            registro = c['registro']
            item = registro if registro._name == 'certum.rev.item' else None
            proceso = registro if registro._name == 'certum.rev.proceso' else registro.proceso_id
            candidatos.append({
                'clave': c['clave'],
                'caso': c['caso'].name,
                'persona': c['partner'].name or '',
                'email': c['partner'].email or '',
                'proyecto': proceso.name or '',
                'documento': item.name if item else '',
                'sin_correo': not c['partner'].email,
            })
        return {
            'fallidos': [_fila_envio(e) for e in fallidos],
            'atascados': [_fila_envio(e) for e in atascados],
            'candidatos': candidatos,
            'cron_cola': _cron(CRON_COLA),
            'cron_diario': _cron(CRON_DIARIO),
            'pausado': Envio._pausado(),
        }

    def _ctx_remitente(self):
        Param = request.env['ir.config_parameter'].sudo()
        Envio = request.env['certum.rev.correo.envio'].sudo()
        servidores = request.env['ir.mail_server'].sudo().with_context(active_test=False).search(
            [], order='active desc, sequence, id')
        return {
            'servidores': [{
                'id': s.id,
                'nombre': s.name,
                'buzon': Envio._buzon(s),
                'activo': s.active,
            } for s in servidores],
            'servidor_elegido': _entero(Param.get_param(PARAM_SERVIDOR)),
            'nombre_remitente': Param.get_param(PARAM_NOMBRE) or NOMBRE_POR_DEFECTO,
            'contacto_correos': Param.get_param(PARAM_CONTACTO) or CONTACTO_POR_DEFECTO,
            'remitente_actual': Envio._remitente(),
            'pausado': Envio._pausado(),
        }

    def _ctx_copias(self):
        clientes = request.env['res.partner'].sudo().search(
            [('is_company', '=', True), ('rol_en_certum', '=', ROL_CLIENTE)], order='name')
        Proceso = request.env['certum.rev.proceso'].sudo()
        return {'clientes_copias': [{
            'id': c.id,
            'nombre': c.name,
            'cc': c.certum_correo_cc or '',
            'proyectos': Proceso.search_count([('cliente_id', '=', c.id),
                                               ('state', 'in', ('publicacion', 'revision'))]),
            'url': '%s/copias/%s/guardar' % (RUTA_CORREOS, c.id),
        } for c in clientes]}

    def _ctx_correos(self, kw):
        Envio = request.env['certum.rev.correo.envio'].sudo()
        hace_30 = fields.Datetime.now() - timedelta(days=30)
        enviados = {caso.id: total for caso, total in Envio._read_group(
            [('estado', '=', 'enviado'), ('create_date', '>=', hace_30)], ['caso_id'], ['__count'])}
        casos = request.env['certum.rev.correo.caso'].sudo().search([])
        ctx = dict(
            casos=[_fila_caso(c, enviados) for c in casos],
            variables=VARIABLES,
            kpi_enviados=sum(enviados.values()),
            kpi_fallidos=Envio.search_count([('estado', '=', 'fallido'), ('origen', 'not in', ('prueba', 'seguridad'))]),
            kpi_cola=Envio.search_count([('estado', 'in', ('pendiente', 'en_cola'))]),
            kpi_activos=len(casos.filtered('activo')),
            hay_servidor=bool(request.env['ir.mail_server'].sudo().search_count([])),
            url_correos=RUTA_CORREOS,
            url_remitente=RUTA_CORREOS + '/remitente/guardar',
            url_recuperar=RUTA_CORREOS + '/recuperar',
            url_reintentar_fallidos=RUTA_CORREOS + '/reintentar-fallidos',
        )
        ctx.update(self._ctx_historial(kw))
        ctx.update(self._ctx_recuperacion())
        ctx.update(self._ctx_remitente())
        ctx.update(self._ctx_copias())
        return ctx

    def _fragmentos(self):
        """Tras una acción, los trozos que cambian: indicadores, historial y
        recuperación. Las plantillas no: cada una se guarda sola."""
        valores = self._ctx('correos', **self._ctx_correos({}))
        pintar = request.env['ir.ui.view']._render_template
        return {
            'kpis_correos': str(pintar('certum_revision.admin_correos_kpis', valores)),
            'historial_correos': str(pintar('certum_revision.admin_correos_historial', valores)),
            'recuperacion_correos': str(pintar('certum_revision.admin_correos_recuperacion', valores)),
        }

    # ─── Pantalla ────────────────────────────────────────────────────────
    @http.route(RUTA_CORREOS, type='http', auth='user', website=True, sitemap=False)
    def admin_correos(self, **kw):
        guard = self._guard()
        if guard:
            return guard
        return request.render('certum_revision.admin_correos',
                              self._ctx('correos', **self._ctx_correos(kw)))

    @http.route(RUTA_CORREOS + '/caso/<int:caso_id>/vista-previa', type='http', auth='user',
                website=True, sitemap=False)
    def admin_correos_vista_previa(self, caso_id, **kw):
        guard = self._guard()
        if guard:
            return guard
        caso = request.env['certum.rev.correo.caso'].sudo().browse(caso_id).exists()
        if not caso:
            return request.not_found()
        asunto, cuerpo = request.env['certum.rev.correo.envio'].sudo()._vista_previa(
            caso, request.env.user.partner_id)
        pagina = Markup('<!DOCTYPE html><html><head><meta charset="utf-8"/>'
                        '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
                        '<title>%s</title></head><body style="margin:0">%s</body></html>') % (asunto, cuerpo)
        return request.make_response(str(pagina), headers=[('Content-Type', 'text/html; charset=utf-8')])

    # ─── Plantillas ──────────────────────────────────────────────────────
    @http.route(RUTA_CORREOS + '/caso/<int:caso_id>/guardar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_correos_guardar_caso(self, caso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        caso = request.env['certum.rev.correo.caso'].sudo().browse(caso_id).exists()
        if not caso:
            return responder(RUTA_CORREOS, error='Esa plantilla ya no existe.')
        errores = {}
        asunto = ' '.join((post.get('asunto') or '').split())
        texto = (post.get('texto') or '').replace('\r\n', '\n').strip()
        if not asunto:
            errores['asunto'] = 'El asunto no puede quedar vacío.'
        if not texto:
            errores['texto'] = 'El correo necesita un texto.'
        valores = {
            # Un correo de seguridad no se apaga: sin él no se podría confirmar
            # la acción que protege.
            'activo': bool(post.get('activo')) or caso.obligatorio,
            'asunto': asunto,
            'texto': texto,
            'boton': ' '.join((post.get('boton') or '').split()),
        }
        if caso.dias_ayuda:
            dias = _entero(post.get('dias'), -1)
            if dias < 1 or dias > 60:
                errores['dias'] = 'Escriba un número de días entre 1 y 60.'
            valores['dias'] = dias
        if errores:
            return responder(RUTA_CORREOS + '#plantillas', error='Revise los campos marcados.',
                             errores=errores)
        caso.write(valores)
        auditar('correo_plantilla_guardada', caso=caso.codigo, activo=caso.activo)
        estado = 'activa' if caso.activo else 'desactivada'
        return responder(RUTA_CORREOS + '#plantillas',
                         ok='Plantilla «%s» guardada (%s).' % (caso.name, estado),
                         fragmentos=self._fragmentos)

    @http.route(RUTA_CORREOS + '/caso/<int:caso_id>/probar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_correos_probar(self, caso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        caso = request.env['certum.rev.correo.caso'].sudo().browse(caso_id).exists()
        email = (post.get('email') or '').strip()
        if not caso:
            return responder(RUTA_CORREOS, error='Esa plantilla ya no existe.')
        if '@' not in email or ' ' in email or len(email) > 200:
            return responder(RUTA_CORREOS + '#plantillas', error='Escriba un correo válido para la prueba.',
                             errores={'email': 'Correo no válido.'})
        envio = request.env['certum.rev.correo.envio'].sudo()._enviar_prueba(
            caso, email, request.env.user.partner_id)
        auditar('correo_prueba', caso=caso.codigo, envio=envio.id)
        if envio.estado == 'fallido':
            return responder(RUTA_CORREOS + '#plantillas',
                             error='La prueba no salió: %s' % (envio.motivo or 'error del servidor de correo'),
                             fragmentos=self._fragmentos)
        return responder(RUTA_CORREOS + '#plantillas',
                         ok='Prueba de «%s» enviada a %s.' % (caso.name, email),
                         fragmentos=self._fragmentos)

    # ─── Copias por cliente ──────────────────────────────────────────────
    @http.route(RUTA_CORREOS + '/copias/<int:partner_id>/guardar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_correos_copias(self, partner_id, **post):
        guard = self._guard()
        if guard:
            return guard
        cliente = request.env['res.partner'].sudo().browse(partner_id).exists()
        if not cliente or not cliente.is_company or cliente.rol_en_certum != ROL_CLIENTE:
            return responder(RUTA_CORREOS + '#copias', error='Las copias se configuran solo en empresas cliente.')
        crudo = post.get('cc') or ''
        Envio = request.env['certum.rev.correo.envio'].sudo()
        validos = Envio._parsear(crudo)
        sobrantes = [p for p in crudo.replace(';', ',').replace('\n', ',').split(',')
                     if p.strip() and p.strip().lower() not in validos]
        if sobrantes:
            return responder(RUTA_CORREOS + '#copias',
                             error='Estos correos no son válidos: %s' % ', '.join(s.strip() for s in sobrantes[:5]),
                             errores={'cc_%s' % cliente.id: 'Revise las direcciones.'})
        if len(validos) > 10:
            return responder(RUTA_CORREOS + '#copias', error='Como mucho 10 direcciones en copia por cliente.',
                             errores={'cc_%s' % cliente.id: 'Demasiadas direcciones.'})
        cliente.write({'certum_correo_cc': ', '.join(validos) or False})
        auditar('correo_copias', cliente=cliente.id, n=len(validos))
        if not validos:
            return responder(RUTA_CORREOS + '#copias', ok='%s ya no recibe copias.' % cliente.name)
        return responder(RUTA_CORREOS + '#copias',
                         ok='Copias de %s guardadas: %s.' % (cliente.name, ', '.join(validos)))

    # ─── Remitente ───────────────────────────────────────────────────────
    @http.route(RUTA_CORREOS + '/remitente/guardar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_correos_remitente(self, **post):
        guard = self._guard()
        if guard:
            return guard
        errores = {}
        servidor_id = _entero(post.get('servidor_id'))
        if servidor_id:
            servidor = request.env['ir.mail_server'].sudo().browse(servidor_id).exists()
            if not servidor:
                errores['servidor_id'] = 'Ese servidor ya no existe.'
            elif not servidor.active:
                errores['servidor_id'] = 'Ese servidor está desactivado en Odoo: actívelo antes de usarlo.'
        nombre = ' '.join((post.get('nombre') or '').split()) or NOMBRE_POR_DEFECTO
        contacto = (post.get('contacto') or '').strip() or CONTACTO_POR_DEFECTO
        if '@' not in contacto or ' ' in contacto:
            errores['contacto'] = 'Escriba un correo válido.'
        if len(nombre) > 80:
            errores['nombre'] = 'Como mucho 80 caracteres.'
        if errores:
            return responder(RUTA_CORREOS + '#remitente', error='Revise los campos marcados.',
                             errores=errores)
        pausado = post.get('automatico') != '1'
        Param = request.env['ir.config_parameter'].sudo()
        Param.set_param(PARAM_SERVIDOR, str(servidor_id) if servidor_id else '')
        Param.set_param(PARAM_NOMBRE, nombre)
        Param.set_param(PARAM_CONTACTO, contacto)
        Param.set_param(PARAM_PAUSA, '1' if pausado else '0')
        auditar('correo_remitente', servidor=servidor_id, nombre=nombre, contacto=contacto,
                pausado=pausado)
        remitente = request.env['certum.rev.correo.envio'].sudo()._remitente()
        mensaje = 'Remitente guardado: los correos saldrán como %s.' % remitente
        if pausado:
            mensaje = 'Envío automático en pausa. Remitente: %s.' % remitente
        return responder(RUTA_CORREOS + '#remitente', ok=mensaje,
                         fragmentos=lambda: dict(self._fragmentos(),
                                                 remitente_actual=str(escape(remitente))))

    # ─── Recuperación ────────────────────────────────────────────────────
    @http.route(RUTA_CORREOS + '/envio/<int:envio_id>/reintentar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_correos_reintentar(self, envio_id, **post):
        guard = self._guard()
        if guard:
            return guard
        envio = request.env['certum.rev.correo.envio'].sudo().browse(envio_id).exists()
        if not envio or envio.estado not in ('fallido', 'pendiente', 'en_cola'):
            return responder(RUTA_CORREOS + '#recuperacion', error='Ese correo no está pendiente ni fallido.')
        if envio.estado == 'en_cola' and envio.mail_id:
            envio.mail_id.send(raise_exception=False)
            envio._sincronizar()
        else:
            envio._procesar(forzar_envio=True)
        auditar('correo_reintento', envio=envio.id, estado=envio.estado)
        return self._resultado([envio])

    @http.route(RUTA_CORREOS + '/reintentar-fallidos', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_correos_reintentar_fallidos(self, **post):
        guard = self._guard()
        if guard:
            return guard
        # Como mucho 50 por pulsación: se mandan dentro de esta petición.
        fallidos = request.env['certum.rev.correo.envio'].sudo().search(
            [('estado', '=', 'fallido'), ('origen', 'not in', ('prueba', 'seguridad'))], limit=50)
        if not fallidos:
            return responder(RUTA_CORREOS + '#recuperacion', error='No hay correos fallidos.')
        fallidos._procesar(forzar_envio=True)
        auditar('correo_reintento_lote', envios=','.join(str(i) for i in fallidos.ids))
        return self._resultado(fallidos)

    @http.route(RUTA_CORREOS + '/recuperar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_correos_recuperar(self, **post):
        guard = self._guard()
        if guard:
            return guard
        pedidas = set(request.httprequest.form.getlist('clave'))
        if not pedidas:
            return responder(RUTA_CORREOS + '#recuperacion', error='Marque al menos un correo para enviar.')
        Envio = request.env['certum.rev.correo.envio'].sudo()
        envios = Envio.browse()
        for candidato in Envio._candidatos():
            if candidato['clave'] not in pedidas or len(envios) >= 50:
                continue
            envios |= Envio.encolar(candidato['codigo'], candidato['registro'], candidato['partner'],
                                    candidato.get('referencia', ''), origen='recuperacion')
        if not envios:
            return responder(RUTA_CORREOS + '#recuperacion',
                             error='Ninguno de los marcados sigue pendiente: ya se enviaron o dejaron de corresponder.')
        envios.filtered(lambda e: e.estado == 'pendiente')._procesar(forzar_envio=True)
        auditar('correo_recuperacion', envios=','.join(str(i) for i in envios.ids))
        return self._resultado(envios)

    def _resultado(self, envios):
        enviados = sum(1 for e in envios if e.estado in ('enviado', 'en_cola'))
        fallidos = sum(1 for e in envios if e.estado == 'fallido')
        omitidos = len(envios) - enviados - fallidos
        partes = ['%d enviado(s)' % enviados]
        if fallidos:
            partes.append('%d fallido(s)' % fallidos)
        if omitidos:
            partes.append('%d ya no correspondían' % omitidos)
        mensaje = ', '.join(partes) + '.'
        if fallidos and not enviados:
            return responder(RUTA_CORREOS + '#recuperacion', error='No salió ninguno: ' + mensaje,
                             fragmentos=self._fragmentos)
        return responder(RUTA_CORREOS + '#recuperacion', ok=mensaje,
                         fragmentos=self._fragmentos)
