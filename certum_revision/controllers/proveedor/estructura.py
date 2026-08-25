# -*- coding: utf-8 -*-
"""Reestructurar un expediente YA INICIADO, sin tocar el curso de la revisión.

Se puede porque el expediente tiene su propia copia de la estructura y el curso
vive entero en el ítem: estado, archivos, fechas, paso de la cadena, revisores,
comentarios y trazabilidad. La carpeta solo dice DÓNDE se muestra el ítem, así
que mover un documento o una carpeta no altera nada de lo anterior.

Quién y cuándo: el PROVEEDOR, y solo mientras el expediente está activo
(publicación o revisión). Ver `proceso.puede_reestructurar()`.
"""
import logging

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.certum_revision.models.checklist import MAX_PROFUNDIDAD

from ..helpers import ROL_PROVEEDOR, _rol_en_proceso, json_err, json_r

_logger = logging.getLogger(__name__)


def _proceso_editable(proceso_id):
    """(proceso, None) si el proveedor puede reestructurarlo; (None, error)."""
    proc = request.env['certum.rev.proceso'].sudo().browse(int(proceso_id))
    if not proc.exists():
        return None, json_err('Proyecto no encontrado.', 404)
    if _rol_en_proceso(proc) != ROL_PROVEEDOR:
        return None, json_err('Solo el proveedor reestructura el proyecto.', 403)
    if not proc.puede_reestructurar():
        return None, json_err('El proyecto ya no está activo: no admite '
                              'cambios de estructura.', 400)
    return proc, None


def _carpeta_de(proc, raw_id):
    """Carpeta del expediente, o None si el id es vacío; False si no es suya."""
    try:
        cid = int(raw_id or 0)
    except (TypeError, ValueError):
        return False
    if not cid:
        return None
    carpeta = proc.folder_ids.filtered(lambda c: c.id == cid)
    return carpeta or False


def _item_de(proc, raw_id):
    try:
        iid = int(raw_id or 0)
    except (TypeError, ValueError):
        return False
    return proc.item_ids.filtered(lambda i: i.id == iid) or False


def _sig_secuencia(recs):
    return max(recs.mapped('sequence') or [0]) + 10


