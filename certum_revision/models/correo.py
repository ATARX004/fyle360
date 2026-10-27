# -*- coding: utf-8 -*-
"""Correos de FYLE 360: las plantillas, la cola y el historial.

Sigue la misma metodología que los correos del e-learning
(dv_custom_website_slides, T-30). Tres piezas:

* `certum.rev.correo.caso` — cada situación que manda un correo (documento
  publicado, observado, plazo por vencer…): si está activa, su asunto y su
  texto. Los crea data/correo_data.xml con noupdate: lo que se edite en el
  panel se queda.
* `certum.rev.correo.envio` — una fila por correo y por persona: a quién, por
  qué, cuándo y cómo acabó. Es a la vez la cola, el historial y el seguro
  contra duplicados.
* el motor, en `certum.rev.correo.envio`: avisar()/encolar(), el cron que
  procesa la cola y el cron diario que busca lo que toca por fecha.

Cuatro reglas:

1. **Nada se manda dos veces.** Cada envío lleva una `clave` única (caso,
   persona, registro y referencia). Encolar lo que ya existe no hace nada,
   así que el cron diario puede repasar días atrasados y la pestaña
   Recuperación puede reenviar sin miedo.
2. **Un disparador solo encola.** Publicar, aprobar u observar no esperan al
   servidor de correo, y un fallo al encolar no tumba la transición que lo
   disparó: va en un savepoint y se anota en el log.
3. **Antes de mandar se vuelve a mirar** (`_vigente`): un «por vencer» de un
   documento que ya se revisó, o un «observado» que ya se corrigió, no sale;
   queda como «No se envió» con el motivo.
4. **Lo que ya había antes de instalar esto no se avisa.** El parámetro
   `certum_revision.correo_desde` se fija la primera vez: la recuperación no
   propone avisar de publicaciones de hace meses.

El texto de las plantillas es **plano**, con variables `{nombre}`,
`{documento}`… (lista en VARIABLES): no se usa `mail.template` para que nadie
pueda meter Jinja ni HTML desde el panel.

Tampoco se fija idioma (`lang`) en ningún sitio: los textos ya están en
español y el marco se pinta con el idioma del entorno. Un código fijo como
es_PE rompe el envío si la base no lo tiene instalado («Invalid language
code»), como pasó en homologacion_portal (506f65e).
"""

import logging
import re
from datetime import timedelta
from email.utils import formataddr

from markupsafe import Markup, escape

from odoo import api, fields, models

from .tz_utils import fmt_lima, today_lima

_logger = logging.getLogger(__name__)

PARAM_DESDE = 'certum_revision.correo_desde'
PARAM_SERVIDOR = 'certum_revision.correo_servidor_id'
PARAM_NOMBRE = 'certum_revision.correo_nombre'
PARAM_CONTACTO = 'certum_revision.correo_contacto'
PARAM_PAUSA = 'certum_revision.correo_pausado'

NOMBRE_POR_DEFECTO = 'FYLE 360'
CONTACTO_POR_DEFECTO = 'sistemas@certumglobal.pe'

EMAIL_RE = re.compile(r'^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$')

CRON_COLA = 'certum_revision.cron_correos_enviar'
CRON_DIARIO = 'certum_revision.cron_correos_diario'

# Estados de mail.mail -> estado del envío.
_ESTADO_MAIL = {
    'outgoing': 'en_cola',
    'sent': 'enviado',
    'received': 'enviado',
    'exception': 'fallido',
    'cancel': 'fallido',
}

# Variables que admite el texto de una plantilla. Es también la ayuda que
# enseña el panel: si se añade una, se documenta aquí.
VARIABLES = [
    ('nombre', 'Nombre de quien recibe el correo'),
    ('proyecto', 'Código del proyecto'),
    ('referencia', 'Referencia del proyecto (obra, sede, contrato…)'),
    ('plantilla', 'Plantilla con la que se armó el proyecto'),
    ('documento', 'Nombre del documento'),
    ('carpeta', 'Carpeta donde está el documento'),
    ('proveedor', 'Empresa proveedora'),
    ('cliente', 'Empresa cliente'),
    ('vence', 'Fecha límite que corresponde a ese correo'),
    ('dias', 'Días que faltan para esa fecha'),
    ('observacion', 'Texto de la observación del cliente'),
    ('total', 'Cuántos documentos incluye el correo'),
    ('contacto', 'Correo de soporte de Certum'),
    ('solicitante', 'Quién pide eliminar el proyecto (solo en la eliminación)'),
    ('codigo', 'Código para confirmar la eliminación (solo en la eliminación)'),
]

# Códigos que se avisan por fecha (cron diario) y los que dispara una acción.
POR_FECHA = ('pendientes_revision', 'revision_por_vencer',
             'correccion_por_vencer', 'plazo_por_vencer')


class _Variables(dict):
    """Para str.format_map: una variable que no existe se deja tal cual.

    Así una plantilla con «{nombre}» mal escrito no revienta el envío entero:
    sale el texto con las llaves y se ve en la vista previa.
    """

    def __missing__(self, clave):
        return '{%s}' % clave


def _fecha(dia):
    return dia.strftime('%d/%m/%Y') if dia else ''


