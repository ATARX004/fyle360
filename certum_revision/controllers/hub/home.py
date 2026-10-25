# -*- coding: utf-8 -*-
"""Inicio de FYLE 360: el resumen de cada rol.

Es la primera entrada del menú lateral y la pantalla de llegada. Cada rol ve
lo suyo, en el mismo orden: sus cifras, lo que le pide una acción ahora y sus
proyectos.

  - Interno: lo que pide atención en toda la plataforma (antes era una
    pantalla aparte en Administración → Resumen).
  - Cliente: los documentos que esperan su revisión, del más urgente al
    menos, marcando los que le tocan a él.
  - Proveedor: lo observado que debe corregir y lo que falta publicar.
"""
from odoo import fields, http
from odoo.http import request

from ...models.tz_utils import fmt_lima, today_lima
from ..admin.resumen import resumen_interno
from ..helpers import (ROL_CLIENTE, ROL_INTERNO, ROL_PROVEEDOR, _empresa, _get_rol,
                       item_es_mio)

ACTIVOS = [('proceso_id.state', 'in', ('publicacion', 'revision'))]


def _plazo(limite):
    """Datetime límite (UTC) -> {'fecha', 'dias', 'tono'} para la lista."""
    if not limite:
        return {'fecha': '', 'dias': None, 'tono': ''}
    dia = fields.Date.to_date(fmt_lima(limite, '%Y-%m-%d'))
    dias = (dia - today_lima()).days
    tono = 'danger' if dias <= 1 else 'warn' if dias <= 3 else 'ok'
    return {'fecha': fmt_lima(limite, '%d/%m/%Y'), 'dias': dias, 'tono': tono}


def _fila(item, motivo, limite, mio=False):
    proceso = item.proceso_id
    return {
        'nombre': item.name,
        'proyecto': proceso.name + (' · %s' % proceso.referencia if proceso.referencia else ''),
        'carpeta': item.carpeta_id.ruta or item.carpeta_id.name or '',
        'motivo': motivo,
        'plazo': _plazo(limite),
        'mio': mio,
        'url': '/my/proceso/%s?item=%s' % (proceso.id, item.id),
    }


class CertumRevHub(http.Controller):

    @http.route('/my/certum', type='http', auth='user', website=True)
    def hub_home(self, **kw):
        rol = _get_rol()
        emp = _empresa()
        Proceso = request.env['certum.rev.proceso'].sudo()
        Item = request.env['certum.rev.item'].sudo()
        vals = {'rol': rol, 'empresa': emp, 'cifras': [], 'pendientes': [],
                'procesos': Proceso.browse(), 'atencion': [], 'proximos': Proceso.browse()}

        if rol == ROL_INTERNO:
            vals.update(resumen_interno())

        elif rol == ROL_PROVEEDOR:
            procesos = Proceso.search([('proveedor_id', '=', emp.id), ('state', '!=', 'borrador')],
                                      order='fecha_vencimiento asc')
            propios = ACTIVOS + [('proveedor_id', '=', emp.id)]
            observados = Item.search(propios + [('state', '=', 'observado')],
                                     order='fecha_limite_correccion asc')
            por_publicar = Item.search(propios + [('state', '=', 'pendiente')],
                                       order='proceso_id, sequence')
            vals['cifras'] = [
                {'valor': len(procesos.filtered(lambda p: p.state in ('publicacion', 'revision'))),
                 'etiqueta': 'proyectos en curso'},
                {'valor': len(observados), 'etiqueta': 'observados por corregir',
                 'tono': observados and 'alerta' or ''},
                {'valor': len(por_publicar), 'etiqueta': 'por publicar'},
                {'valor': Item.search_count([('proveedor_id', '=', emp.id), ('state', '=', 'aprobado')]),
                 'etiqueta': 'aprobados'},
            ]
            vals['pendientes'] = (
                [_fila(i, 'Corregir y volver a publicar', i.fecha_limite_correccion)
                 for i in observados[:8]]
                + [_fila(i, 'Publicar el documento', False)
                   for i in por_publicar[:max(0, 8 - len(observados))]])
            vals['procesos'] = procesos[:6]

        elif rol == ROL_CLIENTE:
            procesos = Proceso.search([('cliente_id', '=', emp.id), ('state', '!=', 'borrador')],
                                      order='fecha_vencimiento asc')
            propios = ACTIVOS + [('cliente_id', '=', emp.id)]
            por_revisar = Item.search(propios + [('state', '=', 'publicado')],
                                      order='fecha_limite_revision asc')
            mios = por_revisar.filtered(lambda i: item_es_mio(i, ROL_CLIENTE))
            vals['cifras'] = [
                {'valor': len(procesos.filtered(lambda p: p.state in ('publicacion', 'revision'))),
                 'etiqueta': 'proyectos en revisión'},
                {'valor': len(mios), 'etiqueta': 'le toca revisar a usted',
                 'tono': mios and 'alerta' or ''},
                {'valor': len(por_revisar), 'etiqueta': 'esperan revisión de su empresa'},
                {'valor': Item.search_count(propios + [('state', '=', 'observado')]),
                 'etiqueta': 'en corrección del proveedor'},
            ]
            # Primero lo que le toca a él; dentro de cada grupo, lo que vence antes.
            orden = list(mios) + list(por_revisar - mios)
            vals['pendientes'] = [
                _fila(i, 'Le toca revisar a usted' if i in mios else 'Esperando a otro revisor de su empresa',
                      i.fecha_limite_revision, mio=i in mios)
                for i in orden[:8]]
            vals['procesos'] = procesos[:6]

        return request.render('certum_revision.portal_hub', vals)