class CertumRevEstructura(http.Controller):

    # ── Carpetas ──────────────────────────────────────────────────────
    @http.route('/my/proceso/<int:proceso_id>/carpeta/crear', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def carpeta_crear(self, proceso_id, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('Indica un nombre para la carpeta.')
        padre = _carpeta_de(proc, post.get('parent_id'))
        if padre is False:
            return json_err('La carpeta padre no pertenece a este proyecto.')
        if padre and padre.nivel + 1 >= MAX_PROFUNDIDAD:
            return json_err('No se pueden anidar más de %s niveles de carpetas.'
                            % MAX_PROFUNDIDAD)
        hermanas = (padre.child_ids if padre
                    else proc.folder_ids.filtered(lambda c: not c.parent_id))
        carpeta = request.env['certum.rev.carpeta'].sudo().create({
            'proceso_id': proc.id,
            'name': name[:200],
            'sequence': _sig_secuencia(hermanas),
            'parent_id': padre.id if padre else False,
        })
        _logger.info('[AUDIT] estructura_carpeta_crear user=%s proceso=%s '
                     'carpeta=%s', request.env.user.id, proc.id, carpeta.id)
        return json_r({'ok': True, 'id': carpeta.id})

    @http.route('/my/proceso/<int:proceso_id>/carpeta/<int:cid>/editar',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def carpeta_editar(self, proceso_id, cid, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        carpeta = _carpeta_de(proc, cid)
        if not carpeta:
            return json_err('Carpeta no encontrada.', 404)
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('El nombre no puede quedar vacío.')
        carpeta.write({'name': name[:200]})
        _logger.info('[AUDIT] estructura_carpeta_editar user=%s carpeta=%s',
                     request.env.user.id, carpeta.id)
        return json_r({'ok': True})

    @http.route('/my/proceso/<int:proceso_id>/carpeta/<int:cid>/mover',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def carpeta_mover(self, proceso_id, cid, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        carpeta = _carpeta_de(proc, cid)
        if not carpeta:
            return json_err('Carpeta no encontrada.', 404)
        destino = _carpeta_de(proc, post.get('parent_id'))
        if destino is False:
            return json_err('La carpeta de destino no pertenece a este proyecto.')
        if destino and destino.id == carpeta.id:
            return json_err('Una carpeta no puede colgar de sí misma.')
        if destino and destino.nivel + 1 >= MAX_PROFUNDIDAD:
            return json_err('El destino ya está en el nivel más profundo '
                            'permitido (%s).' % MAX_PROFUNDIDAD)
        try:
            carpeta.write({'parent_id': destino.id if destino else False})
        except ValidationError as exc:
            # Mover una carpeta dentro de su propia descendencia.
            return json_err(getattr(exc, 'name', None) or
                            'No se puede mover una carpeta dentro de sí misma.')
        _logger.info('[AUDIT] estructura_carpeta_mover user=%s carpeta=%s '
                     'destino=%s', request.env.user.id, carpeta.id,
                     destino.id if destino else 0)
        return json_r({'ok': True})

    @http.route('/my/proceso/<int:proceso_id>/carpeta/<int:cid>/eliminar',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def carpeta_eliminar(self, proceso_id, cid, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        carpeta = _carpeta_de(proc, cid)
        if not carpeta:
            return json_err('Carpeta no encontrada.', 404)
        # Los documentos NO se borran: quedan sin carpeta (ondelete set null).
        _logger.info('[AUDIT] estructura_carpeta_eliminar user=%s carpeta=%s',
                     request.env.user.id, carpeta.id)
        carpeta.unlink()
        return json_r({'ok': True})

    # ── Documentos ────────────────────────────────────────────────────
    @http.route('/my/proceso/<int:proceso_id>/item/crear', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def item_crear(self, proceso_id, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('Indica un nombre para el documento.')
        carpeta = _carpeta_de(proc, post.get('carpeta_id'))
        if carpeta is False:
            return json_err('La carpeta no pertenece a este proyecto.')
        hermanos = (carpeta.item_ids if carpeta
                    else proc.item_ids.filtered(lambda i: not i.carpeta_id))
        item = request.env['certum.rev.item'].sudo().create({
            'proceso_id': proc.id,
            'carpeta_id': carpeta.id if carpeta else False,
            'name': name[:200],
            'description': (post.get('description') or '').strip()[:2000] or False,
            'required': (post.get('required') or '1') == '1',
            'sequence': _sig_secuencia(hermanos),
        })
        _logger.info('[AUDIT] estructura_item_crear user=%s proceso=%s item=%s',
                     request.env.user.id, proc.id, item.id)
        return json_r({'ok': True, 'id': item.id})

    @http.route('/my/proceso/<int:proceso_id>/item/<int:iid>/editar',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def item_editar(self, proceso_id, iid, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        item = _item_de(proc, iid)
        if not item:
            return json_err('Documento no encontrado.', 404)
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('El nombre no puede quedar vacío.')
        item.write({
            'name': name[:200],
            'description': (post.get('description') or '').strip()[:2000] or False,
            'required': (post.get('required') or '1') == '1',
        })
        _logger.info('[AUDIT] estructura_item_editar user=%s item=%s',
                     request.env.user.id, item.id)
        return json_r({'ok': True})

    @http.route('/my/proceso/<int:proceso_id>/item/<int:iid>/mover',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def item_mover(self, proceso_id, iid, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        item = _item_de(proc, iid)
        if not item:
            return json_err('Documento no encontrado.', 404)
        destino = _carpeta_de(proc, post.get('carpeta_id'))
        if destino is False:
            return json_err('La carpeta de destino no pertenece a este proyecto.')
        # Mover NO toca el curso: estado, archivos, plazos, paso de la cadena,
        # comentarios y trazabilidad cuelgan del ítem, no de la carpeta.
        item.write({'carpeta_id': destino.id if destino else False})
        _logger.info('[AUDIT] estructura_item_mover user=%s item=%s destino=%s',
                     request.env.user.id, item.id, destino.id if destino else 0)
        return json_r({'ok': True})

    @http.route('/my/proceso/<int:proceso_id>/item/<int:iid>/eliminar',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def item_eliminar(self, proceso_id, iid, **post):
        proc, err = _proceso_editable(proceso_id)
        if err:
            return err
        item = _item_de(proc, iid)
        if not item:
            return json_err('Documento no encontrado.', 404)
        # Solo se borra lo que no tiene historia: borrar un documento con
        # archivos, conversación o trazabilidad destruiría evidencia.
        if item.state != 'pendiente':
            return json_err('Solo se pueden quitar documentos que sigan '
                            'pendientes. Este ya está %s.' % item.state)
        if item.attachment_ids or item.comment_ids or item.aprobacion_ids:
            return json_err('Este documento ya tiene historial (archivos, '
                            'comentarios o trazabilidad) y no se puede quitar.')
        _logger.info('[AUDIT] estructura_item_eliminar user=%s item=%s',
                     request.env.user.id, item.id)
        item.unlink()
        # Quitar el último pendiente puede dejar el expediente completo.
        proc._check_completado()
        return json_r({'ok': True})

    # ── Guardar la estructura como plantilla NUEVA ────────────────────
    @http.route('/my/proceso/<int:proceso_id>/guardar-plantilla', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def guardar_plantilla(self, proceso_id, **post):
        """Crea una plantilla NUEVA con la estructura actual del expediente.

        La plantilla original no se toca: queda a criterio del proveedor
        conservarla o retirarla más adelante.
        """
        proc = request.env['certum.rev.proceso'].sudo().browse(int(proceso_id))
        if not proc.exists():
            return json_err('Proyecto no encontrado.', 404)
        if _rol_en_proceso(proc) != ROL_PROVEEDOR:
            return json_err('Solo el proveedor puede guardar la plantilla.', 403)
        if proc.state == 'borrador':
            return json_err('El proyecto aún no se ha abierto.', 400)
        nueva = proc.crear_plantilla_desde_proceso(post.get('name'))
        return json_r({'ok': True, 'id': nueva.id, 'code': nueva.code,
                       'name': nueva.name,
                       'redirect': '/my/plantilla/%d' % nueva.id})
