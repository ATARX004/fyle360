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

### A2. Copia de seguridad y retirar la copia vieja de `extra_addons`

1. **Backup de la base** antes de nada: esta versión crea dos tablas
   (`certum_rev_correo_caso`, `certum_rev_correo_envio`) y una columna en
   `res_partner`. Desde `https://certumglobal.pe/web/database/manager` → **Backup**
   de `certum-global-sac` (con filestore).

2. Comprobar que la copia vieja **no** la controla el git de VALIDA (si saliera
   algo, un `git pull` en `extra_addons` la volvería a traer: avisar antes de seguir):

```bash
cd /cloudclusters/odoo/extra_addons && git ls-files certum_revision | head -1
```

3. Moverla **fuera** de cualquier ruta del `addons_path` (no se borra: es la vuelta atrás):

```bash
mkdir -p /cloudclusters/odoo/backups
mv /cloudclusters/odoo/extra_addons/certum_revision /cloudclusters/odoo/backups/certum_revision-$(date +%F-%H%M)
ls /cloudclusters/odoo/backups
```

### A3. Sumar la ruta al `addons_path`

```bash
CONF=/cloudclusters/config/odoo/odoo.conf
cp -a "$CONF" "$CONF.bak-$(date +%F-%H%M)"
sed -i 's#^addons_path *=.*#&,/cloudclusters/odoo/fyle_addons#' "$CONF"
grep -n "^addons_path" "$CONF"   # UNA sola línea, terminada en ,/cloudclusters/odoo/fyle_addons
```

### A4. Actualizar y reiniciar

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

- `https://certumglobal.pe/my/certum` abre con la marca FYLE 360.
- `https://certumglobal.pe/my/certum/admin` (usuario interno): Resumen, Proyectos,
  Empresas, Plantillas, Correos y Ajustes.
- **Correos → Remitente**: elegir el servidor de `sistemas@certumglobal.pe`
  (se elige solo si existe) y comprobar «Hoy salen como…».
- **Correos → Plantillas → Enviar prueba** a un buzón propio: llega con FYLE 360
  arriba.
- **Ajustes → Tareas programadas**: «Cola de correos» y «Avisos del día» encendidas.
- En el backend ya no aparece el menú «Certum Global · Revisión».
- Logs limpios: `tail -n 100 /var/log/supervisor/odoo.log`

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