class CertumRevCorreoCaso(models.Model):
    _name = 'certum.rev.correo.caso'
    _description = 'FYLE 360 · correo: plantilla'
    _order = 'orden, id'

    codigo = fields.Char('Código', required=True, readonly=True)
    name = fields.Char('Nombre', required=True)
    cuando = fields.Text('Cuándo se envía', readonly=True)
    para = fields.Char('A quién', readonly=True)
    activo = fields.Boolean('Activo', default=True)
    # Los correos de seguridad (el código de eliminación) no se pueden
    # desactivar: sin ellos la acción que protegen quedaría bloqueada.
    obligatorio = fields.Boolean(readonly=True)
    orden = fields.Integer(default=10)
    asunto = fields.Char('Asunto', required=True)
    texto = fields.Text(
        'Texto', required=True,
        help='Un párrafo por bloque, separados por una línea en blanco. '
             'Admite variables entre llaves: {nombre}, {documento}…')
    boton = fields.Char('Texto del botón')
    dias = fields.Integer('Días')
    dias_ayuda = fields.Char(readonly=True)
    # Lo que el marco añade por su cuenta, según el caso. No se edita: es
    # estructura, no texto.
    lista = fields.Selection([
        ('pendientes', 'Documentos por revisar'),
        ('difusion', 'Documentos difundidos'),
    ], readonly=True)
    cita = fields.Selection([
        ('observacion', 'La observación del cliente'),
        ('mensaje', 'El mensaje de quien difunde'),
    ], readonly=True)

    _sql_constraints = [
        ('codigo_unico', 'unique(codigo)', 'Ya existe una plantilla con ese código.'),
    ]


