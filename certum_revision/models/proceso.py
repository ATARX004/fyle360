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
    # Etiqueta libre para distinguir expedientes que comparten plantilla y
    # cliente (obra, sede, contrato, periodo...). Opcional.
    referencia = fields.Char(
        string='Referencia', tracking=True,
        help='Cómo distinguir este expediente de otros hechos con la misma '
             'plantilla: obra, sede, contrato o periodo.')
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
        ('personas', 'Participantes designados (en orden)'),
    ], default='cualquiera', string='Modo de revisión', copy=False,
        help='Cualquiera: un contacto del cliente aprueba y listo. '
             'Secuencial: se aprueba capa por capa hasta el nivel 1. '
             'Personas: solo participan los contactos designados, en el orden '
             'indicado; el último es la máxima autoridad.')
    # Participantes del proceso (modo 'personas'). Cadena por defecto de todos
    # sus ítems; un ítem puede sobrescribirla con la suya propia.
    revisor_ids = fields.One2many('certum.rev.revisor', 'proceso_id',
                                  string='Participantes de la revisión',
                                  copy=False)
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
        """Evita el duplicado ACCIDENTAL, no la reutilización de la plantilla.

        Una plantilla está hecha para usarse muchas veces: con varios clientes
        y varias veces al mismo año. Por eso solo se considera duplicado un
        proceso IDÉNTICO en las cinco cosas que lo definen —proveedor, cliente,
        plantilla, fecha de inicio y referencia—, que es el resultado típico de
        pulsar dos veces "Iniciar proceso".

        La `referencia` es además la salida cuando sí se quieren dos
        expedientes el mismo día para el mismo cliente (dos obras, dos sedes):
        basta con etiquetarlos distinto.
        """
        for proc in self:
            fecha = proc.fecha_inicio or today_lima()
            ref = (proc.referencia or '').strip().lower()
            gemelos = self.search([
                ('id', '!=', proc.id),
                ('proveedor_id', '=', proc.proveedor_id.id),
                ('cliente_id', '=', proc.cliente_id.id),
                ('checklist_id', '=', proc.checklist_id.id),
                ('fecha_inicio', '=', fecha),
            ]).filtered(
                lambda h: (h.referencia or '').strip().lower() == ref)
            if gemelos:
                raise ValidationError(_(
                    'Ya existe un expediente idéntico (%(otro)s): mismo cliente, '
                    'misma plantilla y misma fecha de inicio. Si de verdad '
                    'necesitas otro, cambia la fecha de inicio o ponle una '
                    'referencia que lo distinga (obra, sede, contrato…).',
                    otro=gemelos[0].name))

    # ── Apertura ──────────────────────────────────────────────────────
    @api.model
    def fyle_menu(self, ruta=''):
        """El menú lateral del usuario actual: rol, entradas y contadores.

        Lo llama el marco (views/portal_common.xml, `sr_menu`) en cada
        página. El rol es el GLOBAL —el de su empresa, o «interno» si es
        usuario interno—, no el que tenga en un proyecto concreto: el menú no
        cambia al entrar a un proyecto. `ruta` es la de la página, para
        marcar la entrada activa.
        """
        user = self.env.user
        empresa = user.partner_id.commercial_partner_id
        rol = 'interno' if not user.share else (empresa.sudo().rol_en_certum or '')
        Item = self.env['certum.rev.item'].sudo()
        activos = [('proceso_id.state', 'in', ('publicacion', 'revision'))]

        def entrada(nombre, url, icono, prefijos=(), n=0):
            activo = ruta == url or any(ruta.startswith(p) for p in prefijos)
            return {'nombre': nombre, 'url': url, 'icono': icono, 'n': n, 'activo': activo}

        inicio = entrada('Inicio', '/my/certum', 'i-home')
        inicio['activo'] = ruta in ('/my/certum', '/my/certum/admin')
        recibidos = entrada('Recibidos', '/my/repositorio', 'i-download', ('/my/repositorio',))
        principal, admin = [inicio], []
        if rol == 'proveedor':
            principal += [
                entrada('Mis proyectos', '/my/procesos', 'i-folder', ('/my/proceso',),
                        Item.search_count(activos + [('proveedor_id', '=', empresa.id),
                                                     ('state', '=', 'observado')])),
                entrada('Plantillas', '/my/plantillas', 'i-doc', ('/my/plantilla',)),
            ]
        elif rol == 'cliente':
            principal.append(
                entrada('Revisiones', '/my/revisiones', 'i-eye', ('/my/revisiones', '/my/proceso'),
                        Item.search_count(activos + [('cliente_id', '=', empresa.id),
                                                     ('state', '=', 'publicado')])))
        principal.append(recibidos)
        if rol == 'interno':
            base = '/my/certum/admin'
            admin = [
                entrada('Empresas y roles', base + '/empresas', 'i-building'),
                entrada('Plantillas', '/my/plantillas', 'i-doc', ('/my/plantilla',)),
                entrada('Proyectos', base + '/proyectos', 'i-folder', ('/my/proceso',),
                        self.sudo().search_count([('state', '=', 'fuera_plazo')])),
                entrada('Correos', base + '/correos', 'i-send', (base + '/correos',),
                        self.env['certum.rev.correo.envio'].sudo().search_count(
                            [('estado', '=', 'fallido'), ('origen', '!=', 'prueba')])),
                entrada('Ajustes', base + '/ajustes', 'i-clock'),
            ]
        etiquetas = {'proveedor': 'Proveedor', 'cliente': 'Cliente', 'interno': 'Certum Global'}
        return {
            'rol': rol,
            'rol_nombre': etiquetas.get(rol, 'Sin rol asignado'),
            'empresa': empresa.sudo(),
            'principal': principal,
            'admin': admin,
            'admin_abierto': any(e['activo'] for e in admin),
        }

    @api.model
    def _retirar_copias_web(self):
        """Lo que corre en cada -u (data/portal_data.xml). Idempotente.

        Si alguien abre una pantalla de FYLE 360 con el editor del sitio web
        y guarda, Odoo crea una copia de la vista para ese sitio que TAPA la
        del módulo: a partir de ahí ninguna actualización se ve. Estas
        pantallas son una aplicación, no páginas de contenido, así que esas
        copias se retiran.
        """
        copias = self.env['ir.ui.view'].sudo().with_context(active_test=False).search([
            ('key', '=like', 'certum_revision.%'), ('website_id', '!=', False)])
        if copias:
            _logger.info('[AUDIT] copias_web_retiradas %s', ','.join(copias.mapped('key')))
            copias.unlink()

    def action_abrir(self):
        for proc in self:
            if proc.state != 'borrador':
                raise UserError(_('El proyecto ya fue abierto.'))
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
        # Recorrido por profundidad: garantiza que la carpeta padre ya existe
        # cuando se crea la hija, para reproducir el árbol tal cual.
        for folder in self.checklist_id.folder_ids.sorted(
                key=lambda f: (f.nivel, f.sequence, f.id)):
            carpeta = Carpeta.create({
                'proceso_id': self.id,
                'name': folder.name,
                'sequence': folder.sequence,
                'parent_id': folder_map.get(folder.parent_id.id),
                'origen_id': folder.id,
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
                'origen_id': it.id,
            })

    # ── Reestructuración del expediente ───────────────────────────────
    def puede_reestructurar(self):
        """El expediente admite cambios de estructura mientras esté ACTIVO.

        En 'completado' se bloquea a propósito: añadir un requisito pendiente
        dejaría el expediente cerrado y con algo sin aprobar a la vez. Reabrirlo
        es una decisión con consecuencias (plazos, avisos) que no debe salir de
        un botón de "nueva carpeta".
        """
        self.ensure_one()
        return self.state in ('publicacion', 'revision')

    def diff_estructura(self):
        """Compara la estructura ACTUAL del expediente con su plantilla.

        Se apoya en `origen_id`, que quedó grabado al copiar la plantilla, así
        que distingue de verdad lo añadido de lo movido o renombrado, en vez de
        adivinar por el nombre.
        """
        self.ensure_one()
        d = {'nuevas': [], 'nuevos': [], 'renombrados': [], 'movidos': [],
             'quitados': []}
        ch = self.checklist_id

        # Carpetas
        for c in self.folder_ids:
            if not c.origen_id:
                d['nuevas'].append(c.ruta or c.name)
                continue
            if (c.name or '') != (c.origen_id.name or ''):
                d['renombrados'].append('%s → %s' % (c.origen_id.name, c.name))
            if c.parent_id.origen_id.id != c.origen_id.parent_id.id:
                d['movidos'].append('Carpeta «%s»' % c.name)

        # Ítems
        for it in self.item_ids:
            if not it.origen_id:
                d['nuevos'].append(it.name)
                continue
            if (it.name or '') != (it.origen_id.name or ''):
                d['renombrados'].append('%s → %s' % (it.origen_id.name, it.name))
            if it.carpeta_id.origen_id.id != it.origen_id.folder_id.id:
                d['movidos'].append('«%s» → %s' % (
                    it.name, it.carpeta_id.ruta or 'sin carpeta'))

        # Lo que estaba en la plantilla y ya no está en el expediente
        origen_carpetas = set(self.folder_ids.mapped('origen_id').ids)
        origen_items = set(self.item_ids.mapped('origen_id').ids)
        for f in ch.folder_ids:
            if f.id not in origen_carpetas:
                d['quitados'].append('Carpeta «%s»' % f.name)
        for i in ch.item_ids:
            if i.id not in origen_items:
                d['quitados'].append(i.name)

        d['total'] = sum(len(v) for k, v in d.items() if k != 'total')
        return d

    def crear_plantilla_desde_proceso(self, nombre=None):
        """Guarda la estructura ACTUAL del expediente como una plantilla NUEVA.

        No toca la plantilla original: se crea una copia aparte, y queda a
        criterio del proveedor conservar o retirar la antigua.
        """
        self.ensure_one()
        base = self.checklist_id
        Checklist = self.env['certum.rev.checklist'].sudo()
        Folder = self.env['certum.rev.checklist.folder'].sudo()
        Item = self.env['certum.rev.checklist.item'].sudo()

        nueva = Checklist.create({
            'name': (nombre or '').strip()[:200] or _(
                '%(base)s (según %(proc)s)', base=base.name, proc=self.name),
            'proveedor_id': (base.proveedor_id.id or self.proveedor_id.id),
            'sector': base.sector,
            'plazo_dias': base.plazo_dias,
            'description': _(
                'Estructura tomada del expediente %(proc)s el %(fecha)s. La '
                'plantilla original «%(base)s» se conserva sin cambios.',
                proc=self.name, fecha=today_lima().strftime('%d/%m/%Y'),
                base=base.name),
        })

        # Árbol por profundidad: la carpeta padre existe antes que la hija.
        mapa = {}
        for c in self.folder_ids.sorted(key=lambda c: (c.nivel, c.sequence, c.id)):
            nf = Folder.create({
                'checklist_id': nueva.id,
                'name': c.name,
                'sequence': c.sequence,
                'parent_id': mapa.get(c.parent_id.id),
            })
            mapa[c.id] = nf.id
        for it in self.item_ids.sorted(key=lambda i: (i.sequence, i.id)):
            Item.create({
                'checklist_id': nueva.id,
                'folder_id': mapa.get(it.carpeta_id.id),
                'name': it.name,
                'description': it.description,
                'required': it.required,
                'sequence': it.sequence,
                'doc_template_code': it.doc_template_code,
            })
        _logger.info('[AUDIT] plantilla_desde_proceso user=%s proceso=%s '
                     'plantilla=%s', self.env.user.id, self.id, nueva.id)
        return nueva

    def write(self, vals):
        res = super().write(vals)
        # Si alguien empuja el plazo hacia adelante, el expediente deja de estar
        # vencido. Va aquí y no solo en la aprobación de la solicitud para que
        # NINGÚN camino que amplíe el plazo se olvide de revivirlo.
        if 'plazo_dias' in vals or 'fecha_inicio' in vals:
            self._revivir_si_hay_plazo()
        return res

    def _revivir_si_hay_plazo(self):
        """Saca de 'fuera_plazo' al expediente cuyo límite vuelve al futuro.

        Quedarse en 'fuera_plazo' con días por delante no es solo una etiqueta
        equivocada: el expediente queda CONGELADO —no se puede publicar,
        aprobar ni observar, solo comentar—, así que ampliar el plazo no
        serviría de nada. Se vuelve a 'revision' si ya se publicó algo y a
        'publicacion' si aún no.
        """
        hoy = today_lima()
        for proc in self:
            if proc.state != 'fuera_plazo' or not proc.fecha_inicio:
                continue
            limite = proc.fecha_inicio + timedelta(days=proc.plazo_dias or 0)
            if hoy > limite:
                continue
            hubo_publicacion = any(i.state != 'pendiente' for i in proc.item_ids)
            proc.state = 'revision' if hubo_publicacion else 'publicacion'
            _logger.info('[AUDIT] proceso_revivido proceso=%s estado=%s '
                         'limite=%s', proc.id, proc.state, limite)
            # Revivir NO cierra: aunque esté todo aprobado, el cierre lo
            # decide el proveedor (ver `cerrar_proyecto`).

    def action_marcar_fuera_plazo(self):
        for proc in self:
            if proc.state in ('publicacion', 'revision'):
                proc.state = 'fuera_plazo'
                _logger.info('[AUDIT] proceso_fuera_plazo user=%s proceso=%s',
                             self.env.user.id, proc.id)
        return True

    def _objetivo(self):
        """Documentos que deciden si el proyecto está terminado: los
        obligatorios, o todos si ninguno lo es."""
        self.ensure_one()
        return self.item_ids.filtered('required') or self.item_ids

    def listo_para_cerrar(self):
        """Todo lo obligatorio está aprobado, pero el proyecto sigue abierto.

        **Aprobarlo todo ya no lo cierra.** El cierre es un acto deliberado del
        proveedor, y hasta que ocurra el proyecto admite cambios: reorganizar
        carpetas, renombrar, añadir un documento que faltaba. Cerrar en
        automático al aprobar el último dejaba el proyecto congelado justo
        cuando más se suele querer retocarlo.
        """
        self.ensure_one()
        if self.state not in ('publicacion', 'revision'):
            return False
        objetivo = self._objetivo()
        return bool(objetivo) and all(i.state == 'aprobado' for i in objetivo)

    def cerrar_proyecto(self, partner=None):
        """Cierra el proyecto. Lo decide una persona, no el sistema."""
        self.ensure_one()
        if self.state == 'completado':
            raise UserError(_('Este proyecto ya está cerrado.'))
        if self.state not in ('publicacion', 'revision'):
            raise UserError(_('Solo se cierra un proyecto activo.'))
        objetivo = self._objetivo()
        if not objetivo:
            raise UserError(_('El proyecto no tiene documentos que cerrar.'))
        faltan = objetivo.filtered(lambda i: i.state != 'aprobado')
        if faltan:
            raise UserError(_(
                'Faltan %(n)s documento(s) por aprobar: %(cuales)s',
                n=len(faltan),
                cuales=', '.join(faltan[:5].mapped('name'))
                + ('…' if len(faltan) > 5 else '')))
        self.state = 'completado'
        _logger.info('[AUDIT] proceso_cerrado user=%s proceso=%s',
                     self.env.user.id, self.id)
        return True

    def reabrir_proyecto(self, partner=None):
        """Vuelve a abrir un proyecto cerrado, para poder reorganizarlo.

        Es la vuelta atrás del cierre manual: si cerrar es una decisión, tiene
        que poder deshacerse. Los documentos no se tocan —siguen aprobados—,
        solo se levanta el candado que impedía reorganizar y publicar.
        """
        self.ensure_one()
        if self.state != 'completado':
            raise UserError(_('Este proyecto no está cerrado.'))
        self.state = 'revision'
        _logger.info('[AUDIT] proceso_reabierto user=%s proceso=%s',
                     self.env.user.id, self.id)
        # Si mientras estaba cerrado se pasó el plazo, que se note enseguida
        # y no en la próxima pasada del cron.
        if self.fase == 'vencida':
            self.action_marcar_fuera_plazo()
        return True

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
