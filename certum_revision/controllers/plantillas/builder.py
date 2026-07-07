# -*- coding: utf-8 -*-
"""Panel Proveedor: constructor de plantillas (checklist) e iniciar proceso.

Todo el acceso a datos usa sudo() + validación de propiedad en código
(_checklist_or_none / _mis_checklists). Un proveedor jamás toca plantillas
de otro. El interno también puede administrar cualquier plantilla.
"""
import logging

from odoo import http
from odoo.http import request

from ..helpers import (
    ROL_INTERNO,
    ROL_PROVEEDOR,
    _checklist_or_none,
    _companias_por_rol,
    _empresa,
    _mis_checklists,
    is_ajax,
    json_err,
    json_r,
)

_logger = logging.getLogger(__name__)


# ── Serialización compartida ─────────────────────────────────────────
def _folder_data(folder):
    return {
        'id': folder.id,
        'name': folder.name,
        'sequence': folder.sequence,
    }


def _item_data(item):
    return {
        'id': item.id,
        'name': item.name,
        'description': item.description or '',
        'required': bool(item.required),
        'sequence': item.sequence,
        'folder_id': item.folder_id.id or False,
    }


def _checklist_data(ch):
    """JSON completo de una plantilla para refrescar la UI del editor."""
    folders = ch.folder_ids.sorted(lambda f: (f.sequence, f.id))
    items = ch.item_ids.sorted(lambda i: (i.sequence, i.id))
    return {
        'id': ch.id,
        'name': ch.name,
        'code': ch.code or '',
        'plazo_dias': ch.plazo_dias or 0,
        'folders': [_folder_data(f) for f in folders],
        'items': [_item_data(i) for i in items],
        'folder_count': len(folders),
        'item_count': len(items),
    }


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_true(value):
    return str(value).strip().lower() in ('1', 'true', 'on', 'yes', 'si', 'sí')


