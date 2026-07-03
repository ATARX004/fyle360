# certum_revision — Flujo de Revisión y Aceptación (Módulo 1)

Odoo 18 Enterprise · modelos 100% en código (sin Studio) · arquitectura portal estilo Certum Global.

## Qué hace

El proveedor publica los documentos de un checklist (organizado en carpetas);
el cliente los revisa, comenta y aprueba/observa dentro de un plazo derivado de
la fecha de vencimiento del proveedor. Detalle completo en
`../PLAN_modulo1_revision_aceptacion.md`.

## Instalación

1. Copiar `certum_revision/` a la carpeta de addons y reiniciar Odoo.
2. Instalar el módulo **Certum Global — Flujo de Revisión y Aceptación** (app).
3. Asignar el grupo **Revisión / Interno** al equipo Certum Global.

## Puesta en marcha (primer flujo)

1. **Backend → Certum Global · Revisión → Checklists maestros**: crear la plantilla
   (carpetas + ítems, marcar los obligatorios).
2. En **Contactos**, asignar `Rol en Certum Global` = *Proveedor* / *Cliente* a las
   empresas (los usuarios portal deben ser contactos de esas empresas).
3. **Certum Global · Revisión → Procesos**: crear proceso (proveedor, cliente, checklist,
   fecha de vencimiento) y pulsar **Abrir proceso** (o dejar que el cron lo abra
   ~3 meses antes del vencimiento).
4. Portal:
   - Proveedor: `/my/certum` → `/my/procesos` → publica cada ítem (drawer AJAX).
   - Cliente: `/my/certum` → `/my/revisiones` → aprueba u observa con comentario.

## Rutas portal (contrato estable)

| Ruta | Actor | Descripción |
|---|---|---|
| `GET /my/certum` | ambos | Hub con KPIs |
| `GET /my/procesos` | proveedor | Sus procesos |
| `GET /my/revisiones` | cliente | Procesos de sus proveedores |
| `GET /my/proceso/<id>` | ambos | Detalle (tabs por carpeta + drawer) |
| `GET /my/item/<id>/panel` | ambos | JSON del drawer (datos + hilo + acciones) |
| `POST /my/item/<id>/publicar` | proveedor | Sube/corrige documento |
| `POST /my/item/<id>/aprobar` | cliente | Aprueba el ítem |
| `POST /my/item/<id>/observar` | cliente | Observa con comentario |
| `POST /my/item/<id>/comentar` | ambos | Comenta en el hilo |
| `GET /my/item/<id>/download/<att_id>` | ambos | Descarga verificando pertenencia |

## Configuración (ir.config_parameter)

| Clave | Default | Uso |
|---|---|---|
| `certum_revision.dias_apertura` | 90 | Apertura antes del vencimiento |
| `certum_revision.dias_duracion` | 45 | Duración del proceso |
| `certum_revision.dias_urgente` | 15 | Umbral semáforo URGENTE |
| `certum_revision.dias_critico` | 5 | Umbral semáforo CRÍTICO |
| `certum_revision.max_upload_mb` | 50 | Tamaño máximo de upload |

## Notas de desarrollo

- Tras editar XML: `-u certum_revision`. CSS/JS: `?debug=assets`. Controllers:
  `--dev xml,reload` o reinicio.
- La validación central de acciones por estado/rol vive en
  `controllers/helpers.py::_get_item_error` (máquina de estados §6 del plan).
- Los `template_id` y las URLs son contrato: no cambiarlos al refactorizar.
- Gancho para el Módulo 2 (generador): `doc_template_code` en ítems del maestro
  y del proceso.
