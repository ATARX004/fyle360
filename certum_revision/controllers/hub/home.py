# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from ..helpers import ROL_CLIENTE, ROL_INTERNO, ROL_PROVEEDOR, _empresa, _get_rol


class CertumRevHub(http.Controller):

    @http.route('/my/certum', type='http', auth='user', website=True)
    def hub_home(self, **kw):
        rol = _get_rol()
        emp = _empresa()
        Proceso = request.env['certum.rev.proceso'].sudo()
        Item = request.env['certum.rev.item'].sudo()

        kpis, procesos = [], Proceso.browse()
        if rol == ROL_INTERNO:
            # El interno administra desde su panel (/my/certum/admin); el hub le da un resumen
            # global y atajos. Ve todos los procesos (incluidos borradores).
            procesos = Proceso.search([], order='fecha_vencimiento asc')
            kpis = [
                {'icon': 'i-folder', 'label': 'Proyectos activos', 'tone': 'brand',
                 'value': Proceso.search_count([('state', 'in', ('publicacion', 'revision'))])},
                {'icon': 'i-eye', 'label': 'Ítems por revisar', 'tone': 'warn',
                 'value': Item.search_count([('state', '=', 'publicado')])},
                {'icon': 'i-check', 'label': 'Proyectos completados', 'tone': 'ok',
                 'value': Proceso.search_count([('state', '=', 'completado')])},
                {'icon': 'i-alert', 'label': 'Fuera de plazo', 'tone': 'danger',
                 'value': Proceso.search_count([('state', '=', 'fuera_plazo')])},
            ]
        elif rol == ROL_PROVEEDOR:
            procesos = Proceso.search([('proveedor_id', '=', emp.id),
                                       ('state', '!=', 'borrador')])
            kpis = [
                {'icon': 'i-folder', 'label': 'Proyectos activos', 'tone': 'brand',
                 'value': len(procesos.filtered(lambda p: p.state in ('publicacion', 'revision')))},
                {'icon': 'i-upload', 'label': 'Ítems por publicar', 'tone': 'warn',
                 'value': Item.search_count([('proveedor_id', '=', emp.id),
                                             ('state', '=', 'pendiente'),
                                             ('proceso_id.state', 'in', ('publicacion', 'revision'))])},
                {'icon': 'i-alert', 'label': 'Ítems observados', 'tone': 'danger',
                 'value': Item.search_count([('proveedor_id', '=', emp.id),
                                             ('state', '=', 'observado'),
                                             ('proceso_id.state', 'in', ('publicacion', 'revision'))])},
                {'icon': 'i-check', 'label': 'Ítems aprobados', 'tone': 'ok',
                 'value': Item.search_count([('proveedor_id', '=', emp.id),
                                             ('state', '=', 'aprobado')])},
            ]
        elif rol == ROL_CLIENTE:
            procesos = Proceso.search([('cliente_id', '=', emp.id),
                                       ('state', '!=', 'borrador')])
            kpis = [
                {'icon': 'i-folder', 'label': 'Proyectos en revisión', 'tone': 'brand',
                 'value': len(procesos.filtered(lambda p: p.state in ('publicacion', 'revision')))},
                {'icon': 'i-eye', 'label': 'Ítems por revisar', 'tone': 'warn',
                 'value': Item.search_count([('cliente_id', '=', emp.id),
                                             ('state', '=', 'publicado')])},
                {'icon': 'i-alert', 'label': 'Observados (en corrección)', 'tone': 'danger',
                 'value': Item.search_count([('cliente_id', '=', emp.id),
                                             ('state', '=', 'observado')])},
                {'icon': 'i-check', 'label': 'Ítems aprobados', 'tone': 'ok',
                 'value': Item.search_count([('cliente_id', '=', emp.id),
                                             ('state', '=', 'aprobado')])},
            ]

        return request.render('certum_revision.portal_hub', {
            'rol': rol,
            'empresa': emp,
            'kpis': kpis,
            'procesos': procesos[:6],
        })
