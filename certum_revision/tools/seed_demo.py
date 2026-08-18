# -*- coding: utf-8 -*-
"""Datos de demostración de certum_revision — para QA del flujo completo.

POR QUÉ UN SCRIPT Y NO `data/demo.xml`
--------------------------------------
Un `demo.xml` declarado en la clave `'demo'` del manifest SOLO se carga en bases
creadas CON datos de demostración. `certum-global-sac` es una base de producción
(creada sin demo), así que ahí nunca se cargaría. Este script funciona sobre
cualquier base, es idempotente (se puede correr varias veces sin duplicar) y se
puede revertir.

USO (en el servidor)
--------------------
    /cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin shell \
        -d certum-global-sac --no-http < tools_seed_demo.py

Para BORRAR todo lo que crea (deja la base como estaba):
    CERTUM_DEMO_PURGE=1 /cloudclusters/odoo/venv/bin/python3 \
        /cloudclusters/odoo/odoo-bin shell -d certum-global-sac --no-http \
        < tools_seed_demo.py

Todo lo que crea lleva el prefijo "[DEMO]" en el nombre, así que es
identificable y borrable sin tocar datos reales.
"""
import os

# ── Configuración ────────────────────────────────────────────────────────
TAG = '[DEMO]'
# Contraseña SOLO para los usuarios de prueba de esta demo. Cambiala aqui antes
# de correr el script si la demo va a quedar en un entorno accesible.
DEMO_PASSWORD = 'CertumDemo2026!'
PURGE = os.environ.get('CERTUM_DEMO_PURGE') == '1'

PROVEEDOR_NAME = TAG + ' Constructora Andina S.A.C.'
CLIENTE_NAME = TAG + ' Minera Cerro Verde S.A.A.'
CHECKLIST_NAME = TAG + ' Homologacion SSOMA 2026'

# (nombre, email, nivel, crear_usuario_portal)
PERSONAL_PROVEEDOR = [
    ('Ana Quispe Flores', 'demo.proveedor.n1@certumglobal.pe', 1, True),
    ('Luis Ramos Chavez', 'demo.proveedor.n2@certumglobal.pe', 2, True),
]
PERSONAL_CLIENTE = [
    ('Rosa Del Aguila Vega', 'demo.cliente.n1@certumglobal.pe', 1, True),
    ('Carlos Mendoza Rios', 'demo.cliente.n2@certumglobal.pe', 2, True),
    ('Jorge Salas Paredes', 'demo.cliente.n3@certumglobal.pe', 3, True),
]

# (carpeta, secuencia, [(item, obligatorio, descripcion)])
ESTRUCTURA = [
    ('1. Legal y laboral', 10, [
        ('Constancia de inscripcion en RNP', True,
         'Vigente a la fecha de presentacion. PDF descargado de SUNAT/OSCE.'),
        ('Planilla electronica (T-Registro) del ultimo mes', True,
         'Debe incluir a todo el personal que ingresara a operaciones.'),
        ('Contratos de trabajo del personal asignado', False,
         'Opcional en esta etapa; se exigira antes del ingreso a mina.'),
    ]),
    ('2. Seguridad y salud en el trabajo', 20, [
        ('Politica de SST firmada por la alta direccion', True,
         'Firmada y fechada dentro de los ultimos 12 meses.'),
        ('IPERC de linea base', True,
         'Matriz IPERC por puesto de trabajo, con controles y riesgo residual.'),
        ('SCTR salud y pension vigente', True,
         'Constancia de la aseguradora con relacion nominal del personal.'),
        ('Examenes medicos ocupacionales (EMO)', True,
         'Aptitud medica vigente de cada trabajador asignado.'),
        ('Programa anual de capacitaciones SST', True,
         'Cronograma con temas, horas y responsables.'),
    ]),
    ('3. Medio ambiente', 30, [
        ('Plan de manejo de residuos solidos', True,
         'Incluye segregacion, almacenamiento temporal y EO-RS contratada.'),
        ('Certificado de la EO-RS contratada', False,
         'Registro vigente ante MINAM.'),
    ]),
]


