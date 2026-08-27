# -*- coding: utf-8 -*-
"""Configuración de los avisos por correo y catálogo de eventos.

Dos piezas:

  - **EVENTOS**: el catálogo. Cada aviso del sistema está aquí con su código,
    su nombre y a quién va. El panel de administración se pinta leyendo esta
    lista, así que añadir un aviso nuevo es añadir una entrada y una plantilla,
    no tocar la interfaz.
  - **`certum.rev.aviso.config`**: el AbstractModel que responde «¿está activo
    este aviso?», «¿desde qué dirección se envía?» y «¿por qué servidor?».

Todo se guarda en `ir.config_parameter`, no en un modelo propio: son ajustes
de instalación, uno por base de datos, y así se leen igual desde un cron que
desde el portal sin arrastrar un registro singleton.

**Nota sobre el servidor saliente:** aquí se ELIGE un `ir.mail_server` ya
creado en el backend de Odoo; no se editan host, usuario ni contraseña desde
el portal. Exponer credenciales SMTP en una pantalla web es superficie de
ataque que no compensa: crear el servidor es una tarea de una sola vez.
"""
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

PREFIJO = 'certum_revision.aviso_'
EMAIL_RE = re.compile(r'^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$')

# Catálogo de avisos. `auto` marca los que dispara el sistema solo; los que no
# lo son se lanzan desde una acción de una persona y no se pueden desactivar
# sin romper esa acción.
EVENTOS = [
    {'code': 'publicado', 'nombre': 'Documento publicado',
     'para': 'Al cliente', 'auto': True,
     'ayuda': 'El proveedor sube un documento y el cliente debe revisarlo.'},
    {'code': 'aprobado', 'nombre': 'Documento aprobado',
     'para': 'Al proveedor', 'auto': True,
     'ayuda': 'El cliente aceptó el documento.'},
    {'code': 'observado', 'nombre': 'Documento observado',
     'para': 'Al proveedor', 'auto': True,
     'ayuda': 'El cliente lo devolvió, con el texto de la observación.'},
    {'code': 'turno_devuelto', 'nombre': 'Turno de revisión devuelto',
     'para': 'Al cliente', 'auto': True,
     'ayuda': 'El proveedor reabrió el turno de un revisor que dejó vencer '
              'su plazo.'},
    {'code': 'pendientes_revision', 'nombre': 'Recordatorio de pendientes',
     'para': 'Al cliente', 'auto': True,
     'ayuda': 'Resumen diario de los documentos que siguen esperando '
              'revisión. Se envía una vez al día y solo si hay algo.'},
    {'code': 'revision_por_vencer', 'nombre': 'Revisión por vencer',
     'para': 'Al cliente', 'auto': True,
     'ayuda': 'Aviso a N días de que venza la ventana de revisión de un '
              'documento, antes de que se apruebe solo.'},
    {'code': 'correccion_por_vencer', 'nombre': 'Corrección por vencer',
     'para': 'Al proveedor', 'auto': True,
     'ayuda': 'Aviso a N días de que venza el plazo para corregir un '
              'documento observado.'},
    {'code': 'plazo_por_vencer', 'nombre': 'Plazo del proyecto por vencer',
     'para': 'A ambas partes', 'auto': True,
     'ayuda': 'Aviso a N días de que venza el plazo general del proyecto.'},
    {'code': 'difusion', 'nombre': 'Difusión de un documento aprobado',
     'para': 'A quien elija el proveedor', 'auto': False,
     'ayuda': 'Envío manual de un documento aprobado a contactos del '
              'cliente, con enlace al repositorio del proyecto.'},
]


class CertumRevAvisoConfig(models.AbstractModel):
    _name = 'certum.rev.aviso.config'
    _description = 'Configuración de los avisos por correo'

    # ── Catálogo ───────────────────────────────────────────────────────
    @api.model
    def eventos(self):
        """El catálogo, con el estado actual de cada aviso."""
        return [dict(e, activo=self.activo(e['code'])) for e in EVENTOS]

    @api.model
    def evento(self, code):
        for e in EVENTOS:
            if e['code'] == code:
                return e
        return None

    # ── Ajustes ────────────────────────────────────────────────────────
    @api.model
    def _icp(self):
        return self.env['ir.config_parameter'].sudo()

    @api.model
    def activo(self, code):
        """¿Está activo este aviso? Y el interruptor general manda sobre todos.

        El interruptor general existe para las pruebas: sin él, ensayar el
        flujo completo en la base de producción llenaría de correos los
        buzones de gente real.
        """
        if self._icp().get_param(PREFIJO + 'enviar', '1') != '1':
            return False
        return self._icp().get_param('%sev_%s' % (PREFIJO, code), '1') == '1'

    @api.model
    def envio_general(self):
        return self._icp().get_param(PREFIJO + 'enviar', '1') == '1'

    @api.model
    def remitente(self):
        """Cabecera `De`. Vacío = lo decide Odoo con la empresa del usuario.

        Aviso práctico: Microsoft 365 rechaza los envíos cuyo remitente no
        coincide con la cuenta autenticada, así que aquí debe ir esa misma
        dirección o los correos rebotarán.
        """
        icp = self._icp()
        correo = (icp.get_param(PREFIJO + 'from_email', '') or '').strip()
        if not correo:
            return ''
        nombre = (icp.get_param(PREFIJO + 'from_name', '') or '').strip()
        return ('%s <%s>' % (nombre, correo)) if nombre else correo

    @api.model
    def mail_server_id(self):
        """Servidor saliente elegido, o 0 para que Odoo escoja el suyo."""
        try:
            sid = int(self._icp().get_param(PREFIJO + 'mail_server_id', 0) or 0)
        except (TypeError, ValueError):
            return 0
        if sid and not self.env['ir.mail_server'].sudo().browse(sid).exists():
            return 0
        return sid

    @api.model
    def copia_global(self):
        """Direcciones en copia en todos los avisos (p. ej. un buzón de
        seguimiento de Certum)."""
        return self.parsear(self._icp().get_param(PREFIJO + 'cc', ''))

    @api.model
    def dias_preaviso(self):
        """Días de antelación de los avisos de «por vencer»."""
        try:
            return max(1, int(self._icp().get_param(PREFIJO + 'dias_preaviso', 2)))
        except (TypeError, ValueError):
            return 2

    # ── Utilidades ─────────────────────────────────────────────────────
    @api.model
    def parsear(self, crudo):
        """Lista de correos válidos a partir de un texto separado por comas,
        puntos y coma o saltos de línea. Los inválidos se descartan en
        silencio: un correo mal escrito no debe impedir que salgan los demás.
        """
        if not crudo:
            return []
        piezas = re.split(r'[,;\s]+', str(crudo))
        vistos, salida = set(), []
        for p in piezas:
            p = p.strip().lower()
            if p and EMAIL_RE.match(p) and p not in vistos:
                vistos.add(p)
                salida.append(p)
        return salida

    @api.model
    def base_url(self):
        return (self._icp().get_param('web.base.url', '') or '').rstrip('/')

    @api.model
    def hay_servidor(self):
        """¿Hay algún servidor saliente configurado en la base?

        Sin `ir.mail_server`, en una instalación autohospedada NINGÚN correo
        sale: se quedan en la cola como fallidos y nadie se entera. El panel
        avisa de esto en grande, porque es el fallo más silencioso del
        sistema.
        """
        return bool(self.env['ir.mail_server'].sudo().search_count([]))
