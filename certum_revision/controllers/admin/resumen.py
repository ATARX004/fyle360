# -*- coding: utf-8 -*-
"""Resumen y Proyectos del panel de administración.

Rutas:

    GET   /my/certum/admin                              -> resumen: lo que pide atención
    GET   /my/certum/admin/proyectos                    -> todos los proyectos, con filtros
    POST  /my/certum/admin/proyecto/<id>/abrir          -> abre un borrador
    POST  /my/certum/admin/proyecto/<id>/fuera-plazo    -> lo marca fuera de plazo

Sustituye a la lista y la ficha de proyectos del backend de Odoo: el detalle
de cada proyecto es el mismo que ven proveedor y cliente (/my/proceso/<id>),
donde el interno entra como supervisor.
"""
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .base import RUTA_ADMIN, AdminBase, auditar, responder

RUTA_PROYECTOS = RUTA_ADMIN + '/proyectos'
POR_PAGINA = 30

ESTADOS = [
    ('borrador', 'Borrador'),
    ('publicacion', 'Publicación'),
    ('revision', 'Revisión'),
    ('completado', 'Completado'),
    ('fuera_plazo', 'Fuera de plazo'),
]


def _entero(valor, defecto=0):
    try:
        return int(str(valor or '').strip())
    except (TypeError, ValueError):
        return defecto


