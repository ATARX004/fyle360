# DEPLOY — `certum_revision` / FYLE 360 (carpeta de addons propia)

Mismo patrón que `monitoreos_addons` (ver `MONITOREOS/DEPLOY_MONITOREOS.md`):
un repo = una carpeta de addons en el servidor. No toca el git de
`extra_addons` (repo de VALIDA) ni las otras carpetas.

| Dato | Valor |
|---|---|
| Repo | `ATARX004/fyle360` (privado) — rama `main` |
| Carpeta en el servidor | `/cloudclusters/odoo/fyle_addons` |
| Copia vieja a retirar | `/cloudclusters/odoo/extra_addons/certum_revision` (desplegada por ZIP) |
| `odoo.conf` que lee el servicio | `/cloudclusters/config/odoo/odoo.conf` |
| Base de datos | `certum-global-sac` |
| Python / binario | `/cloudclusters/odoo/venv/bin/python3` · `/cloudclusters/odoo/odoo-bin` |
| Servicio | `supervisorctl restart odoo` |

⚠ **El módulo YA está instalado en producción**: siempre `-u certum_revision`,
nunca `-i`.
⚠ `-u` no recarga el Python del servicio vivo: si tocaste un `.py`, **reinicia**.
⚠ El `-u` se corre como **`odoo`** (`gosu odoo …`), no como root.
⚠ Si `certum_revision` existe en dos rutas del `addons_path`, gana la primera:
por eso el paso A2 retira la copia de `extra_addons` **antes** de sumar la ruta nueva.
⚠ Antes de cada `-u`, que no quede ninguna consola de Odoo abierta: una sesión
olvidada retiene tablas y hace fallar el `ALTER TABLE`.
`ps aux | grep "odoo-bin shell" | grep -v grep` debe salir vacío.

---

## Parte A — Una sola vez

### A0. En la PC: subir el repo

1. GitHub → **New repository** → `fyle360` → **Private** → sin README ni .gitignore.
2. En PowerShell:

```powershell
cd "C:\Users\jesus\OneDrive\Desktop\ODOO MODULOS DE HOMOLOGACION Y DE INSPECCION\FYLE360"
git remote add origin https://github.com/ATARX004/fyle360.git
git push -u origin main
```

### A1. En el servidor: llave de despliegue propia y clonado

GitHub no deja reutilizar una deploy key en dos repos: va una nueva.

```bash
ssh-keygen -t ed25519 -C "fyle-deploy" -f ~/.ssh/id_fyle -N ""
cat ~/.ssh/id_fyle.pub
# GitHub → repo fyle360 → Settings → Deploy keys → Add deploy key
#   (pegar la clave, SIN marcar "Allow write access")

cat >> ~/.ssh/config <<'EOF'

Host github-fyle
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_fyle
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

ssh -T git@github-fyle     # saluda con tu usuario; "shell access" denegado es normal
git clone git@github-fyle:ATARX004/fyle360.git /cloudclusters/odoo/fyle_addons
chown -R $(stat -c '%U:%G' /cloudclusters/odoo/extra_addons) /cloudclusters/odoo/fyle_addons
ls /cloudclusters/odoo/fyle_addons      # debe verse certum_revision/
```

> Si `~/.ssh` no persiste en el contenedor (pasó con `/root` en otros despliegues),
> repetir el bloque de la llave tras recrearlo.

### A2. Qué cambia en la base, comprobación previa y copia de seguridad

Producción tiene la **v0.4 (2026-08-19)**. Esta versión trae todo lo hecho
desde entonces (PROJECT.md, entradas b a x), así que **no es solo de vistas**:

