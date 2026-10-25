# FYLE360 — FYLE 360

Repo de **un solo módulo Odoo 18**: `certum_revision`, que es **FYLE 360**, la
plataforma de revisión documental de Certum Global: el proveedor publica
documentos, el cliente los aprueba u observa dentro de un plazo, con correos,
trazabilidad y un panel de administración web propio.

Esta carpeta **es la carpeta de addons**: en el servidor se clona tal cual en
`/cloudclusters/odoo/fyle_addons` y esa ruta se suma al `addons_path` (mismo
patrón que `monitoreos_addons`, `elearning_addons` y `productos_addons`).
Despliegue paso a paso en [DEPLOY.md](DEPLOY.md).

```
FYLE360/                       ← git (ATARX004/fyle360, rama main)
├── certum_revision/           ← el módulo (FYLE 360)
├── tools/sync_docker.ps1      ← copia el módulo a la carpeta que monta el Docker local
├── DEPLOY.md                  ← despliegue en el servidor
├── PROJECT.md                 ← estado, reglas y changelog (fuente de verdad operativa)
└── README.md
```

> **Por qué el módulo no se llama `fyle360`:** está instalado en producción
> como `certum_revision`, con datos reales en las tablas `certum_rev_*`.
> Renombrarlo sería, para Odoo, un módulo nuevo: habría que migrar los datos y
> los enlaces de los correos ya enviados dejarían de funcionar. FYLE 360 es el
> nombre visible; `certum_revision` el técnico.

El historial de git viene del repo anterior (`ISO 21`), filtrado para que solo
quede el módulo: los 48 commits desde la v0.1 siguen aquí.

## Reglas del módulo

- **Independiente.** Depende solo de `base`, `portal`, `website` y `mail`. No
  importa ni llama a ningún otro módulo propio; desinstalarlo no rompe nada.
- **Sin backend.** No tiene menús ni vistas en el backend de Odoo: todo se
  administra en `/my/certum/admin`.
- Documentación del módulo (rutas, roles, correos, reglas): 
  [certum_revision/README.md](certum_revision/README.md).

## Cambios frecuentes

| Quiero… | Dónde |
|---|---|
| Cambiar el texto de un correo | En el panel: Administración → Correos → Plantillas (no en el código) |
| Añadir un aviso por correo nuevo | `certum_revision/data/correo_data.xml` + `models/correo.py` |
| Cambiar el marco de los correos | `certum_revision/views/correo_layout.xml` |
| Una pantalla del panel de administración | `controllers/admin/*.py` + `views/admin/*.xml` |
| Colores y tipografía | `certum_revision/static/src/css/portal_base.css` (tokens `--sr-*`) |
| Plazos por defecto | En el panel: Administración → Ajustes |

Qué exige cada cambio: `.py` → **reiniciar** Odoo · `.xml` → `-u certum_revision` ·
`.css/.js` → `-u certum_revision` + Ctrl+F5.

## Trabajo en local (Docker de `dev_local`)

El Docker monta como addons la carpeta
`…\extra_addons\.claude\.claude\worktrees\kind-cannon-8ab307`. Ahí vive una
**copia sin `.git`** de `certum_revision/`; el git está solo aquí.

1. Editar en **este** repo.
2. Copiar al Docker: `.\tools\sync_docker.ps1`
3. Aplicar en el clon (PowerShell, desde `…\kind-cannon-8ab307\dev_local`):
   ```powershell
   docker compose exec -T odoo odoo -c /etc/odoo/odoo.conf -d signa_local -u certum_revision --stop-after-init --no-http
   docker compose restart odoo
   ```
4. Abrir `http://localhost:8069/my/certum` (Ctrl+F5).
5. `git add <rutas>` / `git commit` / `git push` desde este repo (nunca `git add -A`).