class AdminResumen(AdminBase):

    # ─── Resumen ─────────────────────────────────────────────────────────
    @http.route(RUTA_ADMIN, type='http', auth='user', website=True, sitemap=False)
    def admin_resumen(self, **kw):
        guard = self._guard()
        if guard:
            return guard
        Proceso = request.env['certum.rev.proceso'].sudo()
        Item = request.env['certum.rev.item'].sudo()
        Envio = request.env['certum.rev.correo.envio'].sudo()

        activos = Proceso.search([('state', 'in', ('publicacion', 'revision'))],
                                 order='fecha_vencimiento asc')
        listos = activos.filtered(lambda p: p.listo_para_cerrar())
        criticos = activos.filtered(lambda p: p.semaforo == 'critico')
        fuera = Proceso.search([('state', '=', 'fuera_plazo')])
        ahora = fields.Datetime.now()
        por_vencer = Item.search_count([
            ('state', '=', 'publicado'),
            ('proceso_id.state', 'in', ('publicacion', 'revision')),
            ('fecha_limite_revision', '>', ahora),
            ('fecha_limite_revision', '<=', ahora + timedelta(days=2))])
        fallidos = Envio.search_count([('estado', '=', 'fallido'), ('origen', '!=', 'prueba')])
        sin_rol = request.env['res.partner'].sudo().search_count([
            ('is_company', '=', True), ('rol_en_certum', 'in', (False, '')),
            ('child_ids.user_ids.share', '=', True)])

        # Lo que pide una acción, en el orden en que conviene atenderlo.
        atencion = []
        if not request.env['ir.mail_server'].sudo().search_count([]):
            atencion.append({
                'tono': 'danger', 'icono': 'i-alert',
                'titulo': 'No hay servidor de correo saliente',
                'texto': 'Ningún aviso llegará a su destino hasta que se configure uno en Odoo.',
                'url': RUTA_ADMIN + '/correos#remitente', 'accion': 'Revisar remitente'})
        if fallidos:
            atencion.append({
                'tono': 'danger', 'icono': 'i-send',
                'titulo': '%d correo(s) fallido(s)' % fallidos,
                'texto': 'El servidor los rechazó o no se pudieron preparar.',
                'url': RUTA_ADMIN + '/correos#recuperacion', 'accion': 'Recuperar'})
        if fuera:
            atencion.append({
                'tono': 'danger', 'icono': 'i-clock',
                'titulo': '%d proyecto(s) fuera de plazo' % len(fuera),
                'texto': 'Venció su plazo general sin terminar la revisión.',
                'url': RUTA_PROYECTOS + '?estado=fuera_plazo', 'accion': 'Ver proyectos'})
        if por_vencer:
            atencion.append({
                'tono': 'warn', 'icono': 'i-eye',
                'titulo': '%d revisión(es) vencen en 48 horas' % por_vencer,
                'texto': 'Si vencen sin decisión, el documento se aprueba solo.',
                'url': RUTA_PROYECTOS + '?estado=revision', 'accion': 'Ver proyectos'})
        if listos:
            atencion.append({
                'tono': 'ok', 'icono': 'i-check-circle',
                'titulo': '%d proyecto(s) listos para cerrar' % len(listos),
                'texto': 'Todo lo obligatorio está aprobado; falta que el proveedor lo cierre.',
                'url': RUTA_PROYECTOS + '?estado=listos', 'accion': 'Ver cuáles'})
        if sin_rol:
            atencion.append({
                'tono': 'warn', 'icono': 'i-building',
                'titulo': '%d empresa(s) con usuarios y sin rol' % sin_rol,
                'texto': 'Sus usuarios entran al portal pero no ven nada.',
                'url': RUTA_ADMIN + '/empresas', 'accion': 'Asignar rol'})

        cifras = [
            {'valor': len(activos), 'etiqueta': 'proyectos en curso'},
            {'valor': Item.search_count([('state', '=', 'publicado'),
                                         ('proceso_id.state', 'in', ('publicacion', 'revision'))]),
             'etiqueta': 'documentos esperando revisión'},
            {'valor': len(criticos), 'etiqueta': 'en semáforo crítico'},
            {'valor': Proceso.search_count([('state', '=', 'completado')]),
             'etiqueta': 'cerrados'},
        ]
        return request.render('certum_revision.admin_resumen', self._ctx(
            'resumen', atencion=atencion, cifras=cifras,
            proximos=activos[:6]))

    # ─── Proyectos ───────────────────────────────────────────────────────
    @http.route(RUTA_PROYECTOS, type='http', auth='user', website=True, sitemap=False)
    def admin_proyectos(self, **kw):
        guard = self._guard()
        if guard:
            return guard
        Proceso = request.env['certum.rev.proceso'].sudo()
        dominio = []
        estado = kw.get('estado') or ''
        q = (kw.get('q') or '').strip()
        if estado in dict(ESTADOS):
            dominio.append(('state', '=', estado))
        elif estado == 'listos':
            dominio.append(('state', 'in', ('publicacion', 'revision')))
        if q:
            dominio += ['|', '|', '|', ('name', 'ilike', q), ('referencia', 'ilike', q),
                        ('proveedor_id.name', 'ilike', q), ('cliente_id.name', 'ilike', q)]
        procesos = Proceso.search(dominio, order='fecha_vencimiento asc, id desc')
        if estado == 'listos':
            procesos = procesos.filtered(lambda p: p.listo_para_cerrar())
        total = len(procesos)
        paginas_total = max((total + POR_PAGINA - 1) // POR_PAGINA, 1)
        pagina = min(max(_entero(kw.get('pagina'), 1), 1), paginas_total)
        visibles = procesos[(pagina - 1) * POR_PAGINA:pagina * POR_PAGINA]
        paginas = []
        if paginas_total > 1:
            for numero in range(1, paginas_total + 1):
                params = {'estado': estado, 'q': q, 'pagina': numero}
                consulta = '&'.join('%s=%s' % (k, v) for k, v in params.items() if v)
                paginas.append({'numero': numero, 'activa': numero == pagina,
                                'url': '%s?%s' % (RUTA_PROYECTOS, consulta)})
        conteo = {e: Proceso.search_count([('state', '=', e)]) for e, _n in ESTADOS}
        return request.render('certum_revision.admin_proyectos', self._ctx(
            'proyectos', procesos=visibles, total=total, paginas=paginas,
            filtro_estado=estado, filtro_q=q, estados=ESTADOS, conteo=conteo))

    def _proyecto(self, proceso_id):
        return request.env['certum.rev.proceso'].sudo().browse(proceso_id).exists()

    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>/abrir', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_proyecto_abrir(self, proceso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso:
            return responder(RUTA_PROYECTOS, error='Ese proyecto ya no existe.')
        try:
            proceso.action_abrir()
        except (UserError, ValidationError) as exc:
            return responder(RUTA_PROYECTOS, error=str(exc.args[0] if exc.args else exc))
        auditar('proyecto_abierto', proceso=proceso.id)
        return responder(RUTA_PROYECTOS, ok='Proyecto %s abierto: el proveedor ya puede publicar.' % proceso.name)

    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>/fuera-plazo', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_proyecto_fuera_plazo(self, proceso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso or proceso.state not in ('publicacion', 'revision'):
            return responder(RUTA_PROYECTOS, error='Solo un proyecto en curso se puede marcar fuera de plazo.')
        proceso.action_marcar_fuera_plazo()
        auditar('proyecto_fuera_plazo', proceso=proceso.id)
        return responder(RUTA_PROYECTOS, ok='Proyecto %s marcado fuera de plazo.' % proceso.name)