class CertumRevPlantillas(http.Controller):

    # ── Listado de plantillas ─────────────────────────────────────────
    @http.route('/my/plantillas', type='http', auth='user', website=True)
    def plantillas_list(self, **kw):
        checklists = _mis_checklists().sorted('name')
        rol = ROL_INTERNO if request.env.user and not request.env.user.share \
            else ROL_PROVEEDOR
        plantillas = [{
            'id': ch.id,
            'name': ch.name,
            'code': ch.code or '',
            'sector': ch.sector or '',
            'plazo_dias': ch.plazo_dias or 0,
            'folder_count': len(ch.folder_ids),
            'item_count': len(ch.item_ids),
            'proveedor': ch.proveedor_id.name or '',
        } for ch in checklists]
        return request.render('certum_revision.plantillas_list', {
            'rol': rol,
            'plantillas': plantillas,
        })

    # ── Crear plantilla ───────────────────────────────────────────────
    @http.route('/my/plantilla/crear', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def plantilla_crear(self, **post):
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('Indica un nombre para la plantilla.')
        plazo_dias = _to_int(post.get('plazo_dias'), 30) or 30

        vals = {
            'name': name[:200],
            'plazo_dias': plazo_dias,
        }
        # El interno crea plantillas globales (sin dueño); el proveedor las suyas.
        if request.env.user.share:
            vals['proveedor_id'] = _empresa().id
        ch = request.env['certum.rev.checklist'].sudo().create(vals)
        _logger.info('[AUDIT] plantilla_crear user=%s checklist=%s name=%s',
                     request.env.user.id, ch.id, name)

        payload = {'ok': True, 'id': ch.id,
                   'redirect': '/my/plantilla/%d' % ch.id}
        if is_ajax():
            return json_r(payload)
        return request.redirect(payload['redirect'])

    # ── Editor de una plantilla ───────────────────────────────────────
    @http.route('/my/plantilla/<int:cid>', type='http', auth='user',
                website=True)
    def plantilla_editor(self, cid, **kw):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return request.redirect('/my/plantillas')
        data = _checklist_data(ch)
        clientes = [{'id': c.id, 'name': c.name}
                    for c in _companias_por_rol('cliente')]
        # Para el interno: elegir proveedor al iniciar una plantilla global.
        proveedores = [{'id': p.id, 'name': p.name}
                       for p in _companias_por_rol('proveedor')]
        return request.render('certum_revision.plantilla_editor', {
            'rol': rol,
            'checklist': ch,
            'ch_data': data,
            'clientes': clientes,
            'proveedores': proveedores,
        })

    # ── Editar cabecera de la plantilla ───────────────────────────────
    @http.route('/my/plantilla/<int:cid>/editar', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def plantilla_editar(self, cid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        vals = {}
        if 'name' in post:
            name = (post.get('name') or '').strip()
            if not name:
                return json_err('El nombre no puede quedar vacío.')
            vals['name'] = name[:200]
        if 'plazo_dias' in post:
            vals['plazo_dias'] = max(0, _to_int(post.get('plazo_dias'), ch.plazo_dias))
        if vals:
            ch.write(vals)
            _logger.info('[AUDIT] plantilla_editar user=%s checklist=%s vals=%s',
                         request.env.user.id, ch.id, list(vals.keys()))
        return json_r({'ok': True, 'checklist': _checklist_data(ch)})

    # ── Carpetas ──────────────────────────────────────────────────────
    @http.route('/my/plantilla/<int:cid>/carpeta/crear', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def carpeta_crear(self, cid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('Indica un nombre para la carpeta.')
        seq = max(ch.folder_ids.mapped('sequence') or [0]) + 10
        folder = request.env['certum.rev.checklist.folder'].sudo().create({
            'checklist_id': ch.id,
            'name': name[:200],
            'sequence': seq,
        })
        _logger.info('[AUDIT] carpeta_crear user=%s checklist=%s folder=%s',
                     request.env.user.id, ch.id, folder.id)
        return json_r({'ok': True, 'folder': _folder_data(folder),
                       'checklist': _checklist_data(ch)})

    @http.route('/my/plantilla/<int:cid>/carpeta/<int:fid>/editar',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def carpeta_editar(self, cid, fid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        folder = ch.folder_ids.filtered(lambda f: f.id == int(fid))
        if not folder:
            return json_err('La carpeta no pertenece a esta plantilla.', 404)
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('El nombre no puede quedar vacío.')
        folder.write({'name': name[:200]})
        _logger.info('[AUDIT] carpeta_editar user=%s checklist=%s folder=%s',
                     request.env.user.id, ch.id, folder.id)
        return json_r({'ok': True, 'folder': _folder_data(folder),
                       'checklist': _checklist_data(ch)})

    @http.route('/my/plantilla/<int:cid>/carpeta/<int:fid>/eliminar',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def carpeta_eliminar(self, cid, fid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        folder = ch.folder_ids.filtered(lambda f: f.id == int(fid))
        if not folder:
            return json_err('La carpeta no pertenece a esta plantilla.', 404)
        folder.unlink()
        _logger.info('[AUDIT] carpeta_eliminar user=%s checklist=%s folder=%s',
                     request.env.user.id, ch.id, fid)
        return json_r({'ok': True, 'checklist': _checklist_data(ch)})

    # ── Ítems ─────────────────────────────────────────────────────────
    @http.route('/my/plantilla/<int:cid>/item/crear', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def item_crear(self, cid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        name = (post.get('name') or '').strip()
        if not name:
            return json_err('Indica un nombre para el ítem.')
        folder = self._folder_of(ch, post.get('folder_id'))
        if folder is False:
            return json_err('La carpeta no pertenece a esta plantilla.', 404)
        seq = max(ch.item_ids.mapped('sequence') or [0]) + 10
        item = request.env['certum.rev.checklist.item'].sudo().create({
            'checklist_id': ch.id,
            'folder_id': folder.id if folder else False,
            'name': name[:200],
            'description': (post.get('description') or '').strip()[:2000] or False,
            'required': _is_true(post.get('required')),
            'sequence': seq,
        })
        _logger.info('[AUDIT] item_crear user=%s checklist=%s item=%s',
                     request.env.user.id, ch.id, item.id)
        return json_r({'ok': True, 'item': _item_data(item),
                       'checklist': _checklist_data(ch)})

    @http.route('/my/plantilla/<int:cid>/item/<int:iid>/editar', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def item_editar(self, cid, iid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        item = ch.item_ids.filtered(lambda i: i.id == int(iid))
        if not item:
            return json_err('El ítem no pertenece a esta plantilla.', 404)
        vals = {}
        if 'name' in post:
            name = (post.get('name') or '').strip()
            if not name:
                return json_err('El nombre no puede quedar vacío.')
            vals['name'] = name[:200]
        if 'description' in post:
            vals['description'] = (post.get('description') or '').strip()[:2000] or False
        if 'required' in post:
            vals['required'] = _is_true(post.get('required'))
        if 'folder_id' in post:
            folder = self._folder_of(ch, post.get('folder_id'))
            if folder is False:
                return json_err('La carpeta no pertenece a esta plantilla.', 404)
            vals['folder_id'] = folder.id if folder else False
        if vals:
            item.write(vals)
            _logger.info('[AUDIT] item_editar user=%s checklist=%s item=%s',
                         request.env.user.id, ch.id, item.id)
        return json_r({'ok': True, 'item': _item_data(item),
                       'checklist': _checklist_data(ch)})

    @http.route('/my/plantilla/<int:cid>/item/<int:iid>/eliminar',
                type='http', auth='user', website=True, methods=['POST'],
                csrf=True)
    def item_eliminar(self, cid, iid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        item = ch.item_ids.filtered(lambda i: i.id == int(iid))
        if not item:
            return json_err('El ítem no pertenece a esta plantilla.', 404)
        item.unlink()
        _logger.info('[AUDIT] item_eliminar user=%s checklist=%s item=%s',
                     request.env.user.id, ch.id, iid)
        return json_r({'ok': True, 'checklist': _checklist_data(ch)})

    # ── Iniciar proceso desde la plantilla ────────────────────────────
    @http.route('/my/plantilla/<int:cid>/iniciar', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def plantilla_iniciar(self, cid, **post):
        ch, rol = _checklist_or_none(cid)
        if ch is None:
            return json_err('Plantilla no encontrada.', 404)
        if not ch.item_ids:
            return json_err('La plantilla no tiene ítems; agrega al menos uno.')

        cliente_id = _to_int(post.get('cliente_id'))
        if not cliente_id:
            return json_err('Elige la empresa cliente.')
        cliente = request.env['res.partner'].sudo().browse(cliente_id)
        # El cliente debe ser una compañía con rol cliente (evita inyección de id).
        clientes_validos = _companias_por_rol('cliente')
        if not cliente.exists() or cliente.id not in clientes_validos.ids:
            return json_err('El cliente seleccionado no es válido.')

        # Proveedor del proceso:
        #  - plantilla con dueño → ese proveedor;
        #  - proveedor portal sobre plantilla global → él mismo;
        #  - interno sobre plantilla global → lo elige en el modal.
        if ch.proveedor_id:
            proveedor = ch.proveedor_id
        elif request.env.user.share:
            proveedor = _empresa()
        else:
            prov_id = _to_int(post.get('proveedor_id'))
            if not prov_id:
                return json_err('Elige la empresa proveedora.')
            proveedor = request.env['res.partner'].sudo().browse(prov_id)
            if not proveedor.exists() or \
                    proveedor.id not in _companias_por_rol('proveedor').ids:
                return json_err('El proveedor seleccionado no es válido.')

        vals = {
            'proveedor_id': proveedor.id,
            'cliente_id': cliente.id,
            'checklist_id': ch.id,
            'plazo_dias': max(0, _to_int(post.get('plazo_dias'), ch.plazo_dias)),
        }
        fecha_inicio = (post.get('fecha_inicio') or '').strip()
        if fecha_inicio:
            vals['fecha_inicio'] = fecha_inicio

        try:
            proc = request.env['certum.rev.proceso'].sudo().create(vals)
            proc.action_abrir()
        except Exception as exc:  # noqa: BLE001 - se reporta al usuario
            _logger.warning('[AUDIT] plantilla_iniciar_error user=%s '
                            'checklist=%s error=%s', request.env.user.id,
                            ch.id, exc)
            msg = getattr(exc, 'name', None) or str(exc) or \
                'No se pudo iniciar el proceso.'
            return json_err(msg)

        _logger.info('[AUDIT] plantilla_iniciar user=%s checklist=%s '
                     'proceso=%s cliente=%s', request.env.user.id, ch.id,
                     proc.id, cliente.id)
        payload = {'ok': True, 'id': proc.id,
                   'redirect': '/my/proceso/%d' % proc.id}
        if is_ajax():
            return json_r(payload)
        return request.redirect(payload['redirect'])

    # ── Utilidades internas ───────────────────────────────────────────
    @staticmethod
    def _folder_of(ch, raw_id):
        """Devuelve el recordset de la carpeta si pertenece a `ch`.

        - '' / '0' / None -> None (ítem sin carpeta, permitido).
        - id válido de la plantilla -> recordset.
        - id ajeno a la plantilla -> False (señal de error).
        """
        fid = _to_int(raw_id, 0)
        if not fid:
            return None
        folder = ch.folder_ids.filtered(lambda f: f.id == fid)
        return folder or False
