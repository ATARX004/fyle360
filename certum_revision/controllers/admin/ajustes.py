# -*- coding: utf-8 -*-
"""Ajustes del panel de administración: plazos y tareas programadas.

Rutas:

    GET   /my/certum/admin/ajustes                       -> pantalla
    POST  /my/certum/admin/ajustes/guardar               -> plazos y límites
    POST  /my/certum/admin/ajustes/cron/<id>/ejecutar    -> correr una tarea ya
    POST  /my/certum/admin/ajustes/cron/<id>/activar     -> encenderla o apagarla

Hasta ahora estos valores se tocaban en Ajustes → Técnico → Parámetros del
sistema, a ciegas y sin validación. Aquí cada uno dice qué hace y tiene sus
límites. Las tareas se pueden lanzar a mano: es la recuperación cuando un
cron no corrió (servidor reiniciado, worker caído).
"""
from odoo import fields, http
from odoo.http import request

from .base import RUTA_ADMIN, AdminBase, auditar, responder

RUTA_AJUSTES = RUTA_ADMIN + '/ajustes'

# (clave, etiqueta, ayuda, defecto, mínimo, máximo)
PARAMETROS = [
    ('certum_revision.plazo_dias', 'Plazo de un proyecto', 'Días desde la fecha de inicio. '
     'Es el valor que se propone al iniciar un proyecto.', 30, 1, 3650),
    ('certum_revision.dias_correccion', 'Días para corregir', 'Días que tiene el proveedor '
     'para subir la corrección de un documento observado.', 3, 1, 60),
    ('certum_revision.dias_urgente', 'Semáforo urgente', 'Faltando estos días o menos, el '
     'proyecto pasa a «Urgente».', 7, 1, 90),
    ('certum_revision.dias_critico', 'Semáforo crítico', 'Faltando estos días o menos, el '
     'proyecto pasa a «Crítico». Debe ser menor que el urgente.', 3, 0, 60),
    ('certum_revision.max_upload_mb', 'Tamaño máximo por archivo', 'En MB. Lo que pase de '
     'aquí se rechaza al publicar.', 50, 1, 500),
    ('certum_revision.max_zip_mb', 'Tope del paquete ZIP', 'En MB. Evita agotar la memoria '
     'del servidor al descargar un proyecto entero.', 200, 10, 2000),
    ('certum_revision.dias_purga_versiones', 'Conservar versiones superadas', 'Días antes de '
     'borrar el contenido de las versiones que ya no son la vigente.', 10, 1, 365),
]

# Tareas programadas del módulo, con lo que hacen en palabras de negocio.
CRONS = [
    ('certum_revision.cron_correos_enviar', 'Cola de correos',
     'Manda lo encolado. Se despierta sola cuando algo se encola.'),
    ('certum_revision.cron_correos_diario', 'Avisos del día',
     'Plazos por vencer y resumen de pendientes, cada mañana.'),
    ('certum_revision.cron_auto_aprobar_revision', 'Vencimiento de revisiones',
     'Pasa el turno al siguiente revisor o aprueba lo que venció sin revisar.'),
    ('certum_revision.cron_control_plazo', 'Control de plazo',
     'Marca fuera de plazo los proyectos vencidos.'),
    ('certum_revision.cron_abrir_procesos', 'Apertura automática',
     'Abre los borradores que ya deberían estar en curso.'),
    ('certum_revision.cron_purgar_versiones', 'Depurar versiones',
     'Borra el contenido de las versiones superadas antiguas.'),
]

# En español sea cual sea el idioma del usuario: el panel no se traduce.
UNIDADES = {'minutes': 'minutos', 'hours': 'horas', 'days': 'días',
            'weeks': 'semanas', 'months': 'meses'}


def _fecha(momento):
    if not momento:
        return ''
    return fields.Datetime.context_timestamp(
        request.env.user.with_context(tz='America/Lima'), momento).strftime('%d/%m/%Y %H:%M')


