# -*- coding: utf-8 -*-
{
    'name': 'Certum Global — Flujo de Revisión y Aceptación',
    'version': '18.0.1.0.0',
    'category': 'Website/Portal',
    'summary': 'Publicación de documentos por el proveedor y revisión/aprobación por el cliente, con plazos y trazabilidad.',
    'description': """
Módulo 1 — Flujo de Revisión y Aceptación (Proveedor ↔ Cliente)
================================================================
- Checklist maestro reutilizable (carpetas + ítems) ajustable por cliente.
- Apertura de proceso por proveedor: copia del checklist, plazos derivados
  de la fecha de vencimiento.
- Portal proveedor: publicación y corrección de ítems (uploads validados).
- Portal cliente: revisión con estados (aprobado/observado) + hilo de comentarios.
- Fases y semáforo de urgencia; crons de apertura automática y control de plazo.
Modelos 100% en código (sin Studio). Arquitectura estilo Certum Global.
""",
    'author': 'Certum Global',
    'license': 'LGPL-3',
    'depends': ['base', 'portal', 'website', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/config_params.xml',
        'data/mail_templates.xml',
        'data/cron.xml',
        'views/checklist_views.xml',
        'views/proceso_views.xml',
        'views/res_partner_views.xml',
        'views/menus.xml',
        'views/portal_common.xml',
        'views/hub/portal_home.xml',
        'views/proveedor/portal_proceso.xml',
        'views/cliente/portal_revision.xml',
        'views/admin/panel.xml',
        'views/plantillas/builder.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'certum_revision/static/src/css/portal_base.css',
            'certum_revision/static/src/css/hub/home.css',
            'certum_revision/static/src/css/proveedor/proceso.css',
            'certum_revision/static/src/css/cliente/revision.css',
            'certum_revision/static/src/css/admin/panel.css',
            'certum_revision/static/src/css/plantillas/builder.css',
            'certum_revision/static/src/css/proceso/gestion.css',
            'certum_revision/static/src/js/portal_base.js',
            'certum_revision/static/src/js/hub/home.js',
            'certum_revision/static/src/js/admin/panel.js',
            'certum_revision/static/src/js/plantillas/builder.js',
            'certum_revision/static/src/js/proceso/gestion.js',
            'certum_revision/static/src/js/proceso/estructura.js',
        ],
    },
    'application': True,
    'installable': True,
}