| El `-u` **añade** (sin tocar lo existente) | El `-u` **retira** |
|---|---|
| Tablas `certum_rev_ampliacion`, `certum_rev_difusion` (+2 relaciones), `certum_rev_correo_caso`, `certum_rev_correo_envio` | Menú «Certum Global · Revisión», acciones y vistas del backend (el panel web las sustituye) |
| Columnas nuevas, vacías, en `certum_rev_item`, `certum_rev_carpeta`, `certum_rev_checklist_item`, `certum_rev_ampliacion` y `res_partner` (`certum_correo_cc`) | Las 3 plantillas `mail.template` antiguas del módulo (las sustituyen las 9 del panel de Correos) |
| Valores nuevos en selecciones (traza, aprobación) | Copias de las pantallas de FYLE 360 hechas con el editor del sitio web, si las hubiera (taparían las vistas nuevas) |
| Parámetros nuevos (los que ya existen **conservan** su valor) y los crons de correo | — |

**No se modifican** proyectos, documentos, archivos, aprobaciones, comentarios,
empresas, roles, niveles ni plazos ya fijados. `certum_revision.correo_desde`
se fija en el momento del `-u`: **no sale ningún correo sobre lo anterior**.

1. Comprobación previa, **solo lectura** (cuántas copias web y plantillas
   antiguas retirará el `-u`):

```bash
echo "V=env['ir.ui.view'].sudo().with_context(active_test=False); print('copias web:', V.search([('key','=like','certum_revision.%'),('website_id','!=',False)]).mapped('key')); print('plantillas antiguas:', env['mail.template'].sudo().search([('model_id.model','=like','certum.rev.%')]).mapped('name'))" | gosu odoo /cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin shell -c /cloudclusters/config/odoo/odoo.conf -d certum-global-sac --no-http 2>/dev/null | tail -2
```

2. **Backup de la base** (con las credenciales que ya usa Odoo):

```bash
CONF=/cloudclusters/config/odoo/odoo.conf; v(){ grep -E "^$1 *=" "$CONF" | head -1 | cut -d= -f2- | xargs; }; H=$(v db_host); P=$(v db_port); U=$(v db_user); [ "$H" = "False" ] && H=""; [ "$P" = "False" ] && P=""; mkdir -p /cloudclusters/odoo/backups && PGPASSWORD="$(v db_password)" pg_dump ${H:+-h "$H"} ${P:+-p "$P"} -U "$U" -Fc -f /cloudclusters/odoo/backups/certum-global-sac-$(date +%F-%H%M).dump certum-global-sac && ls -lh /cloudclusters/odoo/backups/
```

   Si `pg_dump` no existe en el contenedor: `https://certumglobal.pe/web/database/manager`
   → **Backup** de `certum-global-sac` con filestore.

3. **Backup del filestore** (los archivos subidos):

```bash
CONF=/cloudclusters/config/odoo/odoo.conf; D=$(grep -E "^data_dir *=" "$CONF" | cut -d= -f2- | xargs); D=${D:-$(getent passwd odoo | cut -d: -f6)/.local/share/Odoo}; ls "$D/filestore/certum-global-sac" >/dev/null && tar -czf /cloudclusters/odoo/backups/filestore-certum-global-sac-$(date +%F-%H%M).tgz -C "$D/filestore" certum-global-sac && ls -lh /cloudclusters/odoo/backups/
```

4. Comprobar que la copia vieja **no** la controla el git de VALIDA (si saliera
   algo, un `git pull` en `extra_addons` la volvería a traer: avisar antes de seguir):

```bash
cd /cloudclusters/odoo/extra_addons && git ls-files certum_revision | head -1
```

5. Moverla **fuera** de cualquier ruta del `addons_path` (no se borra: es la vuelta atrás):

```bash
mkdir -p /cloudclusters/odoo/backups && mv /cloudclusters/odoo/extra_addons/certum_revision /cloudclusters/odoo/backups/certum_revision-$(date +%F-%H%M) && ls /cloudclusters/odoo/backups
```

### A3. Sumar la ruta al `addons_path`

```bash
CONF=/cloudclusters/config/odoo/odoo.conf
cp -a "$CONF" "$CONF.bak-$(date +%F-%H%M)"
sed -i 's#^addons_path *=.*#&,/cloudclusters/odoo/fyle_addons#' "$CONF"
grep -n "^addons_path" "$CONF"   # UNA sola línea, terminada en ,/cloudclusters/odoo/fyle_addons
```