# ── Utilidades ───────────────────────────────────────────────────────────
def _log(msg):
    print('[seed] ' + msg)


def _purge(env):
    """Elimina todo lo marcado con TAG. Orden: procesos, plantillas, usuarios, partners."""
    Partner = env['res.partner'].sudo()
    # Solo las COMPANIAS llevan el prefijo; los contactos-persona son hijos y
    # hay que arrastrarlos explicitamente o quedarian huerfanos.
    empresas = Partner.search([('name', 'like', TAG), ('is_company', '=', True)])
    partners = empresas | empresas.mapped('child_ids')

    procesos = env['certum.rev.proceso'].sudo().search([
        '|', ('proveedor_id', 'in', empresas.ids), ('cliente_id', 'in', empresas.ids)])
    n_proc = len(procesos)
    procesos.unlink()          # cascada: carpetas, items, comentarios, trazas

    checklists = env['certum.rev.checklist'].sudo().search([('name', 'like', TAG)])
    n_ch = len(checklists)
    checklists.unlink()        # cascada: carpetas e items maestros

    users = env['res.users'].sudo().search([('partner_id', 'in', partners.ids)])
    n_us = len(users)
    users.unlink()

    n_pa = len(partners)
    partners.unlink()

    _log('purga: %s procesos, %s plantillas, %s usuarios, %s contactos'
         % (n_proc, n_ch, n_us, n_pa))


def _empresa(env, name, rol, email):
    """Compania idempotente con su rol Certum."""
    Partner = env['res.partner'].sudo()
    # '=ilike' y no '=': esta instalación normaliza los nombres de contacto a
    # MAYÚSCULAS al guardarlos, y con igualdad exacta el script no reencontraba
    # lo ya creado y duplicaba las empresas en cada ejecución.
    rec = Partner.search([('name', '=ilike', name), ('is_company', '=', True)], limit=1)
    vals = {'name': name, 'is_company': True, 'rol_en_certum': rol, 'email': email}
    peru = env.ref('base.pe', raise_if_not_found=False)
    if peru:
        vals['country_id'] = peru.id
    if rec:
        rec.write(vals)
    else:
        rec = Partner.create(vals)
        _log('empresa creada: %s (%s)' % (name, rol))
    return rec


def _persona(env, empresa, name, email, nivel, con_usuario):
    """Contacto-persona con nivel jerarquico + usuario portal opcional."""
    Partner = env['res.partner'].sudo()
    rec = Partner.search([('name', '=ilike', name), ('parent_id', '=', empresa.id)], limit=1)
    vals = {'name': name, 'parent_id': empresa.id, 'is_company': False,
            'email': email, 'certum_nivel': nivel, 'function': 'Nivel %s' % nivel}
    if rec:
        rec.write(vals)
    else:
        rec = Partner.create(vals)
    if not con_usuario:
        return rec

    Users = env['res.users'].sudo().with_context(no_reset_password=True)
    user = Users.search([('login', '=', email)], limit=1)
    if not user:
        Users.create({
            'name': name,
            'login': email,
            'password': DEMO_PASSWORD,
            'partner_id': rec.id,
            'groups_id': [(6, 0, [env.ref('base.group_portal').id])],
        })
        _log('usuario portal creado: %s (nivel %s)' % (email, nivel))
    return rec


