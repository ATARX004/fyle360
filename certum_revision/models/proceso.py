# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .tz_utils import today_lima

_logger = logging.getLogger(__name__)

# Defaults; los valores vivos se leen de ir.config_parameter.
DEFAULT_PLAZO_DIAS = 30      # plazo del proveedor: inicio + N días
DEFAULT_DIAS_APERTURA = 90   # (legacy) usado solo por el cron de apertura auto
DEFAULT_DIAS_URGENTE = 7
DEFAULT_DIAS_CRITICO = 3


class CertumRevProceso(models.Model):
    _name = 'certum.rev.proceso'
    _description = 'Proceso de revisión y aceptación'
    _inherit = ['mail.thread']
    _order = 'fecha_inicio desc, id desc'

    name = fields.Char(default=lambda self: _('Nuevo'), copy=False,
                       readonly=True)
    proveedor_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True, tracking=True,
        domain=[('is_company', '=', True)])
    cliente_id = fields.Many2one(
        'res.partner', string='Cliente', required=True, tracking=True,
        domain=[('is_company', '=', True)])
    checklist_id = fields.Many2one('certum.rev.checklist', string='Checklist',
                                   required=True)
    # ── Plazo hacia adelante: fecha_limite = fecha_inicio + plazo_dias ──
    fecha_inicio = fields.Date(
        string='Fecha de inicio', tracking=True, copy=False,
        help='Cuándo arranca el plazo del proveedor. Al abrir el proceso se '
             'usa hoy si se deja vacía.')
    plazo_dias = fields.Integer(
        string='Plazo (días)', tracking=True,
        default=lambda self: self._param_int('certum_revision.plazo_dias',
                                             DEFAULT_PLAZO_DIAS),
        help='Días que tiene el proveedor para publicar, contados desde la '
             'fecha de inicio.')
    fecha_vencimiento = fields.Date(
        string='Vencimiento del proveedor', tracking=True,
        help='Informativo: caducidad del certificado/documento del proveedor. '
             'No condiciona el plazo del proceso.')
    fecha_apertura = fields.Date(readonly=True, copy=False)
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('publicacion', 'Publicación'),
        ('revision', 'Revisión'),
        ('completado', 'Completado'),
        ('fuera_plazo', 'Fuera de plazo'),
    ], default='borrador', tracking=True, copy=False)

    folder_ids = fields.One2many('certum.rev.carpeta', 'proceso_id',
                                 string='Carpetas')
    item_ids = fields.One2many('certum.rev.item', 'proceso_id', string='Ítems')
    solicitud_ids = fields.One2many('certum.rev.solicitud', 'proceso_id',
                                    string='Solicitudes de plazo')

    # ── Política de revisión (la fija el nivel 1 del cliente) ──────────
    revision_modo = fields.Selection([
        ('cualquiera', 'Cualquier nivel aprueba'),
        ('secuencial', 'Aprobación por capas (secuencial)'),
    ], default='cualquiera', string='Modo de revisión', copy=False,
        help='Cualquiera: un contacto del cliente aprueba y listo. '
             'Secuencial: se aprueba capa por capa hasta el nivel 1.')
    revision_capas = fields.Integer(
        string='Capas de aprobación', default=1, copy=False,
        help='En modo secuencial, cuántos niveles deben aprobar en orden '
             'desde el número más alto hasta el 1 (nivel 1 = máximo).')
    revision_config = fields.Boolean(
        string='Política configurada', default=False, copy=False,
        help='Marca que el nivel 1 del cliente ya definió la política.')

    # ── Calculados (no almacenados: dependen del día de hoy) ──────────
    fecha_limite = fields.Date(compute='_compute_fase')
    fase = fields.Selection([
        ('previa', 'Previa a la apertura'),
        ('en_curso', 'En curso'),
        ('vencida', 'Plazo vencido'),
    ], compute='_compute_fase')
    dias_para_cambio = fields.Integer(compute='_compute_fase')
    fuera_de_plazo = fields.Boolean(compute='_compute_fase')
    semaforo = fields.Selection([
        ('a_tiempo', 'A tiempo'),
        ('urgente', 'Urgente'),
        ('critico', 'Crítico'),
        ('na', 'N/A'),
    ], compute='_compute_fase')

    avance = fields.Float(string='Avance (%)', compute='_compute_avance')
    total_items = fields.Integer(compute='_compute_avance')
    items_aprobados = fields.Integer(compute='_compute_avance')
    items_publicados = fields.Integer(compute='_compute_avance')
    items_observados = fields.Integer(compute='_compute_avance')
    items_pendientes = fields.Integer(compute='_compute_avance')

    # ─────────────────────────────────────────────────────────────────
    @api.model
    def _param_int(self, key, default):
        icp = self.env['ir.config_parameter'].sudo()
        try:
            return int(icp.get_param(key, default))
        except (TypeError, ValueError):
            return default

    _MAX_PLAZO_DIAS = 3650  # 10 años: evita OverflowError en fecha_inicio+timedelta

    @api.constrains('plazo_dias')
    def _check_plazo_dias(self):
        for proc in self:
            if proc.plazo_dias < 0 or proc.plazo_dias > self._MAX_PLAZO_DIAS:
                raise ValidationError(_(
                    'El plazo debe estar entre 0 y %s días.', self._MAX_PLAZO_DIAS))

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) in (False, _('Nuevo')):
                vals['name'] = seq.next_by_code('certum.rev.proceso') or _('Nuevo')
        records = super().create(vals_list)
        records._guard_duplicado()
        return records

    def _guard_duplicado(self):
        """Anti-duplicado: proveedor + checklist + año de referencia.

        Si el proceso aún no tiene fecha, se usa hoy como referencia para no
        dejar un hueco que permita duplicados (create + action_abrir sin fecha).
        """
        for proc in self:
            ref = proc.fecha_inicio or proc.fecha_vencimiento or today_lima()
            year = ref.year
            hermanos = self.search([
                ('id', '!=', proc.id),
                ('proveedor_id', '=', proc.proveedor_id.id),
                ('checklist_id', '=', proc.checklist_id.id),
            ])
            for h in hermanos:
                href = h.fecha_inicio or h.fecha_vencimiento
                if href and href.year == year:
                    raise ValidationError(_(
                        'Ya existe un proceso de %(proveedor)s con el checklist '
                        '"%(checklist)s" para el año %(year)s.',
                        proveedor=proc.proveedor_id.display_name,
                        checklist=proc.checklist_id.display_name, year=year))

    # ── Apertura ──────────────────────────────────────────────────────
    def action_abrir(self):
        for proc in self:
            if proc.state != 'borrador':
                raise UserError(_('El proceso ya fue abierto.'))
            if not proc.checklist_id.item_ids:
                raise UserError(_('El checklist no tiene ítems.'))
            if not proc.fecha_inicio:
                proc.fecha_inicio = today_lima()
            proc._guard_duplicado()
            with self.env.cr.savepoint():
                proc._copiar_checklist()
                proc.write({
                    'state': 'publicacion',
                    'fecha_apertura': today_lima(),
                })
            _logger.info('[AUDIT] proceso_abrir user=%s proceso=%s items=%s',
                         self.env.user.id, proc.id, len(proc.item_ids))
        return True

    def _copiar_checklist(self):
        self.ensure_one()
        Carpeta = self.env['certum.rev.carpeta']
        Item = self.env['certum.rev.item']
        folder_map = {}
        for folder in self.checklist_id.folder_ids:
            carpeta = Carpeta.create({
                'proceso_id': self.id,
                'name': folder.name,
                'sequence': folder.sequence,
            })
            folder_map[folder.id] = carpeta.id
        for it in self.checklist_id.item_ids:
            Item.create({
                'proceso_id': self.id,
                'carpeta_id': folder_map.get(it.folder_id.id),
                'name': it.name,
                'description': it.description,
                'required': it.required,
                'sequence': it.sequence,
                'doc_template_code': it.doc_template_code,
            })

    def action_marcar_fuera_plazo(self):
        for proc in self:
            if proc.state in ('publicacion', 'revision'):
                proc.state = 'fuera_plazo'
                _logger.info('[AUDIT] proceso_fuera_plazo user=%s proceso=%s',
                             self.env.user.id, proc.id)
        return True

    def _check_completado(self):
        for proc in self:
            objetivo = proc.item_ids.filtered('required') or proc.item_ids
            if objetivo and all(i.state == 'aprobado' for i in objetivo):
                proc.state = 'completado'
                _logger.info('[AUDIT] proceso_completado proceso=%s', proc.id)

    # ── Fases y avance ────────────────────────────────────────────────
    @api.depends('fecha_inicio', 'plazo_dias', 'state')
    def _compute_fase(self):
        hoy = today_lima()
        d_ur = self._param_int('certum_revision.dias_urgente', DEFAULT_DIAS_URGENTE)
        d_cr = self._param_int('certum_revision.dias_critico', DEFAULT_DIAS_CRITICO)
        for proc in self:
            if not proc.fecha_inicio:
                # Sin fecha de inicio (borrador): el plazo aún no corre.
                proc.update({'fecha_limite': False, 'fase': 'previa',
                             'dias_para_cambio': 0, 'fuera_de_plazo': False,
                             'semaforo': 'na'})
                continue
            limite = proc.fecha_inicio + timedelta(days=proc.plazo_dias or 0)
            proc.fecha_limite = limite
            if hoy < proc.fecha_inicio:
                fase, dias = 'previa', (proc.fecha_inicio - hoy).days
            elif hoy <= limite:
                fase, dias = 'en_curso', (limite - hoy).days
            else:
                fase, dias = 'vencida', 0
            proc.fase = fase
            proc.dias_para_cambio = dias
            proc.fuera_de_plazo = (
                fase == 'vencida' and proc.state not in ('completado', 'borrador'))
            if fase != 'en_curso' or proc.state in ('completado', 'borrador'):
                proc.semaforo = 'na'
            elif dias <= d_cr:
                proc.semaforo = 'critico'
            elif dias <= d_ur:
                proc.semaforo = 'urgente'
            else:
                proc.semaforo = 'a_tiempo'

    @api.depends('item_ids.state')
    def _compute_avance(self):
        for proc in self:
            items = proc.item_ids
            proc.total_items = len(items)
            proc.items_aprobados = len(items.filtered(lambda i: i.state == 'aprobado'))
            proc.items_publicados = len(items.filtered(lambda i: i.state == 'publicado'))
            proc.items_observados = len(items.filtered(lambda i: i.state == 'observado'))
            proc.items_pendientes = len(items.filtered(lambda i: i.state == 'pendiente'))
            proc.avance = (100.0 * proc.items_aprobados / proc.total_items) if items else 0.0
