# -*- coding: utf-8 -*-
"""Hooks de instalación del módulo.

Alinea la ACL con la lógica de roles: el rol 'interno' se detecta por
`not user.share`, así que damos el grupo Interno a todos los usuarios internos
existentes al instalar. Evita tener que asignarlo a mano (o por shell) para que
el equipo entre al backend desde el primer momento.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    group = env.ref('certum_revision.group_certum_rev_interno',
                    raise_if_not_found=False)
    if not group:
        return
    internos = env['res.users'].search([
        ('share', '=', False),
        ('active', '=', True),
    ])
    faltantes = internos.filtered(lambda u: group not in u.groups_id)
    if faltantes:
        group.sudo().write({'users': [(4, u.id) for u in faltantes]})
        _logger.info('[AUDIT] post_init: grupo Interno asignado a %s usuario(s)',
                     len(faltantes))