class AdminAjustes(AdminBase):

    def _crons(self):
        filas = []
        for xmlid, nombre, ayuda in CRONS:
            cron = request.env.ref(xmlid, raise_if_not_found=False)
            if not cron:
                continue
            cron = cron.sudo().with_context(active_test=False)
            intervalo = UNIDADES.get(cron.interval_type, cron.interval_type)
            filas.append({
                'id': cron.id,
                'nombre': nombre,
                'ayuda': ayuda,
                'activo': cron.active,
                'cada': '%s %s' % (cron.interval_number, intervalo),
                'ultima': _fecha(cron.lastcall) or 'nunca',
                'proxima': _fecha(cron.nextcall),
                'url_ejecutar': '%s/cron/%s/ejecutar' % (RUTA_AJUSTES, cron.id),
                'url_activar': '%s/cron/%s/activar' % (RUTA_AJUSTES, cron.id),
            })
        return filas

    def _cron_del_modulo(self, cron_id):
        """Solo las tareas de este módulo: el panel no es un lanzador de
        cualquier cron de la base."""
        for xmlid, _n, _a in CRONS:
            cron = request.env.ref(xmlid, raise_if_not_found=False)
            if cron and cron.id == cron_id:
                return cron.sudo()
        return None

    @http.route(RUTA_AJUSTES, type='http', auth='user', website=True, sitemap=False)
    def admin_ajustes(self, **kw):
        guard = self._guard()
        if guard:
            return guard
        Param = request.env['ir.config_parameter'].sudo()
        parametros = [{
            'clave': clave, 'nombre': nombre, 'ayuda': ayuda, 'min': minimo, 'max': maximo,
            'campo': clave.split('.')[-1],
            'valor': Param.get_param(clave) or defecto,
        } for clave, nombre, ayuda, defecto, minimo, maximo in PARAMETROS]
        return request.render('certum_revision.admin_ajustes', self._ctx(
            'ajustes', parametros=parametros, crons=self._crons(),
            url_guardar=RUTA_AJUSTES + '/guardar'))

    @http.route(RUTA_AJUSTES + '/guardar', type='http', methods=['POST'], csrf=True,
                auth='user', website=True, sitemap=False)
    def admin_ajustes_guardar(self, **post):
        guard = self._guard()
        if guard:
            return guard
        errores, valores = {}, {}
        for clave, nombre, _ayuda, _defecto, minimo, maximo in PARAMETROS:
            campo = clave.split('.')[-1]
            try:
                numero = int(str(post.get(campo) or '').strip())
            except ValueError:
                numero = None
            if numero is None or numero < minimo or numero > maximo:
                errores[campo] = 'Entre %s y %s.' % (minimo, maximo)
                continue
            valores[clave] = numero
        urgente = valores.get('certum_revision.dias_urgente')
        critico = valores.get('certum_revision.dias_critico')
        if urgente is not None and critico is not None and critico >= urgente:
            errores['dias_critico'] = 'Debe ser menor que el umbral urgente.'
        if errores:
            return responder(RUTA_AJUSTES, error='Revise los campos marcados.', errores=errores)
        Param = request.env['ir.config_parameter'].sudo()
        for clave, numero in valores.items():
            Param.set_param(clave, str(numero))
        auditar('ajustes_guardados', **{k.split('.')[-1]: v for k, v in valores.items()})
        return responder(RUTA_AJUSTES, ok='Ajustes guardados. Rigen desde ahora para lo nuevo.')

    @http.route(RUTA_AJUSTES + '/cron/<int:cron_id>/ejecutar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_ajustes_ejecutar(self, cron_id, **post):
        guard = self._guard()
        if guard:
            return guard
        cron = self._cron_del_modulo(cron_id)
        if not cron:
            return responder(RUTA_AJUSTES + '#tareas', error='Esa tarea no es de FYLE 360.')
        try:
            cron.method_direct_trigger()
        except Exception as exc:  # noqa: BLE001 - se informa, no se rompe la pantalla
            return responder(RUTA_AJUSTES + '#tareas', error='La tarea falló: %s' % exc)
        auditar('cron_ejecutado', cron=cron.id)
        return responder(RUTA_AJUSTES + '#tareas', ok='«%s» se ejecutó.' % cron.name)

    @http.route(RUTA_AJUSTES + '/cron/<int:cron_id>/activar', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_ajustes_activar(self, cron_id, **post):
        guard = self._guard()
        if guard:
            return guard
        cron = self._cron_del_modulo(cron_id)
        if not cron:
            return responder(RUTA_AJUSTES + '#tareas', error='Esa tarea no es de FYLE 360.')
        cron.active = not cron.active
        auditar('cron_activo', cron=cron.id, activo=cron.active)
        estado = 'encendida' if cron.active else 'apagada'
        return responder(RUTA_AJUSTES + '#tareas', ok='«%s» %s.' % (cron.name, estado))