### A4. Actualizar y reiniciar

Antes, que no quede ninguna consola de Odoo abierta (debe salir vacío):

```bash
ps aux | grep "odoo-bin shell" | grep -v grep
```

```bash
CONF=/cloudclusters/config/odoo/odoo.conf
gosu odoo /cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin -c "$CONF" \
  -d certum-global-sac -u certum_revision --stop-after-init --no-http
supervisorctl restart odoo
supervisorctl status odoo
tail -n 100 /var/log/supervisor/odoo.log
```

En el log del `-u` es normal ver `Deleting … certum_revision.menu_…`,
`action_proceso`, `view_proceso_form`…: son los menús y vistas de backend que
esta versión retira.

### A5. Verificación

- `https://certumglobal.pe/fyle360`: la landing abre sin iniciar sesión.
- `https://certumglobal.pe/my/certum` con un usuario interno: menú lateral con
  Inicio, Recibidos y el grupo **Administración** (Empresas y roles, Plantillas,
  Proyectos, Correos, Ajustes). El Inicio muestra «Requiere atención».
- Con un usuario cliente y uno proveedor: cada uno ve su menú y su Inicio.
- Un proyecto existente abre con sus documentos, estados y archivos de antes.
- **Correos → Remitente**: elegir el servidor de `sistemas@certumglobal.pe`
  (se elige solo si existe) y comprobar «Hoy salen como…».
- **Correos → Plantillas → Enviar prueba** a un buzón propio: llega con FYLE 360
  arriba.
- **Ajustes → Tareas programadas**: «Cola de correos» y «Avisos del día» encendidas.
- En el backend ya no aparece el menú «Certum Global · Revisión».
- Logs limpios: `tail -n 100 /var/log/supervisor/odoo.log`

> **Correos nuevos desde la mañana siguiente.** Los avisos de siempre (publicado,
> aprobado, observado) siguen saliendo al momento. Lo nuevo —resumen diario de
> pendientes, «por vencer» y plazo del proyecto— empieza a las **8:00 de Lima del
> día siguiente**. Si alguno no se quiere aún, desactívelo en Correos →
> Plantillas antes de esa hora (o pause todo en Correos → Remitente).

### A6. Vuelta atrás

```bash
CONF=/cloudclusters/config/odoo/odoo.conf
BAK=$(ls -t "$CONF".bak-* | head -1); echo "$BAK"                                   # el backup más reciente del conf
VIEJA=$(ls -td /cloudclusters/odoo/backups/certum_revision-* | head -1); echo "$VIEJA"  # la copia retirada en A2
cp -a "$BAK" "$CONF"                                   # quita fyle_addons del addons_path
mv "$VIEJA" /cloudclusters/odoo/extra_addons/certum_revision
gosu odoo /cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin -c "$CONF"   -d certum-global-sac -u certum_revision --stop-after-init --no-http
supervisorctl restart odoo
```

Revisa que los dos `echo` muestren lo esperado antes de seguir. Si el `-u` de
la versión vieja fallara por las tablas nuevas, restaurar el backup de la base
del paso A2.

---

## Parte B — Cada cambio (rutina)

En la PC:

```powershell
cd "C:\Users\jesus\OneDrive\Desktop\ODOO MODULOS DE HOMOLOGACION Y DE INSPECCION\FYLE360"
.\tools\sync_docker.ps1      # y probar en el Docker local (README.md)
git add certum_revision README.md DEPLOY.md tools
git commit -m "..."
git push
```

En el servidor:

```bash
CONF=/cloudclusters/config/odoo/odoo.conf
cd /cloudclusters/odoo/fyle_addons && git pull && \
gosu odoo /cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin -c "$CONF" \
  -d certum-global-sac -u certum_revision --stop-after-init --no-http && \
supervisorctl restart odoo
```

Ya no hace falta el ZIP ni el `chmod` de cada despliegue: `git pull` conserva
los permisos y el `chown` del paso A1 deja la carpeta del usuario de Odoo.
