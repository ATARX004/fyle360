# -*- coding: utf-8 -*-
"""Marca de depuración de versiones antiguas.

Regla de negocio: de cada ítem solo se conserva el ARCHIVO VIGENTE
(`attachment_final_id`). Las versiones superadas y los adjuntos de marcas del
cliente se depuran a los N días (parámetro `certum_revision.dias_purga_versiones`,
10 por defecto).

"Depurar" borra el CONTENIDO del archivo, nunca el registro: el adjunto sigue
existiendo con su nombre, su fecha y su autor, marcado como depurado. Así la
trazabilidad de que ese documento existió queda intacta aunque el binario ya
no ocupe espacio.
"""
from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    certum_purgado = fields.Boolean(
        string='Contenido depurado', default=False, copy=False, index=True,
        help='El contenido del archivo fue eliminado por antigüedad; el '
             'registro se conserva como constancia de que existió.')
    certum_purgado_fecha = fields.Datetime(
        string='Fecha de depuración', readonly=True, copy=False)