class CertumRevCorreoEnvio(models.Model):
    _name = 'certum.rev.correo.envio'
    _description = 'FYLE 360 · correo: envío'
    _order = 'create_date desc, id desc'
    _rec_name = 'asunto'

    caso_id = fields.Many2one('certum.rev.correo.caso', 'Plantilla', required=True,
                              ondelete='restrict', index=True)
    partner_id = fields.Many2one('res.partner', 'Destinatario', ondelete='set null', index=True)
    email = fields.Char('Correo')
    email_cc = fields.Char('Copia', help='Las copias del cliente del proyecto. Van solo en '
                                         'el primer correo de cada aviso: una copia por aviso, '
                                         'no una por destinatario.')
    proceso_id = fields.Many2one('certum.rev.proceso', 'Proyecto', ondelete='cascade', index=True)
    item_id = fields.Many2one('certum.rev.item', 'Documento', ondelete='cascade', index=True)
    difusion_id = fields.Many2one('certum.rev.difusion', 'Difusión', ondelete='cascade', index=True)
    # Sin proyecto a propósito: el aviso de una eliminación tiene que
    # sobrevivir al borrado del proyecto que anuncia.
    eliminacion_id = fields.Many2one('certum.rev.eliminacion', 'Eliminación',
                                     ondelete='cascade', index=True)
    referencia = fields.Char()
    clave = fields.Char(required=True, index=True, copy=False)
    estado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('en_cola', 'En cola de salida'),
        ('enviado', 'Enviado'),
        ('fallido', 'Fallido'),
        ('cancelado', 'No se envió'),
    ], default='pendiente', required=True, index=True)
    origen = fields.Selection([
        ('automatico', 'Automático'),
        ('recuperacion', 'Recuperación manual'),
        ('prueba', 'Prueba'),
        ('seguridad', 'Seguridad'),
    ], default='automatico', required=True)
    asunto = fields.Char()
    motivo = fields.Char('Detalle', help='Por qué falló o por qué no se envió.')
    mail_id = fields.Many2one('mail.mail', 'Correo saliente', ondelete='set null')
    fecha_envio = fields.Datetime('Enviado el')
    intentos = fields.Integer(default=0)

    _sql_constraints = [
        ('clave_unica', 'unique(clave)', 'Ese correo ya está registrado.'),
    ]

    # ═══ Configuración ═══════════════════════════════════════════════════
    @api.model
    def _parametro(self, clave, defecto=''):
        return self.env['ir.config_parameter'].sudo().get_param(clave) or defecto

    @api.model
    def _desde(self):
        valor = self._parametro(PARAM_DESDE)
        return fields.Datetime.to_datetime(valor) if valor else fields.Datetime.now()

    @api.model
    def _contacto(self):
        return self._parametro(PARAM_CONTACTO, CONTACTO_POR_DEFECTO)

    @api.model
    def _pausado(self):
        """Envío automático en pausa: nada sale solo. Es para ensayar el flujo
        en la base real sin llenar de correos los buzones de gente real; lo
        que tocaba aparece en Recuperación y se puede mandar a mano."""
        return self._parametro(PARAM_PAUSA) == '1'

    @api.model
    def _servidor(self):
        """El ir.mail_server elegido en el panel, o vacío (el de Odoo)."""
        valor = self._parametro(PARAM_SERVIDOR)
        if not valor or not valor.isdigit():
            return self.env['ir.mail_server']
        servidor = self.env['ir.mail_server'].sudo().browse(int(valor)).exists()
        return servidor if servidor and servidor.active else self.env['ir.mail_server']

    @api.model
    def _buzon(self, servidor):
        """El buzón desde el que deja enviar un servidor: su from_filter si es
        una dirección, o su usuario SMTP."""
        if not servidor:
            return ''
        if servidor.from_filter and '@' in servidor.from_filter:
            return servidor.from_filter.split(',')[0].strip()
        if servidor.smtp_user and '@' in servidor.smtp_user:
            return servidor.smtp_user
        return ''

    @api.model
    def _remitente(self):
        """«FYLE 360 <buzón>», con el buzón que el servidor deja usar.

        Office 365 rechaza un From que no sea el buzón autenticado: por eso la
        dirección sale del servidor elegido y no se escribe a mano.
        """
        nombre = self._parametro(PARAM_NOMBRE, NOMBRE_POR_DEFECTO)
        buzon = self._buzon(self._servidor())
        if not buzon:
            buzon = self.env['ir.mail_server'].sudo()._get_default_from_address() or self._contacto()
        return formataddr((nombre, buzon))

    @api.model
    def _instalar_correos(self):
        """Lo que corre en cada -u (data/correo_data.xml). Idempotente.

        * Fija `correo_desde` la primera vez: lo anterior no se avisa.
        * Elige el servidor de sistemas@ si no hay ninguno elegido.
        * Retira las plantillas mail.template y los crons del sistema de
          avisos anterior, que ya no se usan.
        """
        Param = self.env['ir.config_parameter'].sudo()
        if not Param.get_param(PARAM_DESDE):
            Param.set_param(PARAM_DESDE, fields.Datetime.to_string(fields.Datetime.now()))
        if not Param.get_param(PARAM_NOMBRE):
            Param.set_param(PARAM_NOMBRE, NOMBRE_POR_DEFECTO)
        if not Param.get_param(PARAM_CONTACTO):
            Param.set_param(PARAM_CONTACTO, CONTACTO_POR_DEFECTO)
        # Sin servidor elegido saldrían desde el remitente por defecto de Odoo
        # (notifications@…), que Office 365 rechaza por no ser su buzón.
        if not Param.get_param(PARAM_SERVIDOR):
            sistemas = self.env['ir.mail_server'].sudo().search(
                ['|', ('from_filter', '=', CONTACTO_POR_DEFECTO),
                 ('smtp_user', '=', CONTACTO_POR_DEFECTO)], limit=1)
            if sistemas:
                Param.set_param(PARAM_SERVIDOR, str(sistemas.id))
        viejos = []
        for xmlid in ('template_item_publicado', 'template_item_aprobado',
                      'template_item_observado', 'template_item_turno_devuelto',
                      'template_pendientes_revision', 'template_revision_por_vencer',
                      'template_correccion_por_vencer', 'template_difusion',
                      'cron_aviso_pendientes', 'cron_aviso_por_vencer'):
            registro = self.env.ref('certum_revision.%s' % xmlid, raise_if_not_found=False)
            if registro:
                viejos.append(xmlid)
                registro.sudo().unlink()
        if viejos:
            _logger.info('[AUDIT] correos_antiguos_retirados %s', ','.join(viejos))

    # ═══ Destinatarios ═══════════════════════════════════════════════════
    @api.model
    def _personas(self, empresa, proceso=None):
        """Las personas de una empresa con correo y, si su buzón no es el de
        ninguna de ellas, la propia empresa.

        Se avisa a las personas, no solo a la empresa: un buzón genérico que
        nadie mira es la forma más común de que un plazo se venza «sin que
        nadie se enterara».

        Si ese lado del `proceso` usa roles propios, solo a las personas de
        su lista: quien no interviene en el proyecto no recibe sus correos, y
        tampoco el buzón genérico de la empresa.
        """
        if not empresa:
            return self.env['res.partner']
        if proceso:
            lado = proceso._lado_de(empresa)
            if lado and proceso.roles_propios(lado):
                return proceso.sudo().participante_ids.filtered(
                    lambda p: p.lado == lado).partner_id.filtered('email')
        personas = self.env['res.partner'].sudo().search([
            ('parent_id', '=', empresa.id), ('is_company', '=', False),
            ('email', '!=', False)])
        correos = {(p.email or '').strip().lower() for p in personas}
        if empresa.email and empresa.email.strip().lower() not in correos:
            personas |= empresa.sudo()
        return personas

    @api.model
    def _de_turno(self, item):
        """A quién le toca revisar AHORA este documento.

        Si la cadena nombra personas, solo a esa persona: avisar a los cinco
        contactos de que le toca a uno es la mejor manera de que ninguno haga
        nada. Si es por niveles o no hay cadena, a toda la empresa cliente.
        """
        cadena = item._cadena()
        paso = item.revision_paso or 0
        if cadena and 1 <= paso <= len(cadena):
            pid = cadena[paso - 1].get('partner_id')
            if pid:
                persona = self.env['res.partner'].sudo().browse(pid).exists()
                if persona.email and item.proceso_id.participa(persona):
                    return persona
        return self._personas(item.proceso_id.cliente_id, item.proceso_id)

    @api.model
    def _unicos(self, partners):
        """Un contacto por dirección de correo: dos fichas con el mismo
        buzón (pasa con el genérico de la empresa) no reciben el aviso dos
        veces."""
        vistos, salida = set(), self.env['res.partner']
        for p in partners:
            correo = (p.email or '').strip().lower()
            if correo and correo not in vistos:
                vistos.add(correo)
                salida |= p
        return salida

    @api.model
    def _destinatarios(self, codigo, registro):
        return self._unicos(self._destinatarios_crudos(codigo, registro))

    @api.model
    def _destinatarios_crudos(self, codigo, registro):
        if codigo in ('publicado', 'turno_devuelto', 'revision_por_vencer'):
            return self._de_turno(registro)
        if codigo == 'pendientes_revision':
            return self._personas(registro.cliente_id, registro)
        if codigo in ('aprobado', 'observado', 'correccion_por_vencer'):
            return self._personas(registro.proceso_id.proveedor_id, registro.proceso_id)
        if codigo == 'plazo_por_vencer':
            return (self._personas(registro.proveedor_id, registro)
                    | self._personas(registro.cliente_id, registro))
        if codigo == 'difusion':
            return registro.partner_ids.sudo().filtered('email')
        return self.env['res.partner']

    @api.model
    def _parsear(self, crudo):
        """Correos válidos de un texto separado por comas, puntos y coma o
        saltos de línea, sin repetir. Los inválidos se descartan: uno mal
        escrito no debe impedir que salgan los demás."""
        salida = []
        for pieza in re.split(r'[,;\s]+', crudo or ''):
            pieza = pieza.strip().lower()
            if pieza and EMAIL_RE.match(pieza) and pieza not in salida:
                salida.append(pieza)
        return salida

    @api.model
    def _copias(self, registro):
        """Las copias que pidió el cliente del proyecto de `registro`."""
        if registro._name == 'certum.rev.eliminacion':
            return []  # un correo interno no va en copia a ningún cliente
        proceso = registro if registro._name == 'certum.rev.proceso' else registro.proceso_id
        return self._parsear(proceso.sudo().cliente_id.certum_correo_cc)

    # ═══ Encolar ═════════════════════════════════════════════════════════
    @api.model
    def _clave(self, codigo, partner, registro, referencia=''):
        return ':'.join([codigo, str(partner.id if partner else 0),
                         registro._name.split('.')[-1], str(registro.id),
                         referencia or ''])

    @api.model
    def _vinculos(self, registro):
        """Campos proceso/item/difusion del envío a partir del registro."""
        if registro._name == 'certum.rev.item':
            return {'item_id': registro.id, 'proceso_id': registro.proceso_id.id}
        if registro._name == 'certum.rev.difusion':
            return {'difusion_id': registro.id, 'proceso_id': registro.proceso_id.id}
        if registro._name == 'certum.rev.eliminacion':
            return {'eliminacion_id': registro.id}
        return {'proceso_id': registro.id}

    @api.model
    def avisar(self, codigo, registro, referencia=''):
        """Encola el correo `codigo` sobre `registro` para cada destinatario.

        Es lo que llaman las transiciones. NUNCA lanza hacia fuera: publicar
        un documento tiene que funcionar aunque el correo esté roto.
        """
        try:
            with self.env.cr.savepoint():
                for partner in self._destinatarios(codigo, registro.sudo()):
                    self.encolar(codigo, registro, partner, referencia)
        except Exception:  # noqa: BLE001
            _logger.exception('correo %s: no se pudo encolar sobre %s:%s',
                              codigo, getattr(registro, '_name', '?'),
                              getattr(registro, 'id', '?'))

    @api.model
    def encolar(self, codigo, registro, partner, referencia='', origen='automatico'):
        """Pone un correo en la cola. Devuelve el envío, nuevo o el que ya había.

        No manda nada: lo hace el cron de la cola, que se despierta al
        momento. Una plantilla desactivada o la pausa general no encolan,
        salvo la recuperación manual, que es una decisión de quien la pulsa.
        """
        Envio = self.sudo()
        caso = self.env['certum.rev.correo.caso'].sudo().search([('codigo', '=', codigo)], limit=1)
        if not caso or not partner or not registro:
            return Envio
        if origen == 'automatico' and (not caso.activo or self._pausado()):
            return Envio
        clave = self._clave(codigo, partner, registro, referencia)
        existente = Envio.search([('clave', '=', clave)], limit=1)
        if existente:
            return existente
        valores = dict(self._vinculos(registro), caso_id=caso.id, partner_id=partner.id,
                       email=partner.email or '', referencia=referencia or '',
                       clave=clave, origen=origen)
        # Las copias del cliente viajan en el PRIMER correo de este aviso:
        # con un correo por persona, ponerlas en todos mandaría cinco copias
        # iguales al mismo buzón.
        vinculo = [(campo, '=', valor) for campo, valor in self._vinculos(registro).items()
                   if campo != 'proceso_id' or registro._name == 'certum.rev.proceso']
        if partner.email and not Envio.search_count(vinculo + [
                ('caso_id', '=', caso.id), ('referencia', '=', referencia or ''),
                ('email_cc', '!=', False)]):
            propio = partner.email.strip().lower()
            valores['email_cc'] = ', '.join(c for c in self._copias(registro) if c != propio) or False
        if not partner.email:
            valores.update(estado='cancelado', motivo='La persona no tiene correo registrado.')
        try:
            with self.env.cr.savepoint():
                envio = Envio.create(valores)
        except Exception:  # noqa: BLE001 - la clave única, si otro llegó antes
            return Envio.search([('clave', '=', clave)], limit=1)
        # Los de seguridad los manda en el acto quien los encola.
        if envio.estado == 'pendiente' and origen != 'seguridad':
            cron = self.env.ref(CRON_COLA, raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        return envio

    # ═══ Lo que necesita cada caso ═══════════════════════════════════════
    def _registro(self):
        self.ensure_one()
        return (self.item_id or self.difusion_id or self.eliminacion_id or self.proceso_id).sudo()

    @api.model
    def _url(self, ruta):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return base.rstrip('/') + ruta

    def _boton_url(self):
        self.ensure_one()
        if self.caso_id.codigo == 'difusion':
            return self._url('/my/repositorio')
        if self.eliminacion_id:
            return self._url('/my/certum/admin/proyectos')
        if self.proceso_id:
            return self._url('/my/proceso/%s' % self.proceso_id.id)
        return self._url('/my/certum')

    @api.model
    def _dias_hasta(self, dia):
        if not dia:
            return ''
        return str(max((dia - today_lima()).days, 0))

    def _variables(self):
        """Los valores de {nombre}, {documento}… para este envío, en crudo.

        Se escapan al ponerlos en el cuerpo (_pintar); el asunto viaja como
        texto y los lleva tal cual.
        """
        self.ensure_one()
        codigo = self.caso_id.codigo
        item = self.item_id.sudo()
        proceso = self.proceso_id.sudo()
        nombre = (self.partner_id.name or '').strip()
        valores = {
            'nombre': nombre.title() if nombre.isupper() else nombre,
            'proyecto': proceso.name or '',
            'referencia': proceso.referencia or '',
            'plantilla': proceso.checklist_id.name or '',
            'documento': item.name or '',
            'carpeta': item.carpeta_id.ruta or item.carpeta_id.name or '',
            'proveedor': proceso.proveedor_id.name or '',
            'cliente': proceso.cliente_id.name or '',
            'vence': '',
            'dias': '',
            'observacion': '',
            'total': '',
            'contacto': self._contacto(),
            'solicitante': '',
            'codigo': '',
        }
        if self.eliminacion_id:
            elim = self.eliminacion_id.sudo()
            valores.update({
                'proyecto': elim.proyecto or '',
                'referencia': elim.referencia or '',
                'proveedor': elim.proveedor or '',
                'cliente': elim.cliente or '',
                'solicitante': elim.solicitante_id.name or '',
                'vence': fmt_lima(elim.vence, '%H:%M'),
                # Solo existe mientras se manda: no se guarda en ningún sitio.
                'codigo': self.env.context.get('fyle_codigo') or '',
            })
        if item and codigo in ('publicado', 'turno_devuelto', 'revision_por_vencer'):
            valores['vence'] = item._limite_revision_lima()
            if item.fecha_limite_revision:
                valores['dias'] = self._dias_hasta(fields.Date.to_date(
                    fmt_lima(item.fecha_limite_revision, '%Y-%m-%d')))
        if item and codigo in ('observado', 'correccion_por_vencer'):
            valores['vence'] = item._limite_correccion_lima()
            if item.fecha_limite_correccion:
                valores['dias'] = self._dias_hasta(fields.Date.to_date(
                    fmt_lima(item.fecha_limite_correccion, '%Y-%m-%d')))
            comentario = item.comment_ids.filtered(lambda c: c.rol == 'cliente')[-1:]
            valores['observacion'] = comentario.body or ''
        if codigo in ('plazo_por_vencer', 'pendientes_revision'):
            valores['vence'] = _fecha(proceso.fecha_limite)
            valores['dias'] = self._dias_hasta(proceso.fecha_limite)
        if codigo == 'pendientes_revision':
            valores['total'] = str(len(self._pendientes(proceso)))
        if codigo == 'difusion':
            valores['total'] = str(len(self.difusion_id.item_ids))
        return {k: str(v or '') for k, v in valores.items()}

    @api.model
    def _pendientes(self, proceso):
        return proceso.item_ids.filtered(
            lambda i: i.state == 'publicado' and i.fecha_limite_revision
        ).sorted('fecha_limite_revision')

    def _datos(self):
        """Ficha del correo: los datos que lo ubican (proyecto, documento…).

        No es editable a propósito: es lo que permite que todas las
        plantillas se lean igual sin depender de que quien edita el texto se
        acuerde de nombrar el proyecto.
        """
        self.ensure_one()
        v = self._variables()
        codigo = self.caso_id.codigo
        filas = [('Proyecto', v['proyecto'] + (' · %s' % v['referencia'] if v['referencia'] else ''))]
        if v['documento']:
            filas.append(('Documento', v['documento']))
            if v['carpeta']:
                filas.append(('Carpeta', v['carpeta']))
        if codigo == 'eliminacion':
            elim = self.eliminacion_id.sudo()
            filas += [('Proveedor', v['proveedor']), ('Cliente', v['cliente']),
                      ('Estado', elim.estado_proyecto or ''),
                      ('Solicitado por', '%s (%s)' % (v['solicitante'], elim.solicitante_id.login)),
                      ('Código válido hasta', v['vence'])]
            return [f for f in filas if f[1]]
        if codigo in ('publicado', 'turno_devuelto', 'revision_por_vencer',
                      'pendientes_revision', 'difusion'):
            filas.append(('Proveedor', v['proveedor']))
        else:
            filas.append(('Cliente', v['cliente']))
        etiquetas = {
            'publicado': 'Revisar antes del',
            'turno_devuelto': 'Nuevo plazo',
            'revision_por_vencer': 'Vence el',
            'observado': 'Corregir antes del',
            'correccion_por_vencer': 'Corregir antes del',
            'plazo_por_vencer': 'Fin del plazo',
        }
        if v['vence'] and codigo in etiquetas:
            filas.append((etiquetas[codigo], v['vence']))
        return [f for f in filas if f[1]]

    def _lista(self):
        """Tabla de documentos de los casos que la llevan."""
        self.ensure_one()
        lista = self.caso_id.lista
        if lista == 'pendientes':
            return [{
                'nombre': it.name,
                'detalle': it.carpeta_id.ruta or it.carpeta_id.name or '',
                'dato': it._limite_revision_lima(),
            } for it in self._pendientes(self.proceso_id.sudo())]
        if lista == 'difusion':
            return [{
                'nombre': it.name,
                'detalle': it.carpeta_id.ruta or it.carpeta_id.name or '',
                'dato': '',
            } for it in self.difusion_id.sudo().item_ids]
        return []

    def _cita(self):
        self.ensure_one()
        if self.caso_id.cita == 'observacion':
            return self._variables()['observacion']
        if self.caso_id.cita == 'mensaje':
            return self.difusion_id.sudo().mensaje or ''
        return ''

    def _vigente(self):
        """¿Sigue teniendo sentido mandarlo? (ok, motivo).

        Entre encolar y procesar pueden pasar minutos, y en la recuperación,
        días: el documento puede haberse revisado, el proyecto cerrado. Mejor
        no mandar que mandar algo falso.
        """
        self.ensure_one()
        codigo = self.caso_id.codigo
        item = self.item_id.sudo()
        proceso = self.proceso_id.sudo()
        if codigo == 'difusion':
            return (True, '') if self.difusion_id else (False, 'La difusión ya no existe.')
        if codigo == 'eliminacion':
            # El código solo existe en el momento de pedirlo: un reintento
            # posterior no tendría qué mandar.
            if not self.env.context.get('fyle_codigo'):
                return False, 'El código solo se manda al pedirlo: hay que pedir uno nuevo.'
            if not self.eliminacion_id.sudo().vigente():
                return False, 'La solicitud de eliminación ya no está vigente.'
            return True, ''
        if not proceso:
            return False, 'El proyecto ya no existe.'
        if codigo != 'aprobado' and proceso.state not in ('publicacion', 'revision'):
            return False, 'El proyecto ya no está en curso.'
        ahora = fields.Datetime.now()
        if codigo in ('publicado', 'turno_devuelto', 'revision_por_vencer'):
            if not item or item.state != 'publicado':
                return False, 'El documento ya no está esperando revisión.'
            if codigo == 'revision_por_vencer' and (
                    not item.fecha_limite_revision or item.fecha_limite_revision <= ahora):
                return False, 'La revisión ya venció.'
        if codigo == 'aprobado' and (not item or item.state != 'aprobado'):
            return False, 'El documento ya no figura como aprobado.'
        if codigo in ('observado', 'correccion_por_vencer'):
            if not item or item.state != 'observado':
                return False, 'El documento ya se corrigió.'
            if codigo == 'correccion_por_vencer' and (
                    not item.fecha_limite_correccion or item.fecha_limite_correccion <= ahora):
                return False, 'El plazo de corrección ya venció.'
        if codigo == 'pendientes_revision' and not self._pendientes(proceso):
            return False, 'Ya no queda nada por revisar.'
        if codigo == 'plazo_por_vencer' and (
                not proceso.fecha_limite or proceso.fecha_limite < today_lima()):
            return False, 'El plazo del proyecto ya venció.'
        return True, ''

    # ═══ Pintar ══════════════════════════════════════════════════════════
    @api.model
    def _parrafos(self, texto, variables):
        """Texto plano del caso -> párrafos HTML con las variables puestas.

        El texto se escapa ANTES de poner las variables, y las variables ya
        llegan escapadas: ni quien edita la plantilla ni el nombre de un
        documento pueden meter HTML en el correo.
        """
        parrafos = []
        for bloque in (texto or '').replace('\r\n', '\n').split('\n\n'):
            bloque = bloque.strip()
            if not bloque:
                continue
            seguro = str(escape(bloque)).format_map(variables)
            parrafos.append(Markup(seguro.replace('\n', '<br/>')))
        return parrafos

    @api.model
    def _pintar(self, caso, variables, boton_url, datos=None, lista=None, cita='', codigo=''):
        """(asunto, cuerpo HTML). `variables` llega en crudo."""
        asunto = ' '.join(str(caso.asunto or '').format_map(_Variables(variables)).split())
        escapadas = _Variables({k: str(escape(v)) for k, v in variables.items()})
        cuerpo = self.env['ir.qweb']._render('certum_revision.correo_layout', {
            'titulo': asunto,
            'parrafos': self._parrafos(caso.texto, escapadas),
            'datos': datos or [],
            'lista': lista or [],
            'lista_dato': 'Hasta' if caso.lista == 'pendientes' else '',
            'cita': cita or '',
            'cita_titulo': ('Observación del cliente' if caso.cita == 'observacion'
                            else 'Mensaje'),
            'codigo': codigo or '',
            'boton': caso.boton,
            'boton_url': boton_url,
            'contacto': self._contacto(),
            'base_url': self._url(''),
            'anio': today_lima().year,
        }, minimal_qcontext=True)
        return asunto, cuerpo

    def _pintar_envio(self):
        self.ensure_one()
        variables = self._variables()
        return self._pintar(self.caso_id, variables, self._boton_url(),
                            datos=self._datos(), lista=self._lista(), cita=self._cita(),
                            codigo=variables['codigo'])

    # ═══ Procesar la cola ════════════════════════════════════════════════
    def _procesar(self, forzar_envio=False):
        """Pendiente -> mail.mail en la cola de Odoo. Uno a uno, cada uno en
        su savepoint: un fallo deja ESE envío como fallido y sigue."""
        remitente = self._remitente()
        servidor = self._servidor()
        contacto = self._contacto()
        hechos = self.browse()
        for envio in self.sudo():
            if envio.estado not in ('pendiente', 'fallido'):
                continue
            if not envio.caso_id.activo and envio.origen == 'automatico':
                envio.write({'estado': 'cancelado', 'motivo': 'La plantilla está desactivada.'})
                continue
            ok, motivo = envio._vigente()
            if not ok:
                envio.write({'estado': 'cancelado', 'motivo': motivo})
                continue
            email = envio.email or envio.partner_id.email
            if not email:
                envio.write({'estado': 'cancelado', 'motivo': 'La persona no tiene correo registrado.'})
                continue
            try:
                with self.env.cr.savepoint():
                    asunto, cuerpo = envio._pintar_envio()
                    mail = self.env['mail.mail'].sudo().create({
                        'subject': asunto,
                        'body_html': cuerpo,
                        'email_from': remitente,
                        'email_to': formataddr((envio.partner_id.name or '', email)),
                        'email_cc': envio.email_cc or False,
                        'reply_to': contacto,
                        'mail_server_id': servidor.id or False,
                        'auto_delete': False,
                    })
                    envio.write({
                        'estado': 'en_cola', 'mail_id': mail.id, 'asunto': asunto,
                        'email': email, 'motivo': False, 'intentos': envio.intentos + 1,
                    })
                    hechos |= envio
            except Exception as exc:  # noqa: BLE001
                _logger.exception('Correo %s: no se pudo preparar', envio.id)
                envio.write({'estado': 'fallido', 'intentos': envio.intentos + 1,
                             'motivo': ('No se pudo preparar: %s' % exc)[:250]})
        if forzar_envio and hechos.mail_id:
            hechos.mail_id.send(raise_exception=False)
        hechos._sincronizar()
        return hechos

    def _sincronizar(self):
        """Estado del mail.mail -> estado del envío."""
        for envio in self.sudo().filtered(lambda e: e.estado == 'en_cola'):
            mail = envio.mail_id
            if not mail:
                # auto_delete va en False: si no está, lo borró alguien a mano.
                envio.write({'estado': 'enviado'})
                continue
            estado = _ESTADO_MAIL.get(mail.state, 'en_cola')
            if estado == envio.estado:
                continue
            valores = {'estado': estado}
            if estado == 'enviado':
                valores['fecha_envio'] = mail.write_date
            if estado == 'fallido':
                valores['motivo'] = (mail.failure_reason or 'El servidor de correo lo rechazó.')[:250]
            envio.write(valores)

    @api.model
    def _cron_enviar(self):
        """Prepara lo pendiente y lo manda ya, sin esperar a la cola general
        de Odoo (en producción corre una vez por hora: el aviso de un
        documento publicado llegaría tarde). Lo que el servidor rechace queda
        como fallido y se reintenta desde Recuperación."""
        self.search([('estado', '=', 'en_cola')], limit=1000)._sincronizar()
        if self._pausado():
            return
        pendientes = self.search([('estado', '=', 'pendiente')], order='id', limit=100)
        pendientes._procesar(forzar_envio=True)

    # ═══ El cron diario: lo que toca por fecha ═══════════════════════════
    @api.model
    def _cron_diario(self):
        if self._pausado():
            return
        for candidato in self._candidatos():
            self.encolar(candidato['codigo'], candidato['registro'], candidato['partner'],
                         candidato.get('referencia', ''))

    @api.model
    def _candidatos(self):
        """Todo lo que, por las reglas, ya tendría que estar en la cola y no
        está. Lo usa el cron diario para encolarlo y la pestaña Recuperación
        para enseñarlo sin encolar.

        Incluye los avisos de una acción (publicado, aprobado, observado,
        difusión) por si el disparador no llegó: su clave es la misma que la
        del disparador, así que nunca salen dos veces.
        """
        Caso = self.env['certum.rev.correo.caso'].sudo()
        activos = {c.codigo: c for c in Caso.search([('activo', '=', True)])}
        candidatos = []
        for codigo, buscar in (
                ('publicado', self._candidatos_publicado),
                ('aprobado', self._candidatos_aprobado),
                ('observado', self._candidatos_observado),
                ('difusion', self._candidatos_difusion),
                ('pendientes_revision', self._candidatos_pendientes),
                ('revision_por_vencer', self._candidatos_revision_vence),
                ('correccion_por_vencer', self._candidatos_correccion_vence),
                ('plazo_por_vencer', self._candidatos_plazo_vence)):
            if codigo not in activos:
                continue
            for registro, referencia in buscar(activos[codigo]):
                for partner in self._destinatarios(codigo, registro):
                    candidatos.append({
                        'codigo': codigo,
                        'caso': activos[codigo],
                        'registro': registro,
                        'partner': partner,
                        'referencia': referencia,
                        'clave': self._clave(codigo, partner, registro, referencia),
                    })
        if not candidatos:
            return []
        ya = set(self.sudo().search([('clave', 'in', [c['clave'] for c in candidatos])]).mapped('clave'))
        return [c for c in candidatos if c['clave'] not in ya]

    @api.model
    def _items_en_curso(self, dominio):
        return self.env['certum.rev.item'].sudo().search(dominio + [
            ('proceso_id.state', 'in', ('publicacion', 'revision'))])

    # Referencias: las MISMAS que usan los disparadores de models/notify.py.
    @api.model
    def ref_publicado(self, item):
        return 'att-%s-p%s' % (item.attachment_final_id.id or 0, item.revision_paso or 0)

    @api.model
    def ref_observado(self, item):
        return 'obs-%s' % (item.fecha_revision or '')

    @api.model
    def ref_aprobado(self, item):
        return 'att-%s' % (item.attachment_final_id.id or 0)

    @api.model
    def _candidatos_publicado(self, caso):
        """Documentos esperando revisión cuyo revisor de turno no recibió su
        aviso: el disparador falló, o la cadena pasó al siguiente revisor."""
        items = self._items_en_curso([('state', '=', 'publicado'),
                                      ('fecha_publicacion', '>=', self._desde())])
        return [(it, self.ref_publicado(it)) for it in items]

    @api.model
    def _candidatos_aprobado(self, caso):
        items = self.env['certum.rev.item'].sudo().search([
            ('state', '=', 'aprobado'), ('fecha_revision', '>=', self._desde())])
        return [(it, self.ref_aprobado(it)) for it in items]

    @api.model
    def _candidatos_observado(self, caso):
        items = self._items_en_curso([('state', '=', 'observado'),
                                      ('fecha_revision', '>=', self._desde())])
        return [(it, self.ref_observado(it)) for it in items]

    @api.model
    def _candidatos_difusion(self, caso):
        difusiones = self.env['certum.rev.difusion'].sudo().search([
            ('fecha', '>=', self._desde())])
        return [(d, '') for d in difusiones]

    @api.model
    def _candidatos_pendientes(self, caso):
        """Un resumen al día por proyecto con lo que sigue esperando. La
        referencia lleva la fecha: uno al día, aunque el cron corra dos veces;
        y si no hay nada pendiente, ningún correo."""
        hoy = today_lima().isoformat()
        procesos = self.env['certum.rev.proceso'].sudo().search([('state', '=', 'revision')])
        return [(p, 'dia-%s' % hoy) for p in procesos if self._pendientes(p)]

    @api.model
    def _candidatos_revision_vence(self, caso):
        """Vence la ventana de revisión dentro de `dias` días: si vence, el
        documento se aprueba SOLO, así que es el aviso que más importa."""
        ahora = fields.Datetime.now()
        items = self._items_en_curso([
            ('state', '=', 'publicado'),
            ('fecha_limite_revision', '>', ahora),
            ('fecha_limite_revision', '<=', ahora + timedelta(days=max(caso.dias or 2, 1)))])
        return [(it, 'lim-%s' % it.fecha_limite_revision) for it in items]

    @api.model
    def _candidatos_correccion_vence(self, caso):
        ahora = fields.Datetime.now()
        items = self._items_en_curso([
            ('state', '=', 'observado'),
            ('fecha_limite_correccion', '>', ahora),
            ('fecha_limite_correccion', '<=', ahora + timedelta(days=max(caso.dias or 2, 1)))])
        return [(it, 'corr-%s' % it.fecha_limite_correccion) for it in items]

    @api.model
    def _candidatos_plazo_vence(self, caso):
        """El plazo general del proyecto vence dentro de `dias` días y aún
        queda algo sin aprobar."""
        hoy = today_lima()
        tope = hoy + timedelta(days=max(caso.dias or 5, 1))
        salida = []
        for p in self.env['certum.rev.proceso'].sudo().search(
                [('state', 'in', ('publicacion', 'revision'))]):
            if p.fecha_limite and hoy <= p.fecha_limite <= tope and \
                    p.item_ids.filtered(lambda i: i.state != 'aprobado'):
                salida.append((p, 'fin-%s' % p.fecha_limite))
        return salida

    # ═══ Vista previa y prueba ═══════════════════════════════════════════
    @api.model
    def _muestra(self, caso, partner):
        """Variables, ficha, lista y cita de muestra para la vista previa."""
        hoy = today_lima()
        vence = _fecha(hoy + timedelta(days=caso.dias or 3))
        variables = {
            'nombre': partner.name or 'María Pérez',
            'proyecto': 'REV/2026/0007',
            'referencia': 'Sede Callao',
            'plantilla': 'Homologación de contratistas',
            'documento': 'Plan de Seguridad y Salud en el Trabajo',
            'carpeta': 'SST / Planes',
            'proveedor': 'Contratista Ejemplo SAC',
            'cliente': 'Cliente Ejemplo SA',
            'vence': vence,
            'dias': str(caso.dias or 3),
            'observacion': 'Falta la firma del gerente general en la última página.',
            'total': '3',
            'contacto': self._contacto(),
            'solicitante': self.env.user.name or 'Ana Torres',
            'codigo': '482913',
        }
        if caso.codigo == 'eliminacion':
            variables['vence'] = fmt_lima(fields.Datetime.now() + timedelta(minutes=15), '%H:%M')
            datos = [('Proyecto', 'REV/2026/0007 · Sede Callao'),
                     ('Proveedor', variables['proveedor']), ('Cliente', variables['cliente']),
                     ('Estado', 'Revisión'),
                     ('Solicitado por', variables['solicitante']),
                     ('Código válido hasta', variables['vence'])]
            return variables, datos, [], ''
        # La otra parte, como en _datos(): al proveedor se le nombra al cliente.
        al_proveedor = caso.codigo in ('aprobado', 'observado', 'correccion_por_vencer',
                                       'plazo_por_vencer')
        datos = [('Proyecto', 'REV/2026/0007 · Sede Callao'),
                 ('Documento', variables['documento']),
                 ('Cliente', variables['cliente']) if al_proveedor
                 else ('Proveedor', variables['proveedor'])]
        lista = []
        if caso.lista:
            lista = [{'nombre': n, 'detalle': d, 'dato': vence if caso.lista == 'pendientes' else ''}
                     for n, d in (('Plan de Seguridad y Salud en el Trabajo', 'SST / Planes'),
                                  ('IPERC de la actividad', 'SST / Riesgos'),
                                  ('Póliza SCTR vigente', 'Seguros'))]
            datos = [datos[0], datos[2]]
        cita = ''
        if caso.cita == 'observacion':
            cita = variables['observacion']
        elif caso.cita == 'mensaje':
            cita = 'Les compartimos la documentación aprobada para su archivo.'
        return variables, datos, lista, cita

    @api.model
    def _vista_previa(self, caso, partner):
        variables, datos, lista, cita = self._muestra(caso, partner)
        boton_url = self._url('/my/repositorio' if caso.codigo == 'difusion' else '/my/certum')
        return self._pintar(caso, variables, boton_url, datos=datos, lista=lista, cita=cita,
                            codigo=variables['codigo'] if caso.codigo == 'eliminacion' else '')

    @api.model
    def _enviar_prueba(self, caso, email, partner):
        """Correo de prueba con datos de muestra. Queda en el historial."""
        asunto, cuerpo = self._vista_previa(caso, partner)
        asunto = '[Prueba] %s' % asunto
        envio = self.sudo().create({
            'caso_id': caso.id,
            'partner_id': partner.id,
            'email': email,
            'clave': 'prueba:%s:%s' % (caso.codigo, fields.Datetime.now().timestamp()),
            'origen': 'prueba',
            'asunto': asunto,
        })
        mail = self.env['mail.mail'].sudo().create({
            'subject': asunto,
            'body_html': cuerpo,
            'email_from': self._remitente(),
            'email_to': email,
            'reply_to': self._contacto(),
            'mail_server_id': self._servidor().id or False,
            'auto_delete': False,
        })
        envio.write({'estado': 'en_cola', 'mail_id': mail.id, 'intentos': 1})
        mail.send(raise_exception=False)
        envio._sincronizar()
        return envio