def _checklist(env, proveedor):
    """Plantilla del proveedor con carpetas e items. Idempotente."""
    Checklist = env['certum.rev.checklist'].sudo()
    ch = Checklist.search([('name', '=ilike', CHECKLIST_NAME)], limit=1)
    if ch:
        _log('plantilla ya existia: %s (%s)' % (ch.name, ch.code))
        return ch

    ch = Checklist.create({
        'name': CHECKLIST_NAME,
        'proveedor_id': proveedor.id,
        'sector': 'Mineria / contratistas',
        'plazo_dias': 30,
        'description': 'Plantilla de demostracion para probar el flujo completo '
                       'de publicacion, revision por niveles y aprobacion.',
    })
    Folder = env['certum.rev.checklist.folder'].sudo()
    Item = env['certum.rev.checklist.item'].sudo()
    for fname, fseq, items in ESTRUCTURA:
        folder = Folder.create({'checklist_id': ch.id, 'name': fname,
                                'sequence': fseq})
        for i, (iname, req, desc) in enumerate(items, start=1):
            Item.create({
                'checklist_id': ch.id,
                'folder_id': folder.id,
                'name': iname,
                'description': desc,
                'required': req,
                'sequence': fseq + i,
            })
    _log('plantilla creada: %s (%s) - %s carpetas, %s items'
         % (ch.name, ch.code, ch.folder_count, ch.item_count))
    return ch


def _proceso(env, proveedor, cliente, checklist):
    """Proceso abierto (state=publicacion) con los items ya copiados."""
    from odoo.addons.certum_revision.models.tz_utils import today_lima

    Proceso = env['certum.rev.proceso'].sudo()
    proc = Proceso.search([
        ('proveedor_id', '=', proveedor.id),
        ('checklist_id', '=', checklist.id)], limit=1)
    if proc:
        _log('proceso ya existia: %s (%s)' % (proc.name, proc.state))
        return proc

    proc = Proceso.create({
        'proveedor_id': proveedor.id,
        'cliente_id': cliente.id,
        'checklist_id': checklist.id,
        'fecha_inicio': today_lima(),
        'plazo_dias': 30,
    })
    proc.action_abrir()
    _log('proceso creado y abierto: %s - %s items, limite %s'
         % (proc.name, proc.total_items, proc.fecha_limite))
    return proc


def seed(env):
    if PURGE:
        _purge(env)
        return

    proveedor = _empresa(env, PROVEEDOR_NAME, 'proveedor',
                         'demo.proveedor@certumglobal.pe')
    cliente = _empresa(env, CLIENTE_NAME, 'cliente',
                       'demo.cliente@certumglobal.pe')

    for name, email, nivel, con_user in PERSONAL_PROVEEDOR:
        _persona(env, proveedor, name, email, nivel, con_user)
    for name, email, nivel, con_user in PERSONAL_CLIENTE:
        _persona(env, cliente, name, email, nivel, con_user)

    # El proveedor solo puede elegir a los clientes que Certum le asigna.
    proveedor.write({'certum_cliente_ids': [(6, 0, [cliente.id])]})

    checklist = _checklist(env, proveedor)
    proc = _proceso(env, proveedor, cliente, checklist)

    # La politica de revision (secuencial / capas) se deja SIN configurar a
    # proposito: fijarla es el paso 2 del guion de QA y la debe fijar el
    # nivel 1 del cliente desde el portal.
    print('')
    print('=' * 68)
    print('  DEMO LISTA - %s' % proc.name)
    print('=' * 68)
    print('  Proveedor : %s' % proveedor.name)
    print('  Cliente   : %s' % cliente.name)
    print('  Plantilla : %s (%s items)' % (checklist.code, checklist.item_count))
    print('  Plazo     : %s -> %s' % (proc.fecha_inicio, proc.fecha_limite))
    print('')
    print('  Usuarios portal (contrasena: %s)' % DEMO_PASSWORD)
    for name, email, nivel, con_user in PERSONAL_PROVEEDOR + PERSONAL_CLIENTE:
        if con_user:
            print('    nivel %s  %-38s %s' % (nivel, email, name))
    print('')
    print('  Entrar por  /my/certum')
    print('  Proveedor -> /my/procesos    |    Cliente -> /my/revisiones')
    print('=' * 68)


# `env` lo inyecta `odoo-bin shell`.
if 'env' in globals():
    seed(env)            # noqa: F821
    env.cr.commit()      # noqa: F821
    print('[seed] cambios COMMITEADOS.')
else:
    print(__doc__)
