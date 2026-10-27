# -*- coding: utf-8 -*-
"""Gestión de un proyecto desde el panel (solo Certum interno).

Rutas:

    GET   /my/certum/admin/proyecto/<id>                      -> la pantalla
    POST  /my/certum/admin/proyecto/<id>/datos                -> referencia y plazos
    POST  /my/certum/admin/proyecto/<id>/roles                -> roles de un lado
    POST  /my/certum/admin/proyecto/<id>/eliminar/solicitar   -> manda el código
    POST  /my/certum/admin/proyecto/<id>/eliminar/confirmar   -> lo comprueba y borra
    POST  /my/certum/admin/proyecto/<id>/eliminar/cancelar    -> anula la solicitud

Roles: cada lado del proyecto (proveedor y cliente) usa los roles generales
de su empresa o una lista propia (models/participante.py). Quien queda fuera
de la lista deja de ver el proyecto y de recibir sus correos.

Eliminar va en dos pasos y sin JavaScript propio: pedir el código recarga la
pantalla con el segundo paso a la vista, porque hay una solicitud pendiente.
El modelo (models/eliminacion.py) explica el porqué del código por correo.
"""
from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from ...models.eliminacion import MINUTOS_VALIDEZ
from ...models.tz_utils import fmt_lima
from .base import RUTA_ADMIN, AdminBase, auditar, responder
from .resumen import ESTADOS, RUTA_PROYECTOS

LADOS = ('proveedor', 'cliente')


def _url(proceso, ancla=''):
    return '%s/proyecto/%s%s' % (RUTA_ADMIN, proceso.id, ('#' + ancla) if ancla else '')


def _entero(valor, defecto=None):
    try:
        return int(str(valor or '').strip())
    except (TypeError, ValueError):
        return defecto


def _lado(proceso, lado):
    """Lo que pinta el bloque de roles de un lado del proyecto."""
    empresa = proceso.proveedor_id if lado == 'proveedor' else proceso.cliente_id
    propios = proceso.roles_propios(lado)
    lista = {p.partner_id.id: p.nivel for p in proceso.participante_ids if p.lado == lado}
    personas = request.env['res.partner'].sudo().search([
        ('parent_id', '=', empresa.id), ('is_company', '=', False)], order='certum_nivel, name')
    filas = []
    for persona in personas:
        # Si aún no hay lista propia, se propone empezar con todos y con su
        # nivel general: lo normal es quitar a unos pocos, no elegir de cero.
        en_lista = persona.id in lista if lista else True
        filas.append({
            'id': persona.id,
            'nombre': persona.name or persona.email or 'Contacto',
            'email': persona.email or '',
            'usuario': bool(persona.user_ids),
            'nivel_general': persona.certum_nivel or 0,
            'participa': en_lista,
            'nivel': lista.get(persona.id, persona.certum_nivel or 0),
        })
    fuera = sum(1 for f in filas if not f['participa']) if propios else 0
    return {
        'lado': lado,
        'titulo': 'Proveedor' if lado == 'proveedor' else 'Cliente',
        'empresa': empresa,
        'propios': propios,
        'filas': filas,
        'dentro': len(filas) - fuera,
        'fuera': fuera,
        'url': '%s/proyecto/%s/roles' % (RUTA_ADMIN, proceso.id),
    }


