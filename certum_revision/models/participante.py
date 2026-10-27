# -*- coding: utf-8 -*-
"""Roles de un proyecto concreto.

Por defecto un proyecto usa los roles GENERALES: participa todo el personal
de la empresa proveedora y de la cliente, cada uno con el nivel que tiene en
Administración → Empresas y roles. Para cada lado del proyecto (proveedor y
cliente) Certum puede cambiar a roles PROPIOS: entonces solo participan las
personas de esta lista, con el nivel que se les dé aquí.

Quien queda fuera de un lado con roles propios deja de ver el proyecto y no
recibe ninguno de sus correos. Su nivel general no cambia: sigue valiendo en
los demás proyectos.
"""
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CertumRevParticipante(models.Model):
    _name = 'certum.rev.participante'
    _description = 'Participante de un proyecto (roles propios)'
    _order = 'lado, nivel, id'

    proceso_id = fields.Many2one('certum.rev.proceso', required=True,
                                 ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Persona', required=True,
                                 ondelete='cascade', index=True)
    lado = fields.Selection([('proveedor', 'Proveedor'), ('cliente', 'Cliente')],
                            required=True)
    nivel = fields.Integer(
        string='Nivel en el proyecto', default=0,
        help='1 = máximo. 0 = participa sin nivel (no aprueba por capas ni '
             'autoriza solicitudes).')

    _sql_constraints = [
        ('persona_unica', 'unique(proceso_id, partner_id)',
         'Esa persona ya está en el proyecto.'),
    ]

    @api.constrains('partner_id', 'lado', 'proceso_id')
    def _check_empresa(self):
        """Cada persona va en el lado de SU empresa: nadie de otra compañía
        se cuela en el proyecto."""
        for p in self:
            empresa = (p.proceso_id.proveedor_id if p.lado == 'proveedor'
                       else p.proceso_id.cliente_id)
            if p.partner_id.is_company or p.partner_id.commercial_partner_id != empresa:
                raise ValidationError(_(
                    '%(persona)s no es personal de %(empresa)s.',
                    persona=p.partner_id.display_name, empresa=empresa.display_name))
            if p.nivel < 0 or p.nivel > 20:
                raise ValidationError(_('El nivel debe estar entre 0 y 20.'))
