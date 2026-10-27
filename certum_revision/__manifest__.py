# -*- coding: utf-8 -*-
{
    'name': 'FYLE 360 — Revisión documental',
    'version': '18.0.2.1.0',
    'category': 'Website/Portal',
    'summary': 'Publicación de documentos por el proveedor y revisión/aprobación por el cliente, con plazos, correos y trazabilidad.',
    'description': """
FYLE 360 — Revisión documental (Certum Global)
==============================================
- Plantillas de requisitos (carpetas + ítems) reutilizables por proveedor.
- Proyectos proveedor ↔ cliente con plazos derivados de la fecha de inicio.
- Portal proveedor: publicación y corrección de documentos.
- Portal cliente: revisión (aprobado/observado), cadenas de revisores y
  ampliaciones de plazo.
- Correos propios: plantillas activables, cola con historial, recuperación
  manual, remitente elegido entre los servidores de Odoo y copias por cliente.
- Panel de administración web propio: sin menús ni vistas en el backend.
- Roles por proyecto: cada lado usa los generales o una lista propia; quien
  queda fuera no ve el proyecto ni recibe sus correos.
- Eliminación de proyectos con código de confirmación enviado a todo el
  personal interno.
Modelos 100 % en código (sin Studio). Nombre técnico: certum_revision.
""",
    'author': 'Certum Global',
    'license': 'LGPL-3',
    'depends': ['base', 'portal', 'website', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/config_params.xml',
        'data/cron.xml',
        'views/correo_layout.xml',
        'data/correo_data.xml',
        'views/portal_common.xml',
        'views/hub/portal_home.xml',
        'views/proveedor/portal_proceso.xml',
        'views/cliente/portal_revision.xml',
        'views/admin/layout.xml',
        'views/admin/resumen.xml',
        'views/admin/proyecto.xml',
        'views/admin/panel.xml',
        'views/admin/correos.xml',
        'views/admin/ajustes.xml',
        'views/plantillas/builder.xml',
        'views/repositorio.xml',
        'views/landing.xml',
        'data/portal_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'certum_revision/static/src/css/portal_base.css',
            'certum_revision/static/src/css/hub/home.css',
            'certum_revision/static/src/css/proveedor/proceso.css',
            'certum_revision/static/src/css/cliente/revision.css',
            'certum_revision/static/src/css/admin/panel.css',
            'certum_revision/static/src/css/admin/admin.css',
            'certum_revision/static/src/css/plantillas/builder.css',
            'certum_revision/static/src/css/proceso/gestion.css',
            'certum_revision/static/src/css/repositorio.css',
            'certum_revision/static/src/js/portal_base.js',
            'certum_revision/static/src/js/admin/panel.js',
            'certum_revision/static/src/js/admin/admin.js',
            'certum_revision/static/src/js/plantillas/builder.js',
            'certum_revision/static/src/js/proceso/gestion.js',
            'certum_revision/static/src/js/proceso/estructura.js',
            'certum_revision/static/src/js/proceso/difusion.js',
        ],
    },
    'application': True,
    'installable': True,
}