class AdminProyecto(AdminBase):

    def _proyecto(self, proceso_id):
        return request.env['certum.rev.proceso'].sudo().browse(proceso_id).exists()

    def _pendiente(self, proceso):
        """La solicitud de eliminación vigente de ESTE usuario, si la hay."""
        elim = request.env['certum.rev.eliminacion'].sudo().search([
            ('proceso_id', '=', proceso.id), ('estado', '=', 'pendiente'),
            ('solicitante_id', '=', request.env.user.id)], limit=1)
        return elim if elim and elim.vigente() else elim.browse()

    def _ctx_proyecto(self, proceso):
        pendiente = self._pendiente(proceso)
        return self._ctx(
            'proyectos', proceso=proceso, estados=dict(ESTADOS),
            lados=[_lado(proceso, lado) for lado in LADOS],
            pendiente=pendiente,
            pendiente_vence=fmt_lima(pendiente.vence, '%H:%M') if pendiente else '',
            minutos_validez=MINUTOS_VALIDEZ,
            n_archivos=request.env['ir.attachment'].sudo().search_count([
                ('res_model', '=', 'certum.rev.item'), ('res_id', 'in', proceso.item_ids.ids)]),
            url_proyecto=_url(proceso))

    def _render_lado(self, proceso, lado):
        return str(request.env['ir.ui.view'].sudo()._render_template(
            'certum_revision.admin_proyecto_roles_lado',
            {'proceso': proceso, 'l': _lado(proceso, lado)}))

    # ─── La pantalla ─────────────────────────────────────────────────────
    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>', type='http', auth='user',
                website=True, sitemap=False)
    def admin_proyecto(self, proceso_id, **kw):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso:
            return responder(RUTA_PROYECTOS, error='Ese proyecto ya no existe.')
        return request.render('certum_revision.admin_proyecto', self._ctx_proyecto(proceso))

    # ─── Datos ───────────────────────────────────────────────────────────
    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>/datos', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_proyecto_datos(self, proceso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso:
            return responder(RUTA_PROYECTOS, error='Ese proyecto ya no existe.')
        errores, valores = {}, {}
        valores['referencia'] = ' '.join((post.get('referencia') or '').split())[:120] or False
        plazo = _entero(post.get('plazo_dias'))
        if plazo is None or plazo < 0 or plazo > proceso._MAX_PLAZO_DIAS:
            errores['plazo_dias'] = 'Escriba un número de días entre 0 y %s.' % proceso._MAX_PLAZO_DIAS
        else:
            valores['plazo_dias'] = plazo
        for campo in ('fecha_inicio', 'fecha_vencimiento'):
            crudo = (post.get(campo) or '').strip()
            if not crudo:
                if campo == 'fecha_inicio' and proceso.state != 'borrador':
                    errores[campo] = 'Un proyecto abierto necesita su fecha de inicio.'
                else:
                    valores[campo] = False
                continue
            try:
                valores[campo] = fields.Date.to_date(crudo)
            except ValueError:
                errores[campo] = 'Fecha no válida.'
        if errores:
            return responder(_url(proceso, 'datos'), error='Revise los campos marcados.', errores=errores)
        try:
            with request.env.cr.savepoint():
                proceso.write(valores)
                proceso._guard_duplicado()
        except (UserError, ValidationError) as exc:
            return responder(_url(proceso, 'datos'), error=str(exc.args[0] if exc.args else exc))
        auditar('proyecto_datos', proceso=proceso.id, plazo=proceso.plazo_dias,
                inicio=proceso.fecha_inicio or '')
        limite = proceso.fecha_limite.strftime('%d/%m/%Y') if proceso.fecha_limite else 'sin fecha'
        return responder(_url(proceso, 'datos'),
                         ok='Datos de %s guardados. Fin del plazo: %s.' % (proceso.name, limite))

    # ─── Roles ───────────────────────────────────────────────────────────
    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>/roles', type='http', methods=['POST'],
                csrf=True, auth='user', website=True, sitemap=False)
    def admin_proyecto_roles(self, proceso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso:
            return responder(RUTA_PROYECTOS, error='Ese proyecto ya no existe.')
        lado = post.get('lado')
        if lado not in LADOS:
            return responder(_url(proceso, 'roles'), error='Lado no válido.')
        campo = 'roles_%s' % lado
        empresa = proceso.proveedor_id if lado == 'proveedor' else proceso.cliente_id
        fragmentos = lambda: {'roles_%s' % lado: self._render_lado(proceso, lado)}  # noqa: E731

        if post.get('modo') != 'proyecto':
            proceso.write({campo: 'general'})
            auditar('proyecto_roles', proceso=proceso.id, lado=lado, modo='general')
            return responder(_url(proceso, 'roles'), fragmentos=fragmentos,
                             ok='%s usa los roles generales de %s: participa todo su personal.'
                                % (proceso.name, empresa.name))

        # Roles propios: la lista que llega, cruzada con el personal real.
        personas = request.env['res.partner'].sudo().search([
            ('parent_id', '=', empresa.id), ('is_company', '=', False)])
        elegidos, errores = {}, {}
        for persona in personas:
            if not post.get('p_%s' % persona.id):
                continue
            nivel = _entero(post.get('n_%s' % persona.id), 0)
            if nivel < 0 or nivel > 20:
                errores['n_%s' % persona.id] = 'Entre 0 y 20.'
            elegidos[persona.id] = nivel
        if errores:
            return responder(_url(proceso, 'roles'), error='Revise los niveles marcados.', errores=errores)
        if not elegidos:
            return responder(_url(proceso, 'roles'),
                             error='Deje al menos a una persona de %s en el proyecto.' % empresa.name)

        # Quien está en una cadena de revisión en curso no puede quedar fuera:
        # el documento esperaría a alguien que ya no ve el proyecto.
        if lado == 'cliente':
            en_cadena = proceso.revisor_ids.partner_id | proceso.item_ids.filtered(
                lambda i: i.state != 'aprobado').revisor_ids.partner_id
            sueltos = en_cadena.filtered(lambda p: p.id not in elegidos)
            if sueltos:
                return responder(_url(proceso, 'roles'), error=(
                    'No se puede dejar fuera a %s: está en la cadena de revisión del proyecto. '
                    'Que el nivel 1 del cliente o el proveedor lo quiten de la cadena primero.'
                    % ', '.join(sueltos.mapped('name'))))

        Participante = request.env['certum.rev.participante'].sudo()
        proceso.participante_ids.filtered(lambda p: p.lado == lado).unlink()
        Participante.create([{'proceso_id': proceso.id, 'partner_id': pid, 'lado': lado,
                              'nivel': nivel} for pid, nivel in elegidos.items()])
        proceso.write({campo: 'proyecto'})
        fuera = len(personas) - len(elegidos)
        auditar('proyecto_roles', proceso=proceso.id, lado=lado, modo='proyecto',
                dentro=len(elegidos), fuera=fuera)
        mensaje = 'Roles propios de %s en %s guardados: %d persona(s) participan' % (
            empresa.name, proceso.name, len(elegidos))
        if fuera:
            mensaje += '; %d no verán el proyecto ni recibirán sus correos' % fuera
        aviso = self._aviso_capas(proceso, lado, elegidos)
        return responder(_url(proceso, 'roles'), ok=mensaje + '.' + aviso, fragmentos=fragmentos)

    def _aviso_capas(self, proceso, lado, elegidos):
        """Con aprobación por capas, cada nivel de la cadena necesita a
        alguien que lo tenga; si no, ese paso no lo podría aprobar nadie."""
        if lado != 'cliente' or proceso.revision_modo != 'secuencial':
            return ''
        niveles = set(elegidos.values())
        faltan = [n for n in range(1, (proceso.revision_capas or 1) + 1) if n not in niveles]
        if not faltan:
            return ''
        return (' Atención: la revisión es por capas y nadie del cliente tiene el nivel %s '
                'en este proyecto.' % ', '.join(str(n) for n in faltan))

    # ─── Eliminar ────────────────────────────────────────────────────────
    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>/eliminar/solicitar', type='http',
                methods=['POST'], csrf=True, auth='user', website=True, sitemap=False)
    def admin_proyecto_eliminar_solicitar(self, proceso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso:
            return responder(RUTA_PROYECTOS, error='Ese proyecto ya no existe.')
        if not post.get('entiendo'):
            return responder(_url(proceso, 'eliminar'),
                             error='Marque que entiende que la eliminación no se puede deshacer.')
        escrito = ' '.join((post.get('confirma') or '').split()).upper()
        if escrito != (proceso.name or '').upper():
            return responder(_url(proceso, 'eliminar'),
                             error='El código escrito no es el del proyecto (%s).' % proceso.name)
        try:
            elim = request.env['certum.rev.eliminacion'].solicitar(proceso)
        except UserError as exc:
            return responder(_url(proceso, 'eliminar'), error=str(exc.args[0] if exc.args else exc))
        auditar('proyecto_eliminar_solicitado', proceso=proceso.id, solicitud=elim.id,
                avisados=elim.avisados)
        return responder(_url(proceso, 'eliminar'), ok=(
            'Código enviado a %d usuario(s) interno(s). Escríbalo abajo antes de las %s.'
            % (elim.avisados, fmt_lima(elim.vence, '%H:%M'))))

    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>/eliminar/confirmar', type='http',
                methods=['POST'], csrf=True, auth='user', website=True, sitemap=False)
    def admin_proyecto_eliminar_confirmar(self, proceso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso:
            return responder(RUTA_PROYECTOS, error='Ese proyecto ya no existe.')
        elim = self._pendiente(proceso)
        if not elim:
            return responder(_url(proceso, 'eliminar'),
                             error='No hay una solicitud vigente: pida un código nuevo.')
        nombre = proceso.name
        try:
            detalle = elim.confirmar(post.get('codigo'))
        except UserError as exc:
            return responder(_url(proceso, 'eliminar'), error=str(exc.args[0] if exc.args else exc))
        auditar('proyecto_eliminado', solicitud=elim.id, proyecto=nombre)
        return responder(RUTA_PROYECTOS, ok='Proyecto %s eliminado: %s.' % (nombre, detalle))

    @http.route(RUTA_ADMIN + '/proyecto/<int:proceso_id>/eliminar/cancelar', type='http',
                methods=['POST'], csrf=True, auth='user', website=True, sitemap=False)
    def admin_proyecto_eliminar_cancelar(self, proceso_id, **post):
        guard = self._guard()
        if guard:
            return guard
        proceso = self._proyecto(proceso_id)
        if not proceso:
            return responder(RUTA_PROYECTOS, error='Ese proyecto ya no existe.')
        elim = self._pendiente(proceso)
        if elim:
            elim.estado = 'anulada'
            auditar('proyecto_eliminar_cancelado', proceso=proceso.id, solicitud=elim.id)
        return responder(_url(proceso, 'eliminar'), ok='Eliminación cancelada. El proyecto sigue intacto.')
