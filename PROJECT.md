# FYLE 360 (`certum_revision`) — estado, despliegue y changelog (Odoo 18 Enterprise)

Estado del proyecto, despliegue, reglas y control de cambios. **Este archivo es
la fuente de verdad operativa**; manténlo actualizado en cada sesión.

Última actualización: **2026-10-26** — 18.0.2.0.0 en producción — el módulo pasa a llamarse **FYLE 360** y vive en su propio repo (`FYLE360`, ATARX004/fyle360). Desde aquí, **la fuente de verdad del código es ese repo**.

---

## 1. Estado actual

| Módulo | Estado | Notas |
|---|---|---|
| **certum_revision** → **FYLE 360** (Módulo 1 · Revisión documental) | 🟢 **18.0.2.0.0 desplegada en producción** (2026-10-26) | Primer despliegue por git desde `/cloudclusters/odoo/fyle_addons` (ver «Despliegue 2026-10-26» en el changelog). Pendiente: verificación funcional completa y repasar la configuración de correos en el panel. |
| **certum_generador** (Módulo 2 · Generador de documentos) | ⚪ No iniciado | Gancho ya previsto: campo `doc_template_code` en ítems. Ver `PLAN_modulo_generador_documentos.md`. |

**Verificado en producción (v0.2):**
- **Hub** por rol con KPIs y avatar de empresa (foto de Contactos).
- **Panel admin (interno)** `/my/certum/admin`: asignar roles a compañías y, por
  proveedor, **qué clientes puede elegir** (M2M `certum_cliente_ids`).
- **Panel proveedor/interno** `/my/plantillas`: constructor de plantillas
  (carpetas + ítems) e **iniciar proceso** (elige cliente asignado + inicio + plazo).
- **Proceso**: publicación de ítems por el proveedor (uploads `ir.attachment`
  con historial), revisión del cliente (aprobar/observar + hilo), avance y
  semáforo. Plazo = `fecha_inicio + plazo_dias`.
- **Notificaciones** por correo al publicar/aprobar/observar.
- **Seguridad**: ACL + record rules (portal solo lectura), control fino por
  propiedad/rol en cada endpoint, resolución de rol por empresa participante.

**En producción y verificado (v0.4):**
- **Jerarquía por niveles** (`res.partner.certum_nivel`) + panel "Personal/niveles".
- **Aprobación por capas**: `revision_modo` (cualquiera/secuencial) + `revision_capas`,
  con traza inmutable `certum.rev.aprobacion`.
- **Ventana de revisión**: `dias_revision` en la primera publicación,
  `fecha_limite_revision`, cron `cron_auto_aprobar_revision` (cada 6 h) y +3 días
  de corrección al observar.
- **Solicitudes de plazo** (`certum.rev.solicitud`): el cliente pide días, sube por
  niveles y el proveedor aprueba/rechaza.
- **Cadena de revisores a medida** (`certum.rev.revisor`) con reparto de días por
  pasos, auto-avance y traza `no_reviso`.
- **Nota + subida del cliente** al observar (`attachment_cliente_ids`).
- **Descarga del expediente en ZIP** (`GET /my/proceso/<id>/descargar`) y
  **depuración automática de versiones superadas** a los 10 días.
- **Participantes designados por proceso** (`certum.rev.revisor.proceso_id`):
  tercer modo de revisión, con personas concretas y su orden.
- **Carpetas anidadas** en plantillas y expedientes (hasta 5 niveles), con
  ítems en cualquier nivel.

> Todo lo anterior está desplegado y en uso.

**En producción y verificado (2026-08-24, entradas (j) a (m)):**
- **Ampliación de la ventana de revisión de un documento** (`certum.rev.ampliacion`),
  que **no es** la ampliación del plazo general del expediente. El revisor la
  **pide**; el **proveedor** la concede o rechaza —él fijó esos días al
  publicar, así que él los amplía—.
- El proveedor **elige a quién** van los días: al turno actual o a un revisor
  posterior, en cuyo caso quedan **reservados** hasta que le toque. A un turno
  ya pasado, o a alguien fuera de la cadena, no se conceden.
- **La corrección vuelve a quien observó**, con sus días de revisión otra vez,
  y desde ahí sigue al resto de la cadena. Las aprobaciones anteriores se
  conservan.

**En el repo, pendiente de desplegar (entradas (n) a (v)):**
- **Devolver un turno vencido**: el proveedor (o Certum interno) puede reabrir
  el turno de un revisor al que el sistema saltó por no revisar a tiempo, con
  los días que necesite. Si el ítem se había auto-aprobado, se reabre; si eso
  había cerrado el expediente, el expediente vuelve a revisión.
- **Se bloquea** si después de la omisión alguien ya aprobó u observó: eso sería
  anular a un revisor, no reabrir un turno.
- **Fix**: ampliar el plazo de un expediente vencido vuelve a activarlo. Antes
  se quedaba congelado en `fuera_plazo` y no se podía trabajar en él.
- **Fix**: la caja de observación ya no recorta el botón de enviar cuando se
  adjunta un archivo.
- **Panel lateral en tres pestañas**: Documento (archivo, acciones y hilo de
  comentarios), Revisión (cadena, días, turnos) y Trazabilidad.
- **Borrar archivos** de un documento que nadie ha revisado, para volver a
  publicar con la zona limpia.
- **Sustituir el documento final** de un ítem ya aprobado, sin reabrir la
  revisión, sin generar versión y sin marca visible (pero con traza).
- El **ZIP** pasa a ser solo del proveedor y del personal interno.
- **Avisos por correo**: despachador único, panel de configuración en
  `/my/certum/admin/correos` y avisos de plazo por vencer.
- **Difusión** de documentos aprobados a contactos del cliente (con creación de
  su usuario de portal si no lo tienen) y **repositorio** en `/my/repositorio`,
  visible solo para quien recibió cada documento.
- **Deshacer la última publicación**, mientras nadie haya revisado esa versión.
- **Confirmación** antes de publicar sobre un documento que ya se está
  revisando, avisando de que reinicia la cadena.
- «Proceso» pasa a llamarse **«proyecto»** en toda la interfaz.
- **El proyecto se cierra a mano**: aprobarlo todo ya no lo cierra, para poder
  seguir reorganizándolo. Y se puede reabrir.
- Requiere `-u certum_revision` (un valor más en la traza y una plantilla de
  correo nueva).

> El siguiente bloque de trabajo son el resto de las **notificaciones
> automáticas por correo** (§5) —el aviso de turno devuelto ya es el primero—,
> seguido del **arrastrar y soltar** y el **tablero por estado**.

**Falta / por definir:** integración `documents.document`, reportes/consolidados,
icono de la app. Ver §5 Roadmap. (Los datos demo ya existen: §2 · Datos de
demostración.)

**Estado del repo (2026-08-24):** el working tree se commitea con cada entrada
de este changelog. Lo desplegado y verificado en producción llega hasta la
entrada **(m)**; de **(n)** a **(v)** están en el repo y en el ZIP, pendiente de `-u`. Antes de
cualquier `-u`, comprobar que no queden `odoo-bin shell` vivos (§2 · Diagnóstico
rápido): son la causa conocida de `LockNotAvailable`.

**Verificación local:** no hay instancia de Odoo en el equipo de desarrollo, así
que cada cambio de lógica se prueba extrayendo el código REAL del módulo y
ejercitándolo contra objetos ORM simulados. Las suites viven en el scratchpad de
la sesión: `test_zip`, `test_cadena`, `test_arbol`, `test_guard`, `test_tz`,
`test_avance`, `test_estructura`, `test_ampliacion`, `test_beneficiario`,
`test_reanudar`, `test_reversion`, `test_revivir`, `test_deshacer`,
`test_limpiar`, `test_final`, `test_avisos`, `test_difusion` y `test_cierre`,
más `check_js` (balance de delimitadores,
consciente de los literales regex y de las cadenas partidas). **Las 18 en verde.** Un fallo en ellas suele ser el mock
desactualizado, no el módulo:
confírmalo antes de "arreglar" código que funciona.

> ⚠️ Los `PLAN_*.md` usan el nombre antiguo "signa" y el modelo de plazo viejo;
> **el código vigente es `certum_revision` / `certum.rev.*`** con plazo
> `fecha_inicio + plazo_dias`. Este `PROJECT.md` es la fuente de verdad.

---

## 2. Entorno y despliegue (servidor Cloud Clusters, SSH)

> **Desde la 18.0.2.0.0 el despliegue es por git**, no por ZIP: el módulo vive
> en `/cloudclusters/odoo/fyle_addons` (clon de este repo). Los pasos vigentes
> están en [DEPLOY.md](DEPLOY.md). Lo de abajo sobre ZIP y `extra_addons` queda
> como referencia histórica hasta que se complete el traslado.

| Dato | Valor |
|---|---|
| Base de datos | `certum-global-sac` |
| Raíz Odoo | `/cloudclusters/odoo/` |
| Binario | `/cloudclusters/odoo/odoo-bin` |
| Python (venv) | `/cloudclusters/odoo/venv/bin/python3` |
| Ruta de addons | `/cloudclusters/odoo/extra_addons/` |
| Módulo en servidor | `/cloudclusters/odoo/extra_addons/certum_revision/` |
| Gestor de procesos | `supervisor` (`supervisorctl`) |

### Comandos operativos

**Reiniciar el portal (aplicar cambios de assets ya presentes / recuperar servicio):**
```bash
supervisorctl restart odoo
```

**Abrir la consola (shell) de Odoo:**
```bash
/cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin shell -d certum-global-sac --no-http
```

**Actualizar el módulo tras cambiar código (modelos/vistas/CSS/JS):**
```bash
/cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin \
  -d certum-global-sac -u certum_revision --stop-after-init --no-http \
  && supervisorctl restart odoo
```
> **`-u` (update) vs `-i` (install):** para un módulo **ya instalado** hay que
> usar **`-u`**. `-i` solo instala módulos nuevos; sobre uno ya instalado NO
> aplica los cambios de código. Usa `-i` únicamente la primera vez.

**Generar el ZIP (en el PC de desarrollo, Windows):**
```bash
python tools_make_zip.py    # crea certum_revision.zip con separadores '/' (POSIX)
```
> ⚠️ **No usar PowerShell `Compress-Archive`**: genera el ZIP con backslashes
> `\` como separador, lo que provoca en Linux el warning "appears to use
> backslashes as path separators" y puede romper la extracción. `tools_make_zip.py`
> usa `zipfile` con rutas `/`, correctas para el servidor.

**Desplegar una versión nueva del módulo (desde el ZIP):**
```bash
# 1) Subir certum_revision.zip a /cloudclusters/odoo/extra_addons/ (gestor de archivos)
cd /cloudclusters/odoo/extra_addons
rm -rf certum_revision          # el .zip queda al lado, no se borra
unzip certum_revision.zip       # o, si no hay unzip:
# /cloudclusters/odoo/venv/bin/python3 -m zipfile -e certum_revision.zip .

# 2) ⚠️ OBLIGATORIO tras descomprimir: corregir permisos (ver aviso abajo)
find certum_revision -type d -exec chmod 755 {} \;
find certum_revision -type f -exec chmod 644 {} \;

# 3) Actualizar + reiniciar
/cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin \
  -d certum-global-sac -u certum_revision --stop-after-init --no-http \
  && supervisorctl restart odoo
```
> **Permisos (causa del "Error de estilo"):** al descomprimir el ZIP, las
> subcarpetas de `static/` suelen quedar sin permiso de lectura/traspaso para el
> usuario de Odoo → no puede leer los CSS y el bundle falla ("could not get
> content for …"; el file manager tampoco deja entrar a `static`). El
> `chmod 755` (carpetas) + `644` (archivos) del paso 2 lo resuelve. Windows no
> guarda permisos Unix en el ZIP, así que **este paso hay que repetirlo en cada
> despliegue por ZIP**. Opcional: ajustar el dueño con
> `chown -R <usuario_odoo>: certum_revision` (mira el usuario con
> `ps aux | grep odoo-bin | grep -v grep`).

### Datos de demostración (QA)

`certum_revision/tools/seed_demo.py` siembra un escenario completo para probar el
flujo sin cargar nada a mano. **Viaja dentro del ZIP**, así que tras desplegar ya
está en el servidor.

```bash
cd /cloudclusters/odoo/extra_addons
/cloudclusters/odoo/venv/bin/python3 /cloudclusters/odoo/odoo-bin shell     -d certum-global-sac --no-http < certum_revision/tools/seed_demo.py
```

Crea (todo prefijado `[DEMO]`, idempotente — se puede correr varias veces):
- **Proveedor** `[DEMO] Constructora Andina S.A.C.` con 2 contactos (niveles 1-2).
- **Cliente** `[DEMO] Minera Cerro Verde S.A.A.` con 3 contactos (niveles 1-3).
- 5 **usuarios portal** (`demo.*@certumglobal.pe`, contraseña en la constante
  `DEMO_PASSWORD` del script — cambiarla antes de correr si el entorno es accesible).
- El M2M `certum_cliente_ids` del proveedor apuntando al cliente.
- **Plantilla** `[DEMO] Homologación SSOMA 2026`: 3 carpetas / 10 ítems reales
  (RNP, T-Registro, política SST, IPERC, SCTR, EMO, capacitaciones, residuos…).
- **Proceso abierto** (`action_abrir`) con los ítems copiados, plazo 30 días.

La **política de revisión se deja sin configurar a propósito**: fijarla es el
paso 2 del guion de QA y la debe fijar el nivel 1 del cliente desde el portal.

Para revertir (borra solo lo `[DEMO]`, incluidos contactos hijos y usuarios):

```bash
CERTUM_DEMO_PURGE=1 /cloudclusters/odoo/venv/bin/python3     /cloudclusters/odoo/odoo-bin shell -d certum-global-sac --no-http     < certum_revision/tools/seed_demo.py
```

> **Por qué un script y no `data/demo.xml`:** un `demo.xml` declarado en la clave
> `'demo'` del manifest solo se carga en bases creadas **con** datos de
> demostración. `certum-global-sac` es de producción (creada sin demo), así que
> ahí nunca se cargaría. El script funciona en cualquier base y es reversible.

### Diagnóstico rápido

- **"Error de estilo / La compilación de estilos falló"** ("could not get
  content for …") → Odoo no puede **leer** un archivo de `assets`. Dos causas:
  (a) subida incompleta de subcarpetas → resubir ZIP completo; (b) **permisos**
  tras descomprimir → `chmod 755` carpetas + `644` archivos (paso 2 del deploy).
  Señal de (b): el file manager tampoco deja entrar a `static/`.
- Ver logs: revisar la salida de supervisor / el log configurado de Odoo.
- Forzar recarga de assets en el navegador: `Ctrl+Shift+R`; o añadir
  `?debug=assets` a la URL para ver el archivo exacto que falla en consola (F12).

---

## 3. Arquitectura y reglas del proyecto

Basadas en la skill `odoo-portal-architecture` (estilo Signa/Certum). **Respetar
siempre:**

1. **Modelos 100% en Python** (sin Odoo Studio). Prefijo `certum.rev.*`,
   constantes de nombres de campo centralizadas.
2. **Organización por dominio, no por tipo:** `controllers/`, `views/`, `css/`
   comparten el mismo árbol de subcarpetas (`hub/`, `proveedor/`, `cliente/`).
3. **Fachada estable = contrato:** los `template_id` y las URLs (`@http.route`)
   **no cambian** al refactorizar. Rutas portal actuales:
   - `GET /my/certum` (hub) · `GET /my/procesos` (proveedor) ·
     `GET /my/revisiones` (cliente) · `GET /my/proceso/<id>` (detalle)
   - `GET /my/item/<id>/panel` (JSON drawer) ·
     `POST /my/item/<id>/{publicar,aprobar,observar,comentar}` ·
     `GET /my/item/<id>/download/<att_id>`
4. **Seguridad en dos capas:** ACL portal solo-lectura + record rules por
   `commercial_partner_id`, y **control fino en cada endpoint** (rol + propiedad
   + fase). Nunca confiar solo en la ACL.
5. **Validación central de acciones** en `controllers/helpers.py::_get_item_error`
   (máquina de estados del ítem). Publicar/aprobar/observar/comentar delegan ahí.
6. **Roles:** interno = usuario Odoo (backend); proveedor/cliente = usuarios
   portal (frontend). Se resuelve con `res.partner.rol_en_certum` sobre el
   `commercial_partner_id` (nunca `user.partner_id.id` directo).
7. **Interfaz:** moderna y fluida. Iconos **SVG (sprite QWeb), nunca emojis**.
   Animaciones, pestañas flotantes, drawer AJAX, toasts, skeleton. Un CSS por
   dominio, registrado en el manifest. Sin `<style>` inline.
8. **Zona horaria de negocio** `America/Lima`. Los `Datetime` se guardan en UTC
   (convención Odoo) y **toda** conversión pasa por `models/tz_utils.py`, que es
   la fuente única: `today_lima()` para decidir, `fmt_lima()` para mostrar,
   `fin_de_dia_utc()` para guardar el final de un día de negocio. Nunca hacer
   `strftime` directo sobre un `Datetime` de Odoo: mostraría UTC.
9. **Auditoría:** `_logger.info("[AUDIT] <accion> user=%s ...")` en toda mutación,
   sin PII.
10. **Idempotencia:** guard anti-duplicado (proveedor + checklist + año) +
    `savepoint()` al abrir procesos.

### Identidad visual (Brandbook Certum Global, pág. 17-18)

| Token CSS | Color | Pantone | Uso |
|---|---|---|---|
| `--sr-brand` | `#3373B9` | 2383 C | Acción principal, tabs, anillos, links |
| `--sr-brand-ink` | `#145597` | 4152 C | Hover/énfasis |
| `--sr-ink` | `#121F33` | 4146 C | Texto principal, toasts |
| `--sr-navy` | `#182B48` | 2767 C | Acentos, hero |
| `--sr-muted` | `#7D8183` | compl. | Texto secundario |

Tokens en `certum_revision/static/src/css/portal_base.css`. El prefijo de clases
`sr-` se mantiene como prefijo neutro.

> Nota: en la pág. 18 del PDF del brandbook los HEX complementarios están rotos
> (placeholder "ASDASD"); los reales se extrajeron de los swatches renderizados.

---

## 4. Historial de cambios (changelog)

### 2026-10-26 (y) — Gestionar proyectos: roles propios y eliminación con código
**Versión `18.0.2.1.0`.** Cada tarjeta de Administración → Proyectos tiene
*Gestionar* (`/my/certum/admin/proyecto/<id>`, `controllers/admin/proyecto.py`),
con tres pestañas:

**1. Datos.** Referencia, fecha de inicio, plazo y vencimiento del certificado,
más abrir / marcar fuera de plazo.

**2. Roles del proyecto** (`models/participante.py`). Cada lado (proveedor y
cliente) usa los roles generales de su empresa o una lista propia del proyecto,
con un nivel por persona que solo vale ahí. Quien queda fuera de una lista
propia **no ve el proyecto** (`_rol_en_proceso` → None, y los listados filtran
con `dominio_participa`) y **no recibe ninguno de sus correos** (`_personas`
del motor de correos, ni el buzón genérico de la empresa). Los niveles del
proyecto rigen la política del nivel 1, las capas, las solicitudes de plazo y
la lista de revisores elegibles (`proceso.nivel_de`, `proceso.personal`). No
deja sacar a quien está en una cadena de revisión en curso.

**3. Eliminar** (`models/eliminacion.py`). Doble confirmación: marcar que se
entiende, escribir el código del proyecto, y luego el código de 6 cifras que
llega a **todos los usuarios internos** en el correo «ELIMINACIÓN DE PROYECTO»
(quién lo pide y qué proyecto). Vale 15 min, 5 intentos, solo lo confirma quien
lo pidió; se guarda solo su huella. Borra el proyecto en cascada y sus
archivos (`ir.attachment` de sus ítems). El correo es una plantilla más en
Correos, pero **obligatoria**: no se apaga, no pasa por la cola ni por la
pausa, y un reintento no lo reenvía (el código ya no existe). Las últimas
eliminaciones quedan listadas al pie de Proyectos.

- Qué cambia en la base: **solo añade.** Tablas `certum_rev_participante` y
  `certum_rev_eliminacion`; columnas `roles_proveedor`/`roles_cliente` en
  proyectos (por defecto `general`: todo sigue igual que hoy),
  `eliminacion_id` en los envíos y `obligatorio` en las plantillas; la
  plantilla `correo_eliminacion`. No se borra ni se reescribe nada.
- Probado en el Docker local: `-u` limpio; roles propios desde la pantalla
  (3 de 5 dentro, los otros 2 dejan de ver el proyecto y salen de los
  destinatarios); eliminación por consola con 90 internos avisados (envío
  simulado) y desde la pantalla con dos proyectos de prueba; código erróneo,
  error sin servidor de correo y vista previa del correo.
- ⚠️ **Sin desplegar.** `git pull`, `-u certum_revision` y reinicio (DEPLOY.md,
  Parte B).

### 2026-10-26 — Despliegue en producción de la 18.0.2.0.0 (por git)
Primer despliegue desde el repo `ATARX004/fyle360`, clonado en
`/cloudclusters/odoo/fyle_addons` (llave `~/.ssh/id_fyle`, alias `github-fyle`).
Backups previos en `/cloudclusters/odoo/backups/`: base
`certum-global-sac-2026-10-26-1618.dump` (pg_dump) y filestore `.tgz`, más la
copia vieja del módulo y su ZIP.

Lo que se aprendió:
- **El ZIP viejo tapaba el módulo.** `extra_addons/certum_revision.zip` seguía en
  su sitio y Odoo acepta `<módulo>.zip` en una ruta de addons: lo encontraba
  antes que `fyle_addons`, sin manifiesto, y el primer `-u` acabó con `not
  installable, skipped` + `inconsistent states` (el servicio arrancó un par de
  minutos sin el módulo). Moverlo a backups y repetir el `-u` lo resolvió.
  DEPLOY.md A2.6 lo cubre.
- **Producción no estaba en la v0.4**: tenía desplegado el sistema de avisos
  de la entrada (s) —la tabla `certum_rev_aviso_log` y 8 plantillas
  `mail.template`—, aunque este archivo seguía marcándolo «sin desplegar».
  El `-u` retiró ese modelo y con él su tabla: **el historial de avisos
  anterior al 2026-10-26 solo está en el `.dump`** (se extrae con
  `pg_restore -t certum_rev_aviso_log`). Proyectos, documentos, archivos y
  aprobaciones no se tocaron.
- La configuración de correo antigua (`certum_revision.aviso_*`: remitente,
  servidor, CC global, interruptores) **no se migra** a la nueva
  (`certum_revision.correo_*`). Hay que repasarla en Administración → Correos;
  la CC global pasa a ser por cliente.

### 2026-10-25 (x) — Landing /fyle360, menú lateral único e Inicio por rol
**1. Landing pública `/fyle360`** (`controllers/landing.py`, `views/landing.xml`,
`static/src/css/landing.css`, `static/src/js/landing.js`). Misma familia que
`/hygiene360`: página propia, navy de Certum, franjas del isotipo. Dos botones
siempre visibles: *Ir a la plataforma* (al Inicio o al login) y *Contratar el
servicio* (WhatsApp con mensaje escrito). Poco texto y escenas animadas que
corren solo mientras se ven: el anillo del logo como ciclo del documento, los
carriles proveedor/cliente por donde viaja, el panel en vivo con cambio de rol
y la bandeja donde entran los avisos. El WhatsApp y el correo comercial se
cambian en Administración → Ajustes → Contacto comercial.

**2. Un solo menú, lateral y por rol.** Fuera la píldora superior y la barra
propia de Administración (parecía otra web y duplicaba el menú). El menú va
pegado a la izquierda, a toda la altura y en navy, y el contenido usa todo el
ancho. *Administración* es un grupo plegable. Se coloca bajo la cabecera fija
del sitio (la mide `portal_base.js`).

**3. El Inicio es el resumen de cada rol.** Interno: cifras, *Requiere
atención* y próximos a vencer (antes era Administración → Resumen;
`/my/certum/admin` ahora redirige). Cliente: lo que le toca revisar, del más
urgente al menos. Proveedor: lo observado por corregir y lo que falta publicar.
Cada fila abre el documento en su proyecto (`?item=<id>`).

**4. Todo enmarcado.** Cabeceras de página en tarjeta con filete de marca,
bloques como paneles con barra de título, ayudas en recuadro. Proyectos vuelve
a las tarjetas de siempre, con las acciones de Certum al pie.

**De paso:** el avatar por defecto de Odoo (SVG) se pintaba roto.

- Probado en el Docker local: `-u` limpio; interno, cliente y proveedor (usuarios
  del seed) con su menú y su Inicio; landing en escritorio y a 375 px.
- ⚠️ **Sin desplegar.** Solo vistas, controladores y assets: `-u certum_revision`
  y reinicio.

### 2026-10-24 (w) — FYLE 360: nueva marca, panel propio y correos por plantillas
**Versión `18.0.2.0.0`.** Tres cambios grandes y uno de repositorio.

**1. Marca FYLE 360.** El producto deja de llamarse «Certum Global · Revisión».
Nombre visible, navegación, títulos de pestaña, categoría de grupos y correos
dicen FYLE 360; el logo provisional sale de `nuestros_productos/views/logos.xml`
(`static/src/img/fyle360_mark.svg` para la web y `fyle360_logo.png`, renderizado
con Chrome headless, para los correos). **El nombre técnico sigue siendo
`certum_revision`**: está en producción con datos reales.

**2. Fuera el backend: panel de administración propio** (`/my/certum/admin`).
Se borran los menús, las acciones y las vistas de backend (`checklist_views`,
`proceso_views`, `res_partner_views`, `menus`); un `-u` los elimina de la base.
El panel tiene barra de secciones: **Resumen** (lo que pide atención), **Proyectos**
(todos, con filtros; abrir borrador / fuera de plazo), **Empresas** (lo que era
`/my/certum/admin`, ahora en `/empresas`), **Plantillas**, **Correos** y
**Ajustes** (plazos y límites con validación + tareas programadas con
«Ejecutar ahora» y encender/apagar). Base común en `controllers/admin/base.py`
(`AdminBase`, `responder`), marco en `views/admin/layout.xml`, JS en
`static/src/js/admin/admin.js` (pestañas por #ancla, formularios AJAX con
fragmentos y errores por campo, confirmaciones, marcar todos).

**3. Correos con la metodología de `dv_custom_website_slides` (T-30).** Se
sustituye el despachador `certum.rev.aviso` + `mail.template` por
`certum.rev.correo.caso` (9 plantillas editables y activables, texto plano con
variables) y `certum.rev.correo.envio` (cola + historial + clave única). El
cron de la cola corre cada 5 min y al encolar; el diario a las 8:00 de Lima.
Panel con cinco pestañas: Plantillas (activar, asunto, texto, botón, días, vista
previa, prueba), **Copias por cliente** (CC propio de cada empresa cliente, solo
en sus proyectos y una vez por aviso), Historial, **Recuperación** (fallidos,
atascados y «por enviar según las reglas», para cuando el cron falla) y
Remitente (servidor elegido entre los `ir.mail_server` de Odoo, nombre,
contacto, pausa general). Nuevo aviso implementado: **plazo del proyecto por
vencer** (estaba en el catálogo sin enviarse). El segundo revisor de una cadena
ahora recibe su aviso cuando le llega el turno. Un `-u` retira las plantillas
`mail.template` y los crons del sistema anterior.

**4. Diseño (skill frontend-design).** Montserrat autoalojada como única
familia; foco de teclado visible; fuera las entradas escalonadas, el avatar
flotante, los contadores animados y las etiquetas en MAYÚSCULAS; solo se eleva
al pasar el ratón lo que se puede pulsar. El único gesto de la portada es el
anillo de cuatro azules del logo, que se dibuja al entrar.

**De paso:** cada `-u` retira las copias de las vistas de FYLE 360 hechas con el
editor del sitio web (tapaban la vista del módulo: pasó con el Inicio en la base
local).

- Probado en el Docker local (`signa_local`): `-u` limpio, las 9 vistas previas,
  ciclo encolar → diario → envío (falla por SMTP neutralizado, como debe),
  guardado AJAX de plantilla, remitente y copias.
- ⚠️ **Sin desplegar.** Modelos nuevos (`certum_rev_correo_caso`,
  `certum_rev_correo_envio`) y un campo en `res.partner` → `-u certum_revision`.
  En el servidor el módulo pasa a `/cloudclusters/odoo/fyle_addons` (ver
  `FYLE360/DEPLOY.md`): **antes hay que retirar la copia de `extra_addons`**.

### 2026-08-27 (v) — El proyecto se cierra A MANO, no al aprobar el último
Cambio de fondo pedido por negocio. Hasta ahora, aprobar el último documento
obligatorio cerraba el proyecto en el acto, y con `state = 'completado'`
**`puede_reestructurar()` pasa a False**: el proyecto quedaba congelado justo
en el momento en que más se suele querer retocarlo —reordenar carpetas,
renombrar un documento, añadir el que faltó—.

- **`_check_completado()` desaparece.** No se deja sin llamar: se elimina, para
  que no quede código muerto que alguien vuelva a cablear por error. Sus tres
  puntos de llamada (`_aprobar_final`, quitar el último pendiente al
  reorganizar y `_revivir_si_hay_plazo`) ya no cierran nada.
- **`proceso.listo_para_cerrar()`** — todo lo obligatorio aprobado y el
  proyecto todavía activo. Los documentos opcionales pendientes no bloquean; si
  no hay ninguno obligatorio, cuentan todos.
- **`proceso.cerrar_proyecto()`** valida antes: nada sin aprobar (y **dice
  cuáles** faltan, no un genérico), ni proyecto vacío, ni ya cerrado.
- **`proceso.reabrir_proyecto()`** — si cerrar es una decisión, tiene que poder
  deshacerse. Los documentos **no se tocan**: siguen aprobados, solo se levanta
  el candado. Si el plazo venció mientras estaba cerrado, queda `fuera_plazo` en
  el acto y no en la próxima pasada del cron.
- Rutas: `POST /my/proceso/<id>/cerrar` y `…/reabrir` (proveedor e interno).
- Interfaz: aviso en verde **«Todo está aprobado. El proyecto sigue abierto a
  propósito»** con el botón de cerrar, y aviso al reabrir. Cerrar y reabrir
  **recargan la página**: cambian la cabecera, los avisos y si se puede editar,
  así que refrescar solo el árbol dejaría botones que ya no tocan.
- Chip **«Listo para cerrar»** en la tarjeta del proyecto: sin él habría que
  entrar a cada uno para descubrir cuál falta cerrar.
- Verificación: `test_cierre.py`, 20 escenarios, incluido que **ningún** camino
  cierre por su cuenta y que solo `cerrar_proyecto` ponga `completado`.
  `test_revivir.py` invierte su caso 7: revivir ya no debe cerrar.
  **18 suites en verde.**
- ⚠️ **Sin desplegar**: solo lógica, vistas y assets → `-u certum_revision`.

> **Efecto secundario querido:** mientras el proyecto no se cierre, siguen
> disponibles reorganizar, renombrar, añadir documentos, deshacer una
> publicación y borrar archivos sin revisar. Difundir y descargar el ZIP
> funcionan igual antes y después de cerrar.

### 2026-08-26 (u) — Fix: al reorganizar faltaba el botón de editar documento
Reportado en producción. `POST /my/proceso/<id>/item/<iid>/editar` existía
desde la entrada (c) —renombre, descripción y obligatorio— pero **nunca se le
puso botón**: las carpetas tenían su lápiz de renombrar y los documentos solo
mover y eliminar. Renombrar un documento era lo único del panel de
reorganizar que no se podía hacer.

- Botón de editar (lápiz) en cada documento, con modal que **precarga** nombre,
  descripción y la marca de obligatorio. Sin precargar, guardar habría borrado
  la descripción existente.
- La acción entra también en la lista `MIAS` del manejador: sin eso el clic
  habría seguido su curso y abierto el panel del documento en vez del modal.
- El modal aclara que cambiar el nombre **no altera la revisión**: el documento
  conserva estado, archivos e historial.
- `test_estructura.py` gana una comprobación que recorre **todas** las acciones
  de reorganizar y verifica que cada una tenga manejador, botón y entrada en la
  guarda. Era justo el hueco que dejó pasar este fallo. **17 suites en verde.**
- ⚠️ **Sin desplegar**: solo vista y assets → `-u certum_revision`.

### 2026-08-26 (t) — Difusión de documentos aprobados y repositorio
Segunda y tercera tanda del bloque de correos, juntas porque son la misma
función vista desde los dos lados: la **difusión** es el envío, el
**repositorio** es dónde aterriza.

**Decisiones de negocio (confirmadas el 2026-08-25):**
- **Sin correos sueltos.** El destinatario es siempre un **contacto de la
  empresa cliente**; si no tiene usuario de portal, se le **crea** y recibe la
  invitación de Odoo. Así el permiso se apoya en un usuario autenticado y no en
  un enlace reenviable a cualquiera.
- **El correo lleva enlace, no adjunto.** Un adjunto se reenvía, envejece y se
  desincroniza; el enlace entrega siempre la versión vigente y solo a quien
  tiene permiso. Eso convierte al repositorio en el sitio donde de verdad vive
  el documento entregado, no en un extra.

**`certum.rev.difusion`** — modelo del envío y **fuente única del permiso**:
- `difundir(proceso, items, partners, mensaje, autor)` valida en serio, porque
  difundir es dar acceso permanente: solo documentos **aprobados y con
  archivo**, solo **de ese proyecto**, solo contactos **de la empresa cliente**,
  y todos **con correo** —diciendo de quién falta, no fallando al final—.
- `_asegurar_usuarios()` crea el usuario de portal a quien no lo tenga y le
  manda la invitación. Un login repetido no impide la difusión al resto.
- `_avisar()` manda **un correo por persona**, no uno con todos en copia:
  el enlace lleva al repositorio de quien lo abre, y poner a treinta personas
  en el mismo «Para» reparte sus direcciones entre desconocidos.
- **`items_para(partner)`** y **`puede_ver(partner, item)`** son la única
  respuesta a «¿puede ver esto?». La lista y la descarga consultan la misma
  regla, para que no puedan divergir. Además solo sirven lo que **sigue
  aprobado**: una reversión de turno reabre el documento y deja de servirse.

**Rutas nuevas:**
- `GET /my/proceso/<id>/difusion/datos` y `POST …/difusion/enviar` (proveedor
  e interno).
- **`GET /my/repositorio`** — lo recibido, agrupado por proyecto. Es la puerta
  de quien **no participa en la revisión**: no tiene rol y no puede abrir el
  proyecto, pero sí ver lo que le entregaron. Enlace fijo en la navegación.
- `GET /my/repositorio/<item_id>/descargar`, que comprueba el permiso **antes**
  de tocar el archivo: adivinar un id no basta.

**Interfaz:** modal de difusión en la cabecera del proyecto, con las dos
columnas —qué se envía y a quién—, marca de quién **no tiene correo** (no se
puede elegir, y se dice por qué) y de a quién **se le creará usuario**, mensaje
opcional, historial de difusiones y confirmación que cuenta cuántos usuarios se
van a crear.

- Verificación: `test_difusion.py`, 16 escenarios. **17 suites en verde.**
- De paso, `_content_disposition` se muda de `proveedor/proceso.py` a
  `helpers.py`: ahora la usan dos controladores.
- ⚠️ **Sin desplegar**: modelo nuevo `certum.rev.difusion` con sus dos tablas de
  relación y su ACL, una plantilla y una vista → requiere `-u certum_revision`.

### 2026-08-26 (s) — Correos: cimientos, panel de configuración y avisos de plazo
Primera de tres tandas hacia la difusión y el repositorio. La arquitectura
sigue la del módulo `homologacion_portal`, que ya resolvió este problema.

**1. Un único sitio por el que sale todo el correo.**
- **`certum.rev.aviso.config`** — catálogo de eventos y ajustes en
  `ir.config_parameter`: interruptor general y por evento, remitente, servidor
  saliente, copia global y días de preaviso.
- **`certum.rev.aviso`** — el despachador. De él salen, de una vez y para todos
  los avisos: el interruptor, el remitente común, la copia, el registro y —lo
  más importante— que **un fallo de correo nunca tumbe la transición que lo
  disparó**. Publicar tiene que funcionar con el SMTP caído.
- **`certum.rev.aviso.log`** — traza de cada envío, con **índice único PARCIAL**
  en PostgreSQL: un solo `enviado` por evento+registro+clave. Parcial a
  propósito —los fallidos deben poder reintentarse—, y en base de datos y no en
  Python porque entre el `search` y el `create` cabe otra ejecución del cron.
- Los 4 correos que ya existían pasan a delegar aquí. De paso dejan de ir al
  buzón genérico de la empresa: van a las **personas**, y en documentos con
  cadena, a **quien le toca revisar ahora**. Un buzón que nadie mira es la
  forma más común de que un plazo se venza «sin que nadie se enterara».

**2. Panel `/my/certum/admin/correos`** (solo interno): elegir el servidor
saliente entre los ya creados, remitente, copia, activar/desactivar cada aviso,
**enviar una prueba** con datos de un proyecto real y ver los últimos envíos.
- **No** edita host, usuario ni contraseña del SMTP: eso se hace una vez en
  Ajustes → Técnico. Exponer credenciales en una pantalla web es superficie de
  ataque que no compensa.
- Avisa **en grande** cuando no hay `ir.mail_server`: es el fallo más silencioso
  del sistema —los correos se encolan como fallidos y nadie se entera—.

**3. Avisos de plazo, el hueco más importante que quedaba.** Hasta ahora nadie
avisaba *antes* de que venciera una revisión y el documento se auto-aprobaba en
silencio.
- **Recordatorio diario** de pendientes: **un solo correo por proyecto** con la
  tabla de lo que falta, y **ninguno si no hay nada**. Uno por documento en un
  proyecto de cuarenta requisitos es la forma más rápida de que el destinatario
  cree una regla de filtrado.
- **Revisión por vencer** y **corrección por vencer**, a N días configurables.
- Dos crones nuevos y tres plantillas nuevas.

- Verificación: `test_avisos.py`, 19 escenarios. **16 suites en verde.**
- ⚠️ **Sin desplegar**: modelo nuevo `certum.rev.aviso.log` (con su ACL), dos
  crones, tres plantillas y parámetros → requiere `-u certum_revision`.
- Pendiente de las tandas siguientes: **difusión** (elegir contactos del cliente
  y mandarles enlace al documento aprobado) y **repositorio del proyecto** con
  acceso limitado a quienes se difundió.

### 2026-08-25 (r) — Sustituir el documento final; el ZIP deja de ser del cliente
**1. Sustituir el documento de un ítem YA APROBADO.** Última red antes de
entregar: el proveedor detecta que el archivo aprobado tiene una errata o no es
el que debía, y lo cambia por el bueno.
- **`item.reemplazar_final(attachment, partner, motivo)`**: borra el archivo
  anterior, pone el nuevo, **no reabre la revisión** y **no genera versión**.
- Deja **traza** (`final_reemplazado`) con los dos nombres y el motivo. El ítem
  **no se marca** de ninguna forma visible —así se pidió—: el documento se ve
  como cualquier otro aprobado, y el registro de auditoría es el que explica qué
  se aprobó.
- Limpia la foto de deshacer, que apuntaría a un archivo recién borrado.
- Ruta: `POST /my/item/<id>/reemplazar-final` (solo proveedor, solo `aprobado`).
- La interfaz pide confirmación diciendo con todas las letras que el anterior se
  borra y que la revisión no se reabre.

**2. El cliente ya no descarga el ZIP.** El paquete completo es una **entrega
del proveedor**, no un autoservicio; además el cliente ya tiene cada documento
en su panel. La ruta rechaza al cliente y el botón —y su aviso de «aún no hay
aprobados»— dejan de pintarse para él (`puede_zip` en el contexto).

**3. Roadmap:** añadida la **difusión de documentos aprobados** a la tanda de
correos (§5), con las piezas que hacen falta —selector de destinatarios que
admita correos sueltos, qué se envía, plantilla, traza del envío y permisos—.
De paso queda anotado que **configurar el servidor de correo saliente** es
requisito previo de toda esa tanda: sin `ir.mail_server` no sale ni un correo.

- Verificación: `test_final.py`, 12 escenarios. **15 suites en verde.**
- ⚠️ **Sin desplegar**: un valor más en la traza → requiere `-u certum_revision`.

### 2026-08-25 (q) — Limpiar archivos sin revisar; el hilo, con el documento
**1. Borrar archivos de un documento que nadie ha revisado.** Deshacer (entrada
(p)) devuelve la versión anterior, pero si lo que se quiere es dejar la zona
limpia y volver a publicar desde cero, no servía.
- **`item._puede_limpiar()`** y **`item.borrar_documento(attachment)`**. Solo el
  proveedor, y solo mientras **no exista ninguna traza de `aprobado` u
  `observado`**: a partir de ahí los archivos son la prueba de sobre qué se
  decidió y borrarlos dejaría la traza sin respaldo.
- Aquí **sí se borra de verdad**, archivo y registro, al revés que la depuración
  por antigüedad: aquella retira versiones superadas de algo ya revisado y por
  eso conserva el rastro; esto retira un archivo que nunca debió estar y del que
  no hay nada que auditar.
- Al borrar el **último**, el ítem vuelve a `pendiente` con los plazos y la foto
  de deshacer limpios: esa foto apuntaría a un archivo que ya no existe.
- Papelera por fila en la pestaña **Documento**, con confirmación.
  Ruta: `POST /my/item/<id>/borrar-documento`. Traza: **`documento_borrado`**.

**2. El hilo de comentarios se muda a la pestaña Documento.** Se comenta *sobre
el archivo que se está mirando*; tenerlo en otra pestaña obligaba a saltar. La
tercera pestaña pasa a llamarse **Trazabilidad** y queda solo para consulta. El
contador de mensajes se muda con el hilo.

- Verificación: `test_limpiar.py`, 11 escenarios. **14 suites en verde.**
- ⚠️ **Sin desplegar**: un valor más en la traza → `-u certum_revision`.

### 2026-08-25 (p) — Panel en pestañas, deshacer publicación y «proyecto»
**1. El panel lateral se reparte en tres pestañas.** Acumulaba documento,
cadena, plazos, turno vencido, conversación y trazabilidad en una sola columna;
con un expediente real había que desplazar mucho para llegar a lo importante.
- **Documento** (el archivo y qué hacer con él), **Revisión** (cómo se revisa:
  cadena, días, turnos) y **Actividad** (conversación y trazabilidad, con el
  número de comentarios en la propia pestaña).
- `renderPanel` acumula en `T.doc` / `T.flujo` / `T.act`. Cada bloque sigue
  **ejecutándose donde estaba** —comparten variables como `rev`, y reagrupar el
  código las habría dejado sin valor—; solo cambia dónde escribe.
- Solo se ofrecen las pestañas con contenido, y con una sola no se pinta barra.
- La pestaña abierta **sobrevive a una acción**: aprobar no devuelve al usuario
  a la primera. Al abrir otro documento se vuelve a `Documento`.

**2. Deshacer la última publicación.** Subir un archivo encima del vigente lo
reemplaza y reinicia la revisión; si era el archivo equivocado no había vuelta
atrás.
- Ocho campos nuevos en `certum.rev.item` (`undo_*`) guardan, **al publicar**,
  la foto del estado anterior: archivo vigente, estado, paso, ambos plazos y
  las marcas de observación.
- **`_undo_disponible()`** y **`revertir_publicacion()`**. Se bloquea en cuanto
  un revisor **decide sobre la versión nueva**: retirarla después dejaría su
  aprobación apuntando a un archivo que no llegó a ver. `ampliacion`,
  `no_reviso` y `auto_aprobado` **no** cuentan como decisión.
- Es de **un solo paso**: la foto se consume al deshacer.
- El archivo retirado **no se borra**: se queda en el historial como no vigente.
- Ruta: `POST /my/item/<id>/deshacer-publicacion` (solo proveedor).
  Traza: **`publicacion_revertida`**.

**3. Confirmación al publicar sobre una revisión viva.** Si el documento está
`publicado` —no `observado`—, subir otro archivo **reinicia la cadena desde el
primer revisor**. Ahora el panel lo avisa antes, y el botón pide confirmación
diciendo cuántas aprobaciones se pierden.

**4. «Proceso» pasa a llamarse «proyecto» en toda la interfaz.** Y de paso se
unifica: la interfaz decía «proceso» en unos sitios y «expediente» en otros
para lo mismo. **No se tocan** rutas (`/my/procesos`), ids de plantilla, ni el
modelo `certum.rev.proceso`: cambiarlos rompería los enlaces ya enviados por
correo y no aporta nada al usuario.

- Verificación: `test_deshacer.py`, 16 escenarios. `check_js` aprende a detectar
  **cadenas partidas por un salto de línea real** —error de sintaxis en JS, y
  justo lo que producen las herramientas que se comen las barras invertidas al
  editar; me mordió tres veces en esta sesión—, y a reconocer regex tras `=`.
  **13 suites en verde.**
- ⚠️ **Sin desplegar**: ocho columnas nuevas en `certum_rev_item` y un valor más
  en la traza → requiere `-u certum_revision`.

### 2026-08-24 (o) — Dos fallos reportados: plazo ampliado y caja recortada
**1. Un expediente vencido seguía diciendo «Fuera de plazo» tras ampliarle el
plazo.** La tarjeta mostraba a la vez el chip rojo **Fuera de plazo** y el verde
**A tiempo · 14 días**, porque `fase` y `semaforo` se calculan de las fechas
—y se arreglaban solos— mientras `state` no sabía volver: `action_marcar_fuera_plazo`
solo iba en un sentido. Y no era cosmética: `_get_item_error` **congela** un
expediente en `fuera_plazo` —nada salvo comentar—, así que ampliar el plazo no
servía de nada.
- **`proceso._revivir_si_hay_plazo()`** devuelve a `revision` (o a `publicacion`
  si aún no se publicó nada) el expediente cuyo límite vuelve a estar en el
  futuro, y recomprueba el completado por si ya lo estaba todo.
- Se dispara desde **`proceso.write()`** cuando cambian `plazo_dias` o
  `fecha_inicio`, para que **ningún** camino que amplíe el plazo se olvide de
  revivirlo —no solo la aprobación de la solicitud—.
- **`cron_control_plazo` pasa a ser simétrico**: marca los vencidos y revive los
  que dejaron de estarlo. Así se sanan solos los expedientes que ya quedaron
  atascados en producción, sin migración ni intervención manual.

**2. Al observar, el botón «Enviar observación» quedaba recortado por abajo.**
`.sr-observe-box.is-open` animaba `max-height` a un número fijo (220 px) con
`overflow: hidden`. Al adjuntar el archivo marcado, la zona de subida crecía y
el botón se salía: se veía solo una franja naranja.
- **`.sr-desplegable`** (en `portal_base.css`) sustituye la altura adivinada por
  una rejilla de una fila que va de `0fr` a `1fr`, con `min-height: 0` en el
  envoltorio interior. El navegador anima hasta la **altura real** del
  contenido, sea la que sea, así que no puede volver a recortarse aunque el
  contenido crezca.
- Se aplica también a **`.sr-solicitar-box`**, que tenía el mismo fallo latente
  con su tope de 280 px.
- Respeta `prefers-reduced-motion`.
- Verificación: `test_revivir.py`, 12 escenarios (revive / no revive por días
  insuficientes / el último día cuenta / no toca otros estados / sin fecha de
  inicio / recomprueba completado / el disparo desde `write` / la ruta de la
  solicitud / el desplegable sin alturas fijas / cron simétrico).
  **12 suites en verde.**
- ⚠️ **Sin desplegar**: solo código y assets; **no hay columnas nuevas**, pero
  requiere `-u certum_revision` por vistas y assets.

### 2026-08-24 (n) — Devolver un turno vencido (reversión del `no_reviso`)
Cuando un revisor deja vencer su ventana, el sistema registra `no_reviso` y
sigue adelante; si era el último, el ítem se auto-aprueba. Eso está bien como
regla general —el plazo tiene que significar algo—, pero a veces la omisión es
un accidente y quedarse con una aprobación que nadie miró no le sirve a nadie.

- **`item.revertir_no_reviso(dias, partner)`** devuelve el turno al revisor
  saltado con los días que se le den, recortados por el plazo general del
  expediente. Si el ítem se había auto-aprobado, se reabre; y si esa aprobación
  había cerrado el expediente, el expediente vuelve a `revision`.
- **`item._reversion_disponible()`** decide si se ofrece. El límite es firme:
  si **después** de la omisión alguien **aprobó u observó**, no se revierte —
  deshacerlo anularía la decisión de una persona, que es cosa muy distinta de
  reabrir un turno que nadie usó—. Devuelve siempre el motivo del bloqueo, para
  explicarlo en pantalla en vez de esconder el botón.
- Con **varias omisiones seguidas** vuelve a la **primera**: son todas del
  sistema, nadie decidió nada, y devolver el turno al primero deja que la cadena
  fluya otra vez por todos ellos. Una aprobación real **corta** la tanda.
- **`item._paso_de_traza()`** localiza el paso de una traza: por persona en
  cadenas nominales, por **nivel** en cadenas por capas (donde el `no_reviso`
  lo firma el usuario del cron, no el revisor).
- Lo ejecuta el **PROVEEDOR** (y Certum interno, que supervisa). Puede sonar
  raro, pero es al revés de lo que parece: la omisión le **beneficia** —el
  documento se aprueba solo—, así que revertirla es renunciar a una aprobación
  que ya tenía. Nadie abusa de un botón que juega en su contra.
- Ruta nueva: `POST /my/item/<id>/revertir` (`dias`).
- Traza: acción **`revertido`** ('Turno devuelto al revisor'), que anota a quién,
  qué paso, cuántos días y si hubo que reabrir el documento.
- **Correo nuevo** `template_item_turno_devuelto` al cliente, con el aviso de
  que esta vez el plazo es firme. Sin él la reversión sería inútil: quien dejó
  pasar su plazo una vez volvería a dejarlo pasar si nadie se lo dice. Es el
  primer ladrillo del bloque de notificaciones del §5.
- La fecha del correo se formatea con **`item._limite_revision_lima()`**, no con
  `strftime` crudo: en UTC habría mostrado el día siguiente, porque la ventana
  cierra a las 23:59 de Lima = 04:59 UTC del día de después.
- Verificación: `test_reversion.py`, 16 escenarios (se ofrece / se bloquea por
  aprobación posterior / por observación posterior, último paso auto-aprobado,
  omisiones encadenadas, aprobación que corta la tanda, cadena por niveles,
  fuera de plazo, recorte al tope, sin margen, días inválidos, y que un caso
  bloqueado no se cuele por la API). **11 suites en verde.**
- ⚠️ **Sin desplegar**: un valor más en la selección de `certum_rev_aprobacion` y
  una plantilla de correo nueva → requiere `-u certum_revision`.

### 2026-08-21 (m) — Al corregir, la revisión vuelve a QUIEN OBSERVÓ
Hasta ahora una observación mandaba el documento al principio de la cadena:
`marcar_publicado` fijaba `revision_paso = 1` en **toda** publicación, incluidas
las correcciones. Con tres revisores, que el tercero observara obligaba a los dos
primeros a aprobar otra vez algo que ya habían dado por bueno —y en cadenas
largas el documento podía no llegar nunca al final dentro del plazo—.

- Dos campos nuevos en `certum.rev.item`: **`revision_paso_observado`** (dónde
  quedó la revisión) y **`observado_por_id`** (quién observó). `marcar_observado`
  los guarda; `marcar_publicado` los consume y los limpia.
- **`_paso_reanudar(cadena)`** decide dónde retomar. Busca primero por
  **PERSONA** y no por posición, porque el proveedor puede editar la cadena
  mientras el ítem está observado y el número antiguo apuntaría a otro revisor.
  Si no la encuentra —cadena por niveles, o alguien a quien sacaron— usa la
  posición guardada, recortada a la cadena vigente. Sin marcas → paso 1, como
  siempre.
- Al retomar, `_set_ventana_actual` recalcula desde cero, así que **ese revisor
  recupera sus días completos** contados desde la corrección, no lo que le
  quedaba. Es lo pedido: "volverá a tener los días necesarios".
- Los pasos anteriores **conservan su aprobación** y no vuelven a decidir. Al
  aprobar el que observó, sigue al resto de la cadena con normalidad.
- `item_avance`: el estado **observado** deja de valer 0. Ahora vale
  `revision_paso_observado - 1`, así que la barra se queda en 1/3 en vez de caer
  a 0/3 y rebotar a 1/3 al republicar, que daba la impresión de trabajo perdido.
  El título añade *"al corregir vuelve al revisor N, no al principio"*.
- Traza: acción nueva **`reanudado`** ('Revisión reanudada tras corregir'), que
  se registra al publicar una corrección que retoma en un paso > 1, indicando el
  paso y cuántas aprobaciones previas siguen valiendo. Con etiqueta y color
  propios en el historial —de paso, `ampliacion` también los tenía sin poner y
  salía con su código crudo—.
- El panel del documento avisa al proveedor **antes** de subir la corrección a
  quién volverá y con cuántos pasos por delante.
- Verificación: `test_reanudar.py`, 14 escenarios (persona sobre posición,
  cadena reordenada, revisor retirado, recorte de rango, niveles, primera
  publicación, modo cualquiera, observador ajeno, barra que no retrocede,
  días recuperados, paso anterior que no se reabre). `test_avance.py` ampliado.
  **10 suites en verde.**
- ⚠️ **Sin desplegar**: dos columnas nuevas en `certum_rev_item` y un valor más
  en la selección de `certum_rev_aprobacion` → requiere `-u certum_revision`.

### 2026-08-21 (l) — El proveedor elige A QUIÉN le da los días extra
Complemento de (k). Conceder días "al documento" era demasiado grueso: en una
cadena de tres revisores, los días caían siempre en el turno vivo, así que
**premiaban a quien casualmente estuviera revisando** y no a quien de verdad
necesitaba tiempo. Ahora el proveedor nombra al destinatario.

- `certum.rev.ampliacion` gana dos campos: **`beneficiario_id`** (a quién van
  los días; vacío = al turno actual, sea quien sea) y **`aplicada`** (si ya
  entraron en una ventana o siguen esperando).
- `conceder(dias, partner, beneficiario=None)` distingue tres casos:
  - beneficiario **con el turno actual**, o ninguno → se amplía la ventana viva
    en el acto, como hasta ahora;
  - beneficiario de un paso **posterior** → los días quedan **reservados**. No
    se toca la ventana de otro: la del paso futuro todavía no existe, así que
    reservar es lo único que tiene sentido;
  - beneficiario de un paso **ya pasado**, o alguien **fuera de la cadena** →
    `UserError`. No se regalan días a quien ya no puede usarlos.
- `item._paso_de(partner)` devuelve la posición (1-based) de una persona en la
  cadena, o 0 si no está. En cadenas por NIVEL nadie es localizable por nombre,
  así que ahí solo cabe "el turno actual" y el selector no se ofrece.
- `item._consumir_dias_reservados(paso)` suma las reservas de ese paso al
  calcular su ventana y las marca `aplicada`, de modo que **no se cobran dos
  veces**. Se integra en `_set_ventana_actual`:
  `dias = self._dias_por_paso(paso, n) + self._consumir_dias_reservados(paso)`.
- Al **resolver una solicitud concreta**, los días van a **quien la pidió**
  (`data-benef` = `solicitante_id`), no al turno actual. Es lo que el revisor
  pidió y lo que el proveedor cree estar concediendo.
- Interfaz: selector *"Para…"* en el bloque **Días de revisión** con "Quien
  tenga el turno ahora" + cada revisor con su número de paso y una marca en el
  que tiene el turno. Las filas muestran a quién fueron los días y una etiqueta
  **reservados** mientras no se hayan aplicado. El aviso de resultado lo dicta
  el servidor (`reservada` en la respuesta), no una suposición del navegador.
- Verificación: `test_beneficiario.py`, 10 escenarios sobre el código real
  (localizar el paso, reserva que llega solo a su revisor y una sola vez, varias
  reservas que se suman, rechazadas/aplicadas que no vuelven a contar, turno
  actual, turno posterior, turno pasado, persona ajena, sin beneficiario).
- De paso, dos suites que habían quedado obsoletas tras cambios posteriores
  vuelven a verde: `test_avance.py` (esperaba la barra por fases, no la de
  revisores de la entrada (g)) y `test_zip.py` (el mock de carpeta no tenía
  `ruta`). Y `check_js.py` ya entiende los literales regex —marcaba 8
  desbalances falsos en archivos correctos— y cubre también `estructura.js`.
  **9 suites en verde.**
- ⚠️ **Sin desplegar**: añade dos columnas a `certum_rev_ampliacion`
  (`beneficiario_id`, `aplicada`), así que requiere `-u certum_revision`.


### 2026-08-19 (k) — Los días de revisión los concede el PROVEEDOR
Corrección de la autoridad respecto de la entrada (j), a petición de negocio y
con buen motivo: si el propio cliente concediera los días, se estaría dando
tiempo a sí mismo sin contrapeso y **el plazo dejaría de significar nada** —la
aprobación automática no llegaría nunca—.

- `POST /my/item/<id>/ampliacion/conceder` y `/my/ampliacion/<id>/rechazar`
  pasan a exigir **`ROL_PROVEEDOR`** (antes: cliente + nivel 1).
- **Pedir** sigue siendo del cliente: cualquier revisor, desde el panel del
  documento, mientras esté en revisión.
- El panel expone `puede_pedir` solo al cliente y `puede_conceder` solo al
  proveedor; ambos —y el interno— ven la lista, que antes solo veía el cliente.
- La traza registra la concesión del **lado del proveedor** (`lado='proveedor'`).
- Queda coherente con el resto: es el proveedor quien fija los días de revisión
  al publicar, así que también es quien los amplía. Las **dos** ampliaciones del
  sistema las decide él.
- Manuales actualizados con el porqué, y con el aviso al cliente de que el reloj
  sigue corriendo mientras el proveedor no responda.

### 2026-08-19 (j) — Ampliar los días de revisión de un documento
Segunda ampliación del sistema, que **no debe confundirse** con la del plazo
general: aquella la pide el cliente y la concede el proveedor; esta es
**interna del cliente** y afecta a un solo documento.

| Qué se amplía | Quién pide | Quién concede |
|---|---|---|
| Plazo general del expediente | Cliente (sube por jerarquía) | **Proveedor** |
| Días de revisión de un ítem | Cualquier revisor del cliente | **Nivel 1 del cliente** |

- **Modelo `certum.rev.ampliacion`** con los dos caminos previstos: el revisor
  **pide** y el nivel 1 resuelve, o el nivel 1 **concede directamente** sin que
  nadie haya pedido (queda registrado igual, con solicitante vacío).
- **`item.ampliar_revision(dias, partner)`** empuja `fecha_limite_revision` del
  **paso actual**. No se filtra a los pasos siguientes: al avanzar, la ventana
  se recalcula con el reparto normal.
- **El tope sigue siendo el plazo general.** Si al recortar no se gana ni un
  minuto, se avisa en lugar de fingir que amplió — el mensaje dice que hay que
  ampliar antes el expediente.
- Cada solicitud y cada concesión quedan en la **trazabilidad** del ítem: nueva
  acción `ampliacion` en `certum.rev.aprobacion`.
- Endpoints: `POST /my/item/<id>/ampliacion/{pedir,conceder}` y
  `POST /my/ampliacion/<id>/rechazar`. Interfaz en el panel del documento.
- Probado con el código real: 7 escenarios, incluido el recorte al tope, la
  falta de margen, días inválidos y un ítem que no está en revisión.
- ⚠️ Sin desplegar: añade la tabla `certum_rev_ampliacion`.

### 2026-08-19 (i) — Fix: el selector de carpeta destino salía sin nombres
En el modal de nuevo documento (y en los de mover), la lista de carpetas
mostraba los radios y los iconos **pero no los nombres**, con una barra de
desplazamiento horizontal de más.

- La lista era una rejilla de radios con sangría por nivel, y su legibilidad
  dependía de un equilibrio frágil entre `flex`, `min-width` y desbordes.
- **Sustituida por un `<select>` con la ruta completa en cada opción**, que es
  exactamente el patrón que el editor de plantillas lleva usando en producción
  sin problemas. Se pierde la sangría visual y se gana fiabilidad; además
  funciona mejor en móvil, donde el desplegable es nativo.
- Retirado el CSS de la lista de radios y el manejador que resaltaba la opción.

### 2026-08-19 (h) — Dos fallos de interfaz + formatos de vista
**Fallos corregidos (ambos míos, del despliegue anterior):**
- **[ALTA] El modal salía transparente.** Se colgaba de `<body>`, y las
  variables de color y sombra (`--sr-surface`, `--sr-shadow-lift`…) están
  declaradas en `.sr-app`: fuera de ese contenedor no resuelven y la tarjeta se
  quedaba sin fondo. Ahora se cuelga de `.sr-app`.
- **[ALTA] Las flechas de plegar carpetas dejaban de responder.** Las escuchas
  se enganchaban a `#srItems`, pero el refresco AJAX **sustituye ese nodo
  entero**, así que el nodo nuevo se quedaba sin escuchas. Bastaba un refresco
  —y el de preferencias ocurre al cargar— para que el plegado muriera. Ahora se
  delega desde `document`. Misma causa saneada en el botón *Plegar todo*, que
  conservaba una referencia al nodo viejo.

**Formatos de vista** (`FORMATOS`, selector propio junto al de orden):
- **Carpetas** (el directorio actual), **Tarjetas** (ficha por documento con su
  ruta) y **Tabla** (densa, columnas Documento/Ubicación/Estado/Revisiones).
- El filtrado se desacopla del formato: los tres marcan sus elementos con
  `.sr-fitem`, así los filtros por estado y *Me toca revisar* funcionan igual en
  los tres. En los formatos planos no hay carpetas, así que el plegado heredado
  se ignora (si no, la lista salía vacía sin motivo aparente).
- Formato y orden se recuerdan entre visitas y se aplican por AJAX.
- Pendiente de esta tanda: **tablero por estado** y **arrastrar y soltar**.
  Decidido para el arrastre (2026-08-19): **escritorio de primera**, tablet
  como extra, y si en táctil no queda fino se **restringe a esos dispositivos
  el modo manual** (selector de destino), que ya funciona en todas partes.

### 2026-08-19 (g) — La barra mide revisiones, no entrega
Cambio de criterio pedido por negocio. `item_avance()` pasa a contar
**aprobaciones conseguidas sobre el total de revisores**:

| Estado | Cadena de 3 | Sin cadena |
|---|---|---|
| Pendiente | 0/3 · 0 % | 0/1 · 0 % |
| Publicado, paso 1 | 0/3 · 0 % | 0/1 · 0 % |
| Publicado, paso 2 | 1/3 · 33 % | — |
| Publicado, paso 3 | 2/3 · 67 % | — |
| Observado | 0/3 · 0 % | 0/1 · 0 % |
| Aprobado | 3/3 · 100 % | 1/1 · 100 % |

- **Publicar ya NO cuenta como avance.** En la versión anterior sumaba un hito
  (con 3 revisores había 4 tramos) para que un documento entregado no marcara
  0 %. Queda revertido: la barra mide revisión, y entregar no es revisar.
- Modo «cualquiera aprueba» se trata como **un único visto bueno** (0/1 → 1/1),
  así la escala es la misma en los dos modos.
- Al **observar**, el contador vuelve a 0: el ciclo se reinicia y las
  aprobaciones previas dejan de contar.
- La etiqueta de la fila pasa a ser el contador corto (`1/3`) y el texto largo
  («2 de 3 revisores han aprobado») va al tooltip y a la cabecera del panel.
  La columna se estrecha de 96 px a 44 px con cifras tabulares.
- Verificado con el código real: los 6 estados de una cadena de 3, los 3 del
  modo cualquiera, y los porcentajes 0/33/67/100.

### 2026-08-19 (f) — Fix del filtro + orden natural de carpetas
- **[ALTA] Bug reportado:** con un filtro activo (p. ej. *Me toca revisar*), al
  pulsar una carpeta **desaparecía todo y quedaba la pantalla en blanco**, sin
  forma de recuperarlo salvo recargando. Causa: la lista de "ramas con
  contenido" se construía solo con los documentos **ya visibles**, así que al
  plegar una carpeta esta se quedaba sin contenido registrado y **se ocultaba a
  sí misma**, llevándose el control para volver a abrirla. Ahora se calcula en
  tres pasos: qué casa el filtro (sin mirar el plegado), qué documentos se ven,
  y qué carpetas son relevantes. El mensaje de "nada coincide" pasa a depender
  del filtro, no del plegado.
- **Orden natural de carpetas y documentos**, seleccionable entre *orden de la
  plantilla* y *por nombre*. `_clave_natural()` rellena con ceros cada tramo de
  dígitos y compara como texto corrido, de modo que "2." va antes que "10." y,
  además, **"1. Legal" queda antes que "1.1 Laboral"** (la carpeta madre antes
  que su hija). Trocear el texto por tramos —lo primero que probé— fallaba
  justo en ese caso: al partir ".1 Laboral" el tramo quedaba en "." y, siendo
  prefijo de ". Legal", colaba la subcarpeta delante.
- El criterio se recuerda entre visitas y se aplica **por AJAX**, sin recargar.
- `refrescarArbol()` se muda a `portal_base.js`, que es el dueño del
  directorio; `estructura.js` lo delega en vez de tener su propia copia.

### 2026-08-19 (e) — Fix: bloques duplicados en el detalle + aviso al pie
- **[ALTA] La vista del detalle tenía 5 bloques duplicados** (`srProcGestion`,
  `srFiltros`, `srDiffBox`, `srEditBar`, `srPartData`): la tarjeta de política,
  la barra de filtros y la de edición salían **dos veces**, con ids repetidos.
  Causa: en la edición del aviso de diferencias calculé el corte final ANTES
  del inicial, así que el tramo intermedio se reinyectó. XML seguía siendo
  válido —los ids repetidos no lo invalidan— y mi verificación cruzada no
  miraba duplicados; ahora sí se comprueba. 172 líneas eliminadas.
- **Aviso de plantilla reubicado:** durante el proceso va **al pie**, tras el
  árbol, para no estorbar mientras se trabaja; sube al **principio** solo cuando
  el expediente ya terminó (`completado` o `fuera_plazo`), que es cuando toca
  decidir si se guarda la plantilla.

### 2026-08-19 (d) — Reorganizar: modal propio y sin recargas
Sustituye los `prompt()`/`confirm()` del navegador —que eran un provisional
feo— por un modal del sistema, y elimina las recargas de página.

- **Modal propio** reutilizando los estilos que ya existían (`sr-modal`).
  Mover se hace con un **selector de carpetas con la jerarquía visible** y
  sangría por nivel, no escribiendo un número. Cada modal lleva una nota que
  explica la consecuencia: al mover, que la revisión **no se altera**; al
  borrar una carpeta, que los documentos **no se pierden**.
- **Todo por AJAX.** El árbol se extrajo a su propia plantilla
  (`sr_proceso_arbol`) y el nuevo `GET /my/proceso/<id>/arbol` lo re-renderiza
  **en el servidor**. El JS sustituye el nodo y actualiza contadores, anillo de
  avance, contador del ZIP y aviso de diferencias. Nada de HTML duplicado en el
  navegador: la plantilla sigue siendo la única fuente.
- **`_contexto_arbol()`** es ahora el único sitio donde se arma ese contexto; lo
  comparten el render de la página y el refresco, así no pueden divergir.
- `window.srPortal` expone `refrescarDirectorio` e `initRings`: tras sustituir
  el árbol hay que **reaplicar filtro y plegado**, o el usuario pierde de vista
  dónde estaba.
- El aviso de diferencias se renderiza siempre (oculto si no hay), para poder
  aparecer tras reorganizar sin recargar. El resumen lo arma el servidor
  (`_resumen_diff`), no el JS.

### 2026-08-19 (c) — Reestructurar un expediente en curso
Se puede reorganizar un expediente ya iniciado **sin tocar la revisión en
curso**, porque el expediente tiene su propia copia de la estructura y el curso
vive entero en el ítem: `carpeta_id` solo dice dónde se muestra.

- **Nuevo `controllers/proveedor/estructura.py`** con 8 endpoints bajo
  `/my/proceso/<id>/…`: crear/renombrar/mover/eliminar carpetas y
  crear/editar/mover/eliminar documentos. Todos exigen **proveedor** y
  expediente **activo** (`puede_reestructurar()`); en *completado* se bloquea a
  propósito, para no dejarlo cerrado y con algo pendiente a la vez.
- **Borrar está restringido:** un documento solo se quita si sigue `pendiente`
  y **sin archivos, comentarios ni trazabilidad**; borrar una carpeta arrastra
  sus subcarpetas pero **los documentos no se pierden** (quedan sin carpeta).
  Al quitar el último pendiente se reevalúa `_check_completado()`.
- **`origen_id`** en `certum.rev.carpeta` y `certum.rev.item`, grabado al copiar
  la plantilla. Permite que `diff_estructura()` distinga de verdad lo añadido de
  lo movido, renombrado o quitado, en vez de adivinar por el nombre.
- **`crear_plantilla_desde_proceso()`**: guarda la estructura actual como una
  plantilla **NUEVA**; la original queda intacta y el proveedor decide después
  si la retira. Se ofrece solo cuando `diff_estructura()` encuentra diferencias,
  con el resumen de qué cambió.
- **Modo edición** en la vista de directorio: botón *Reorganizar*, acciones por
  fila y un aviso permanente de que mover no altera la revisión. Destino por
  selector (no arrastrar y soltar): robusto e igual en móvil.
- Probado con el código real: los **15 campos que guardan el curso** no dependen
  de `carpeta_id`; mover un documento escribe **solo** `carpeta_id` y mover una
  carpeta **solo** `parent_id`; el diff detecta los 4 tipos de cambio y sale
  vacío cuando no hay ninguno.
- ⚠️ Sin desplegar: añade dos columnas (`origen_id`) en tablas del módulo.
  **Los expedientes ya abiertos las tendrán vacías**, así que su diff los dará
  como "todo nuevo" hasta que se abra un expediente nuevo. No afecta al flujo.

### 2026-08-19 (b) — Directorio, filtros y barra de avance
Tres mejoras de la pantalla de detalle del expediente, pedidas por negocio.

- **Vista de directorio.** El grid de tarjetas se sustituye por un árbol tipo
  explorador: carpetas anidadas con sangría y guía vertical, plegables una a una
  o con **Plegar todo**. `_arbol_nodos()` aplana el árbol en orden de lectura;
  dentro de cada carpeta van primero **sus** documentos y luego sus subcarpetas,
  que para un expediente de requisitos se lee mejor. Los sueltos, al final.
  El plegado se resuelve por prefijo de `parent_path` (`1/` contiene `1/2/`).
- **Filtros por estado** (todos / pendientes / publicados / observados /
  aprobados) con contador cada uno, y **"Me toca revisar"** para el cliente, que
  usa `item_es_mio()` → `puede_revisar()`: respeta la cadena, así que no muestra
  lo que es turno de otro. Estado y plegado se aplican **combinados**; una
  carpeta sin documentos visibles bajo el filtro activo se oculta.
- **Barra de avance por documento** (`item_avance()`), en la fila del directorio
  y en el panel del ítem. Publicar **cuenta como un hito más**: con 3 revisores
  hay 4 tramos, así un documento entregado nunca marca 0 % y el 100 % queda
  reservado a la aprobación final. Tonos: gris sin publicar, azul en revisión,
  ámbar en corrección, verde aprobado.
- Probado con el código real: los 7 estados del avance (incluido paso fuera de
  rango, acotado a [0,100]) y el orden del árbol con sueltos al final.
- Manuales actualizados (cliente §6, interno §5).
- ⚠️ Sin desplegar: solo requiere `-u` por cambios de vistas y assets; **no hay
  columnas nuevas**.

### 2026-08-19 — v0.4 en producción
Desplegada y verificada la tanda completa del 18-19 de agosto (commits
`2f3a0c6` → `89cdb5d`). El usuario confirma que el sistema funciona
correctamente. Contenido acumulado en este despliegue:
- Descarga del expediente en **ZIP** y **depuración** de versiones superadas.
- **Participantes designados** por proceso (tercer modo de revisión).
- **Carpetas anidadas** en plantillas y expedientes.
- La **cadena por ítem** pasa a decidirla el proveedor.
- **Reutilización de plantillas** (guard anti-duplicado recalibrado) + campo
  `referencia`.
- **Zona horaria normalizada a Lima** (horas mostradas y tope de plazos).
- Arreglos del seed (`=ilike`) e índice booleano retirado.

**`certum_revision/README.md` reescrito**: estaba desfasado desde julio —
describía el modelo de plazos viejo, la puesta en marcha por backend, un grupo
que ya no se usa y una tabla de parámetros con claves inexistentes
(`dias_duracion`) y valores erróneos. Ahora refleja el código real: 32 rutas,
8 parámetros, 4 crons, quién decide qué y las convenciones de zona horaria y
de cadena de revisión.

### 2026-08-18 (f) — Zona horaria normalizada a Lima
`models/tz_utils.py` pasa a ser la **fuente única** de zona horaria. Regla del
proyecto: Odoo guarda los `Datetime` en **UTC** (convención del ORM, intacta) y
**todo lo que ve o decide el negocio va en hora de Lima**; la conversión ocurre
solo en ese módulo. Se corrigieron dos fallos reales:

- **[ALTA] Las horas se mostraban en UTC.** `_fmt_dt()` hacía `strftime` directo
  sobre el valor almacenado, así que **cada fecha-hora del portal salía 5 horas
  adelantada**: publicación, revisión, límites, comentarios, trazas y depuración.
  Ahora pasa por `fmt_lima()`.
- **[ALTA] El plazo del proceso moría 5 horas antes.** `_tope_proceso()` combinaba
  la fecha límite con `datetime.max.time()` y lo guardaba tal cual; 23:59:59 UTC
  son las **18:59 de Lima**. Ahora `fin_de_dia_utc()` calcula el fin del día
  *limeño* y lo convierte a UTC.
- **Helpers duplicados eliminados:** `helpers.py` tenía su propia copia de
  `_now_lima`/`_today_lima` (y de `pytz`) que además **nunca se usaba**. Ahora
  importa de `tz_utils`.
- **Respaldo sin `pytz` corregido:** antes devolvía `datetime.now()`, la hora del
  *servidor*, lo que habría dado el día equivocado entre las 19:00 y medianoche.
  Ahora usa desfase fijo **UTC-5**, exacto porque Perú no aplica horario de
  verano desde 1994.
- **Usuarios del seed con `tz='America/Lima'`**: las pantallas nativas de Odoo
  (no las del módulo) pintan en la zona del usuario; sin ella muestran UTC.
- Nueva API en `tz_utils`: `a_lima()`, `a_utc()`, `fmt_lima()`, `fin_de_dia_utc()`.
- Probado con el módulo real: 7 escenarios (incluido el cruce de medianoche, en
  que 02:00 UTC del día 19 son las 21:00 del 18 en Lima) y una comprobación
  cruzada contra la base de zonas horarias del sistema: **1095 días sin ninguna
  desviación de UTC-5**, y el respaldo fijo da el mismo resultado que `zoneinfo`.

### 2026-08-18 (e) — Las plantillas se reutilizan (guard anti-duplicado mal calibrado)
**Defecto de producto:** una plantilla solo servía para UN proceso al año, que es
lo contrario de para qué existe. `_guard_duplicado` tenía dos fallos:
1. **Ignoraba el cliente por completo** → un proveedor no podía usar la misma
   plantilla con dos clientes distintos. Ese es el caso central del producto.
2. **Bloqueaba por año entero** → tampoco permitía dos expedientes del mismo
   cliente en el mismo año.

- La regla pasa a ser un anti-duplicado **real**: se bloquea solo si coinciden
  las cinco cosas que definen el expediente —proveedor, cliente, plantilla,
  fecha de inicio **y referencia**—, que es el resultado del doble clic en
  "Iniciar proceso". Todo lo demás se permite.
- **Campo nuevo `proceso.referencia`** (Char opcional, con tracking): etiqueta
  libre —obra, sede, contrato, periodo— para distinguir expedientes hechos con
  la misma plantilla y el mismo cliente. Es además la salida cuando de verdad
  hacen falta dos el mismo día: basta con etiquetarlos distinto.
- La comparación de referencia ignora mayúsculas y espacios sobrantes.
- Se muestra en la tarjeta del listado y en la cabecera del detalle; se pide
  (opcional) en el modal de iniciar proceso, que ahora dice explícitamente que
  la plantilla se puede reutilizar.
- El mensaje de error dejó de ser un muro: explica cómo proceder (cambiar la
  fecha o poner una referencia).
- Probado sin servidor con el código real del modelo: 7 escenarios (otro
  cliente mismo día, mismo cliente otra fecha del mismo año, doble clic,
  referencias distintas, misma referencia con otro formato). 5 procesos
  legítimos sobre una sola plantilla.

### 2026-08-18 (d) — La cadena por ítem pasa al proveedor
Cambio de autoridad pedido por negocio. La revisión queda configurada en **dos
alturas con dos responsables distintos**:

| Qué | Quién decide | Alcance |
|---|---|---|
| Modo del expediente (cualquiera / niveles / participantes) | Nivel 1 del **cliente** | Todo el proceso |
| Cadena de un requisito | El **proveedor** | Un ítem; manda sobre el modo |

- `POST /my/item/<id>/revisores` ahora exige `ROL_PROVEEDOR` (antes: cliente +
  nivel 1). Se mantiene la restricción de estado (`pendiente`/`observado`).
- `item_panel_data`: `puede_config` pasa a `rol == ROL_PROVEEDOR`; los contactos
  del cliente se exponen también al proveedor (los necesita para designar) y el
  cliente conserva la vista **en solo lectura** de la cadena que rige su ítem.
- Los revisores designados siguen siendo **personas del cliente**: lo que decide
  el proveedor es el *enrutamiento*, no la autoridad.
- `set_participantes` (nivel de proceso) **no cambia**: sigue siendo del nivel 1
  del cliente.
- Textos del panel y manuales actualizados (cliente §12, interno §11 con la tabla
  de las dos alturas y la FAQ correspondiente).

### 2026-08-18 (c) — Carpetas anidadas (árbol de requisitos)
Las plantillas y los expedientes pasan de una lista plana de carpetas a un
**árbol de profundidad arbitraria** (tope 5 niveles), con ítems en cualquier nivel.

- **`certum.rev.checklist.folder` y `certum.rev.carpeta`** ganan `parent_id`,
  `child_ids` y `_parent_store`, más `ruta` (breadcrumb) y `nivel` calculados.
  `MAX_PROFUNDIDAD = 5` acota la longitud de las rutas del ZIP y la legibilidad
  del editor. `@api.constrains` cubre recursión, mezcla entre plantillas/procesos
  y exceso de profundidad.
- **`carpeta.raiz_id`** (ancestro de primer nivel) y estadísticas que **suman las
  subcarpetas**: una carpeta padre refleja el avance de todo lo que cuelga.
- **`_copiar_checklist`** copia el árbol ordenando por profundidad, para que la
  carpeta padre exista siempre antes que la hija.
- **ZIP anidado:** `_ruta_zip()` reproduce el árbol como subdirectorios reales,
  saneando **cada tramo por separado** para que un nombre con `/` no pueda
  inventar un nivel. El orden del paquete pasa a ser el de la ruta (orden de
  lectura), con los ítems sin carpeta al final.
- **Editor de plantillas:** botón de subcarpeta por carpeta (oculto al llegar al
  tope), sangría por nivel, contador de subcarpetas, aviso al borrar de que
  arrastra las hijas, y el desplegable de carpeta del ítem muestra la **ruta
  completa** en vez de sangría (los navegadores colapsan los espacios de un
  `<option>`).
- **Detalle del expediente:** las pestañas son las carpetas **raíz** y filtran
  también lo que cuelga de sus subcarpetas (`data-carpeta` = raíz); cada tarjeta
  de ítem muestra su ruta completa.
- Probado sin servidor: 6 escenarios (ruta/nivel/raíz a 3 niveles, ZIP anidado,
  nombre con `/`, orden padres-antes-que-hijas en la copia, orden de lectura,
  sueltos al final).
- Manuales actualizados (cliente §6 y glosarios de ambos).
- ⚠️ Sin desplegar: requiere `-u` (columnas nuevas en `certum_rev_checklist_folder`
  y `certum_rev_carpeta`, ambas del módulo).  
  **[Superado: desplegado el 2026-08-19.]**

### 2026-08-18 (b) — Participantes designados por proceso
Cierra el hueco detectado en la revisión de jerarquías: antes solo se podían
nombrar personas concretas **ítem por ítem**; a nivel de proceso solo existían
capas **por nivel**, donde cualquier persona con ese nivel podía aprobar.

- **`certum.rev.revisor` ahora sirve a dos alturas:** `item_id` (excepción de un
  requisito) o `proceso_id` (participantes del expediente), nunca ambos
  (`@api.constrains`). Misma estructura, misma lógica de pasos.
- **Tercer modo `personas`** en `revision_modo`. La política pasa a ser una
  elección explícita entre *cualquiera* / *por niveles* / *participantes*, en vez
  de ajustes que se pisan.
- **Precedencia de `_cadena()`:** cadena propia del ítem → participantes del
  proceso → capas por nivel → cualquiera.
- **Congelado al publicar** (`_congelar_cadena_proceso`): al publicar un ítem se
  copian sobre él los participantes del proceso. Así la lista se puede editar en
  cualquier momento sin alterar revisiones en curso, y queda registrado en el
  propio documento por quiénes debía pasar.
- **`item.revisores_propios`** distingue una excepción real de una cadena
  heredada; el panel del ítem expone `origen_cadena` (propia / heredada /
  proceso / niveles / cualquiera) para que se vea de dónde salen los permisos.
- Vaciar la lista estando en modo `personas` devuelve el proceso a `cualquiera`,
  para no dejarlo en un estado ambiguo. El endpoint rechaza el modo sin
  participantes.
- Nuevo endpoint `POST /my/proceso/<id>/revisores`; editor de cadena en la
  tarjeta de política, con la máxima autoridad marcada.
- Probado sin servidor: 6 escenarios de precedencia y reparto de días, más el
  escape del JSON embebido (nombre con `</script>`).
- Manuales actualizados: cliente §11 (tres modos) y §12 (excepciones por
  requisito); interno §11 con los tres modos y la trampa de las capas sin
  contactos en ese nivel.
- ⚠️ Sin desplegar: requiere `-u` (columna nueva en `certum_rev_revisor` y en
  `certum_rev_item`). Ambas tablas son del módulo, sin riesgo de bloqueo.  
  **[Superado: desplegado el 2026-08-19.]**

### 2026-08-18 — Despliegue de la v0.3 en producción
Primer despliegue del bloque de julio + la descarga en ZIP. **Completado sin errores.**
- **Incidencia de despliegue (resuelta):** el `-u` falló dos veces con
  `LockNotAvailable: canceling statement due to lock timeout` al añadir la columna
  `certum_purgado` a `ir_attachment`. Causa: **9 sesiones `odoo-bin shell`
  olvidadas desde el 4-17 de agosto**, dos de ellas `idle in transaction` con 13
  días de antigüedad, reteniendo el bloqueo sobre esa tabla. Detener el servicio
  no bastaba: el bloqueante no era el servidor web. Se resolvió con
  `pkill -9 -f "odoo-bin shell -d certum-global-sac"`.
  - **Regla nueva:** salir SIEMPRE del `odoo shell` con `Ctrl-D`, nunca cerrando
    la ventana. Antes de cualquier `-u`, comprobar
    `ps aux | grep "odoo-bin shell" | grep -v grep`.
  - Diagnóstico útil (el usuario de BD es **`admin`**, no `postgres` ni `odoo`):
    `psql -U admin -d certum-global-sac -c "SELECT l.pid, a.state, age(clock_timestamp(), a.state_change) FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid JOIN pg_class c ON c.oid=l.relation WHERE c.relname='ir_attachment' AND l.pid<>pg_backend_pid();"`
- **Demo sembrada:** `REV/2026/0005`, plantilla `PLT/0003`, 10 ítems, 5 usuarios
  portal, plazo 2026-08-18 → 2026-09-17.
- **Defecto detectado en el seed:** esta instalación **normaliza los nombres de
  contacto a MAYÚSCULAS** al guardarlos, así que la búsqueda por igualdad exacta
  no reencontraba lo ya creado y una segunda ejecución habría duplicado las
  empresas. Corregido con `=ilike` en empresas, personas y plantilla.
- **Quitado `index=True`** de `certum_purgado`: índice booleano de baja
  selectividad que solo encarecía las escrituras de `ir_attachment`.
- ⚠️ Ambos cambios están en el ZIP local pero **no en el servidor**: entran en el
  próximo `-u`. Ninguno afecta al QA en curso.  
  **[Superado: desplegado el 2026-08-19.]**

### 2026-08-17 (d) — Descarga en ZIP + depuración de versiones
Función nueva pedida por negocio, con sus reglas fijadas explícitamente.
- **Paquete ZIP del expediente** — `GET /my/proceso/<id>/descargar`. Incluye
  **solo los ítems aprobados** y, de cada uno, **solo el archivo vigente** (nunca
  dos versiones del mismo documento). Lo descargan **ambas partes** y el interno;
  **se permite en expedientes fuera de plazo y completados**. Estructura por
  carpetas del proceso, numerada, más un `LEEME.txt`. Tope configurable
  (`certum_revision.max_zip_mb`, 200 MB) para no agotar memoria.
- **Depuración a los 10 días** (`certum_revision.dias_purga_versiones`) — cron
  diario `cron_purgar_versiones`. Borra el **contenido** de las versiones
  superadas y de los adjuntos de marcas del cliente; **el archivo vigente nunca
  se depura**. Se conserva el registro: `ir.attachment` sobrevive con nombre,
  fecha y autor, marcado con `certum_purgado` / `certum_purgado_fecha`.
- **Advertencia permanente** en la cabecera del proceso y en el panel del ítem,
  pidiendo conservar copia local. El `LEEME.txt` del ZIP repite el aviso.
- Descarga individual de un adjunto ya depurado → redirige con aviso, no 500.
- Probado sin servidor con un ORM simulado: 8 escenarios (colisión de nombres,
  ítem sin contenido, nombres con `/` y `<script>`, sin carpeta, tope excedido).
  Dos defectos corregidos antes de commitear: `REV/2026/0001` quedaba como
  `REV20260001` (los separadores ahora pasan a guion) y la numeración del ZIP
  saltaba números al omitir un archivo.
- ⚠️ **No ejecutado en Odoo**, igual que el resto de la v0.3.  
  **[Superado: desplegado el 2026-08-19.]**

### 2026-08-17 (c) — Manuales de usuario (PDF)
Dos manuales en `manuales/`, en lenguaje no técnico, con la marca Certum Global:
- **`Manual_Administrador_Certum_Interno.pdf`** (22 pág., 16 secciones) — para el
  personal interno: los tres roles, la puesta en marcha de una empresa paso a paso,
  el Panel de Administración, el modelo completo de plazos, las tres formas de
  revisar, las solicitudes de ampliación, trazabilidad y un diagnóstico de los
  problemas frecuentes.
- **`Manual_Cliente.pdf`** (22 pág., 17 secciones) — para las empresas que revisan:
  cómo revisar, aprobar y observar; los plazos y la **aprobación automática**;
  cómo organizar la revisión interna (niveles, capas, cadenas a medida); cómo
  pedir más tiempo; preguntas frecuentes y glosario.
- Escritos contra el comportamiento **real del código** (endpoints, máquina de
  estados del ítem, reparto de días, enrutamiento de solicitudes), no contra los
  planes. Las etiquetas de estado usan los colores reales del portal.
- Fuentes reproducibles en `manuales/fuentes/` (reportlab). Ver su README.
- Ampliados el 2026-08-17 (d) con la descarga en ZIP y la depuración: sección
  nueva en cada manual (cliente §16, interno §15), FAQ y glosario.
- No se documenta el manual del proveedor: no fue solicitado.

### 2026-08-17 (b) — Datos de demostración para el QA
- **`certum_revision/tools/seed_demo.py`**: siembra proveedor + cliente con
  personal por niveles, 5 usuarios portal, plantilla SSOMA de 10 ítems y un
  proceso abierto. Idempotente y con purga (`CERTUM_DEMO_PURGE=1`). Va **dentro
  del ZIP** para no tener que subirlo aparte. Documentado en §2.
- Se descartó `data/demo.xml`: la clave `'demo'` del manifest solo carga en bases
  creadas con datos de demostración, y `certum-global-sac` es de producción.
- Validado sin servidor: sintaxis OK, **todos los campos usados existen** en los
  modelos, y un dry-run con un ORM simulado corre las dos pasadas (creación e
  idempotencia) sin excepciones.
- Corregido antes de liberar: la purga borraba las compañías `[DEMO]` pero dejaba
  huérfanos los contactos-persona (no llevan el prefijo); ahora arrastra
  `child_ids`. También se quitó un carácter no-ASCII de un `print` (riesgo de
  `UnicodeEncodeError` según el locale del servidor).
- ZIP regenerado: 60 entradas, sin backslashes.

### 2026-08-17 — Revisión de estado (sin cambios de código)
Repaso completo tras ~1 mes sin actividad. **No se tocó código.** Hallazgos:
- Working tree limpio; último commit `7c6971c` del **2026-07-14**. Las fechas del
  changelog de julio son las de redacción; las de git van unos días después.
- `certum_revision.zip` **coincide byte a byte** con el código fuente → desplegable
  tal cual, sin regenerar.
- Python compila y los 12 XML del módulo son bien formados; sin TODO/FIXME abiertos.
- Manifest, ACL y crons **sí incluyen** todo lo de la v0.3 (`gestion.css/js`,
  `certum.rev.revisor`, `cron_auto_aprobar_revision`) → no falta cableado.
- **El único bloqueo real es que la v0.3 nunca se desplegó ni se probó.** Movido a
  §5 → P0 con guion de QA.
- Roadmap saneado: "Notificaciones por correo" ya estaba hecho desde el 2026-07-04.

### 2026-07-06 (b) — Fix editor + reparto de días + cadena de revisores a medida
- **Fix editor de plantillas:** volví a pasar `ch_data` al contexto (la
  cabecera lo usa); la auditoría lo había dejado solo como `ch_data_json`.
- **Reparto de días (feature 3):** `dias_revision` se distribuye entre los pasos
  de la cadena; el remanente (días enteros) va a la mayor jerarquía. Cada paso
  tiene su ventana; si no revisa a tiempo el cron registra `no_reviso` (traza) y
  pasa al siguiente; el último sin revisar → auto-aprobado.
- **Cadena de revisores a medida (feature 2):** `certum.rev.revisor` (One2many en
  el ítem). El **nivel 1 del cliente** define, desde el panel lateral del ítem
  (solo si pendiente/observado), una cadena de personas específicas que
  reemplaza la de niveles (la última = máxima autoridad). Lógica de cadena
  UNIFICADA por "pasos" (`revision_paso`): niveles o personas usan el mismo
  reparto de días, auto-avance y trazabilidad. Endpoint
  `POST /my/item/<id>/revisores`.

### 2026-07-06 — Jerarquía, aprobación por capas, ventana de revisión y solicitudes
Gran bloque (cliente y proveedor con niveles; política por proceso; un plazo
para toda la revisión). Define el modelo de plazos antes aparcado.
- **Jerarquía (A):** `res.partner.certum_nivel` (1 = máximo). En Roles, botón
  **Personal/niveles** por empresa (modal AJAX) para asignar nivel a cada
  contacto. `certum.rev.aprobacion` = traza inmutable (quién, nivel, acción,
  fecha/hora). Política por proceso: `revision_modo` (cualquiera/secuencial) +
  `revision_capas`, la fija el **nivel 1 del cliente** en el detalle del proceso.
  En secuencial la aprobación sube capa a capa hasta el nivel 1.
- **Nota + subida del cliente (B):** en el drawer, al observar el cliente ve
  la nota "si dejaste comentarios en el documento, súbelo por aquí" y puede
  adjuntar su archivo (queda en `attachment_cliente_ids`).
- **Ventana de revisión (C):** el proveedor fija los días de revisión en la
  **primera** publicación (`item.dias_revision`, `fecha_limite_revision`). Cron
  `cron_auto_aprobar_revision` (cada 6h) auto-aprueba si vence sin revisar. Al
  observar, +3 días de corrección (`fecha_limite_correccion`,
  `certum_revision.dias_correccion`). Todo acotado al plazo del proceso.
- **Solicitud de plazo (D):** `certum.rev.solicitud`. El cliente pide días; si
  es nivel 1 va directo al proveedor, si no sube autorizándose por niveles.
  El proveedor aprueba (amplía `plazo_dias`) o rechaza.
- Nuevos endpoints: admin `personal/<id>` + `nivel`; cliente `politica`,
  `solicitar-plazo`, `solicitud/<id>/autorizar`; proveedor `solicitud/<id>/decidir`
  + `dias_revision` en publicar. Nuevo JS/CSS `proceso/gestion`.
- ⚠️ **Pendiente de probar en Odoo** (cambio grande, no ejecutado).  
  **[Superado: desplegado el 2026-08-19.]**

### 2026-07-05 (c) — Auditoría interna (multi-agente) + correcciones
Auditoría de 4 dimensiones (acceso/IDOR, ACL/rules, entrada/XSS/uploads,
consistencia) con verificación adversarial. 7 hallazgos confirmados, 2
refutados. **No hubo vulnerabilidades explotables desde portal** (sin IDOR: el
control por propiedad/rol y `_es_interno()` sostienen el aislamiento). Corregido:
- **[ALTA] Editor de plantillas roto:** `<script>` embebía un dict Python con
  `t-esc` → JSON inválido → toda plantilla con contenido cargaba vacía. Ahora el
  controller serializa con `json.dumps` + escape de `<`→`<` y la vista usa
  `t-out` de un `Markup`. (builder.py / builder.xml)
- **[MEDIA] Guard anti-duplicado evadible** cuando el proceso no tenía fecha:
  `_guard_duplicado` usa hoy como referencia y `action_abrir` fija `fecha_inicio`
  antes de validar. (proceso.py)
- **[BAJA] plazo_dias sin cota** → OverflowError al render (self-DoS): cota
  [0,3650] en los 3 endpoints (`_plazo`) + `@api.constrains`. (builder.py/proceso.py)
- **[BAJA] admin_set_clientes** ahora exige que el destino tenga rol proveedor.
- **[BAJA] _get_rol** ya no cae al rol del contacto individual (solo empresa).
- **[BAJA] mimetype** del upload derivado del nombre saneado, no del header.
- **[BAJA] record rule checklist**: documentado que el aislamiento se apoya en
  sudo()+validación (defensa en profundidad, no explotable).

### 2026-07-05 (b) — Logo adaptable + clientes por proveedor
- **Logo adaptable:** el avatar usa `object-fit: contain` + padding + fondo
  blanco (clase `sr-avatar--photo`) para que los logos **rectangulares** se
  vean completos sin recortarse (los cuadrados ya funcionaban). Iniciales
  conservan el fondo de color.
- **Clientes seleccionables por proveedor:** nuevo M2M
  `res.partner.certum_cliente_ids`. En el panel de Roles, cada proveedor tiene
  un botón "Clientes" que abre un modal para marcar qué compañías cliente puede
  elegir. Endpoint `POST /my/certum/admin/clientes`. Al iniciar un proceso, el
  proveedor solo ve/valida sus clientes asignados (el interno sobre plantilla
  global ve todos). Helper `_clientes_seleccionables`.

### 2026-07-05 — UI: avatares de empresa, iconos y animaciones
- **Foto de empresa (Contactos):** componente QWeb reutilizable `sr_avatar`
  (`views/portal_common.xml`) que muestra `res.partner.image_128` embebido en
  base64 (con fallback a iniciales + color por hue del id). Integrado en: hero
  del hub (empresa propia, con flotación suave), tarjetas de proceso (otra
  parte), cabecera de proceso (proveedor→cliente) y lista del admin.
- **Iconos:** añadidos al sprite `i-search, i-building, i-user, i-plus,
  i-pencil, i-trash, i-image, i-bell, i-sparkle`; búsqueda del admin usa lupa.
- **Animaciones suaves:** hover de avatares (escala + sombra), flotación del
  avatar del hero, micro-interacciones de iconos en botones/segmentos, chips.
  Todo respeta `prefers-reduced-motion`.

### 2026-07-04 (tarde) — Paneles web (multi-agente)
- **Construidos 3 dominios nuevos** (workflow de 6 agentes: build + verify por
  dominio), integrados a mano (manifest/__init__/menús/notificaciones):
  - **Admin (Certum interno)** — `GET /my/certum/admin` + `POST /my/certum/admin/rol`.
    Lista de compañías con KPIs por rol y asignación de proveedor/cliente vía
    AJAX. Archivos: `controllers/admin/`, `views/admin/panel.xml`
    (`certum_revision.admin_roles`), `static/src/{css,js}/admin/`.
  - **Proveedor · plantillas** — constructor de carpetas + ítems (crear/editar/
    eliminar inline) y **iniciar proceso** (elige cliente + inicio + plazo →
    crea proceso y `action_abrir`). Rutas `/my/plantillas`, `/my/plantilla/<id>`
    y sus POST. Templates `plantillas_list` / `plantilla_editor`.
  - **Notificaciones** — 3 `mail.template` (publicado→cliente, aprobado/
    observado→proveedor) + `models/notify.py`; cableadas en las transiciones de
    `item` (`marcar_publicado/aprobado/observado`). El comentario se crea antes
    de la transición para que el correo de "observado" incluya la observación.
- **Base para el modelo "proveedor dueño":** `checklist.proveedor_id` +
  `plazo_dias`; helpers `_es_interno`, `_checklist_or_none`, `_mis_checklists`,
  `_companias_por_rol`, `_rol_de_partner`; record rules portal para plantillas;
  secuencia `PLT/####`. Hub y nav enlazan a los paneles web (no al backend).

### 2026-07-04
- **Dirección de producto acordada (giro a "todo en la web"):**
  - Toda la operación y configuración vive en **paneles web propios**; el backend
    de Odoo queda como motor invisible (no como interfaz).
  - **Certum interno** → panel "Administrador general": lista de compañías/
    contactos y asignación de roles (proveedor/cliente) desde la web.
  - **Proveedor** → crea sus plantillas (carpetas + ítems) y sus tiempos; sube
    documentos. (Decisión: el dueño de la plantilla es el proveedor.)
  - **Cliente** → descarga, comenta, aprueba/observa con su propio plazo.
  - **Notificaciones** al publicar y al revisar.
  - Pendiente de construir; ver §5 Roadmap (Fase "Web-first").
- **Modelo de plazo cambiado a "inicio + N días" (hacia adelante):** el proceso
  ya no deriva las fases de la fecha de vencimiento (eso causaba "Plazo vencido"
  al poner un vencimiento cercano). Ahora `fecha_limite = fecha_inicio +
  plazo_dias`. Campos nuevos `fecha_inicio` y `plazo_dias`; `fecha_vencimiento`
  pasa a ser informativa. `plazo_dias` default en `certum_revision.plazo_dias`
  (30). Semáforo urgente/crítico ajustados a 7/3 días.
- **Acceso interno vía `base.group_user` (infalible):** la implicación de grupo
  no bastaba (dependía de propagación + refrescar sesión). Se concede el ACL de
  todos los modelos y el menú raíz directamente a `base.group_user` (Empleado).
  Como todo usuario interno YA es empleado, el acceso funciona de inmediato tras
  `-u`, sin re-login ni asignar grupos. El grupo `group_certum_rev_interno` y su
  implicación se mantienen (semántica + record rule), pero ya no son requisito
  para acceder. Portal sigue restringido a `base.group_portal` + record rules.
  Los usuarios internos ven todos los procesos (sin record rule que los limite).

### 2026-07-03
- **ZIP con separadores POSIX:** el ZIP se generaba con PowerShell
  `Compress-Archive`, que usa backslashes `\` → warning en Linux y riesgo de
  extracción rota. Nuevo `tools_make_zip.py` empaqueta con `/`. Prohibido usar
  `Compress-Archive` para este módulo.
- **Acceso backend para TODO usuario interno (definitivo):** `base.group_user`
  (Empleado) ahora **implica** `group_certum_rev_interno`. Cada usuario interno
  de Odoo recibe el permiso automáticamente al instalar **y en cada `-u`**, y
  Odoo lo propaga a los usuarios ya existentes. Reemplaza al `post_init_hook`
  (que solo corría al instalar, no en upgrade) y a la asignación manual del
  grupo — ambos eliminados. Gestión 100% web, sin shell.
  - Tras el `-u`, si la sesión no refresca los permisos: **cerrar sesión y
    volver a entrar**.
  - Para restringir a un subconjunto en el futuro: quitar la implicación en
    `security.xml` y asignar el grupo por usuario desde Ajustes → Usuarios.
- **Fix "Error de estilo" (2 causas encontradas):**
  1. Subida incompleta de subcarpetas de `static/` → empaquetar el módulo en ZIP
     y desplegar completo (archivos locales verificados íntegros).
  2. **Permisos tras descomprimir:** las subcarpetas quedaban sin lectura para el
     usuario de Odoo ("could not get content for …"; file manager sin acceso a
     `static/`). Solución: `chmod 755` carpetas + `644` archivos tras cada
     descompresión. Documentado como paso obligatorio del deploy por ZIP.
- **Hub del usuario interno:** antes quedaba vacío (sin salida). Añadido panel de
  atajos al backend (Procesos / Checklists), KPIs globales y listado de todos los
  procesos con enlace "Gestionar". (`controllers/hub/home.py`,
  `views/hub/portal_home.xml`, `css/hub/home.css`)
- Creada esta documentación (`PROJECT.md`) e inicializado el repositorio git.

### 2026-07-01
- **Rebrand completo SIGNA → Certum Global:** carpeta `certum_revision/`, modelos
  `certum.rev.*`, ruta hub `/my/certum`, campo `rol_en_certum`, parámetros
  `certum_revision.*`, textos y grupos. Sin rastros de "signa" en el código.
- **Paleta corporativa Certum Global** aplicada a todo el diseño (tokens CSS +
  gradiente del hero navy→azul).
- **Construcción inicial v0.1** del Módulo 1: modelos (checklist maestro, proceso,
  carpeta, ítem, comentario, res.partner), controllers por dominio
  (hub/proveedor/cliente) con helpers, seguridad (grupos + ACL + record rules),
  secuencias, parámetros de configuración, crons de apertura y control de plazo,
  vistas backend, portal completo (hub, listados, detalle con tabs + drawer AJAX)
  y sistema de diseño CSS/JS. Colores semánticos de estado mantenidos.

---

## 5. Tareas futuras (roadmap)

**P0 — cerrado el 2026-08-19.** La v0.4 está desplegada y verificada en
producción, así que el guion de QA que ocupaba este apartado ya se cumplió y se
retiró. Para repetirlo en una tanda futura, el recorrido mínimo es:

1. Publicar un ítem fijando los días de revisión; aprobar y observar desde el
   cliente; comprobar que al republicar **no** se vuelven a pedir los días.
2. Fijar el modo de revisión (niveles y participantes) y verificar que solo
   actúa quien toca, y en orden.
3. Solicitar una ampliación de plazo desde un nivel bajo y seguirla hasta el
   proveedor.
4. Descargar el ZIP como ambas partes: carpetas anidadas, numeración sin huecos
   y una sola versión por ítem.
5. Bajar `dias_purga_versiones` a 0, forzar el cron y comprobar que la versión
   superada queda **sin archivo** conservando el registro, y que la vigente
   sigue descargándose.
6. Reutilizar una plantilla con dos clientes y comprobar que solo se bloquea el
   duplicado exacto.
7. Contrastar una hora mostrada con el reloj de Lima.

**Pendiente menor:** los usuarios internos que ya existían necesitan
`América/Lima` en su perfil de Odoo para que las pantallas nativas del backend
no muestren UTC (las del módulo ya salen bien en cualquier caso).

**Módulo 1 — próxima tanda: notificaciones automáticas por correo**
Hoy solo hay **3 correos**, todos disparados por transiciones del ítem
(`models/notify.py` + `data/mail_templates.xml`): publicado→cliente,
aprobado→proveedor, observado→proveedor. Falta todo lo demás:
- [ ] **Bienvenida al abrir un proceso** — al cliente y al proveedor: qué
      expediente es, cuántos requisitos, plazo límite y enlace directo.
      Disparo en `proceso.action_abrir()`.
- [ ] **Aviso de archivo subido** más completo (hoy existe, revisar contenido):
      incluir carpeta/ruta del requisito y quién debe revisar según la cadena.
- [ ] **Recordatorio de pendientes por revisar** — cron diario al cliente con el
      resumen de ítems `publicado` cuya ventana sigue abierta. Es el hueco más
      importante: hoy el sistema **no avisa antes de que venza** una revisión, y
      el ítem se auto-aprueba en silencio.
- [ ] **Aviso previo al vencimiento** (p. ej. a 2 días) de la ventana de revisión
      y del plazo de corrección del proveedor.
- [ ] **Aviso de auto-aprobación consumada** — hoy **no genera correo**; conviene
      que ambas partes se enteren de que un documento se aprobó por vencimiento.
- [ ] **Aviso al proveedor cuando le toca corregir** un observado que se acerca a
      su límite de corrección.
- [ ] **Resumen semanal** al nivel 1 de cada parte con el avance del expediente.
- [x] ~~**Difusión de documentos aprobados**~~ — hecho el 2026-08-26, entrada
      (t). Con dos ajustes respecto de lo previsto, decididos con negocio:
      **sin correos sueltos** (el destinatario es un contacto del cliente y se
      le crea usuario de portal si no lo tiene) y **enlace en vez de adjunto**
      (el ZIP no se usa aquí; el documento se sirve desde el repositorio).
- [x] ~~**Repositorio del proyecto**~~ — hecho el 2026-08-26, entrada (t):
      `/my/repositorio`, con acceso limitado a quien recibió cada documento.
- [ ] Transversal: **preferencias de notificación** por empresa/persona y un
      parámetro para silenciar todo en pruebas; agrupar en un solo correo para no
      saturar cuando se publican 10 ítems seguidos.
- [ ] Transversal: **configurar el servidor de correo saliente**. Sin un
      `ir.mail_server`, en autohospedado (Cloud Clusters) **ningún** correo sale:
      se quedan en la cola como fallidos. OdooBot **no** sustituye a esto —es
      mensajería interna del backend—. Una sola cuenta de Certum
      (`smtp.office365.com:587`, STARTTLS, con `email_from` fijo a la cuenta
      autenticada, que es lo que ya hacen las plantillas) sirve para todo el
      sistema y los clientes no configuran nada.

**Módulo 1 — cercano:**
- [x] ~~**Datos demo**~~ — hecho el 2026-08-17 como
      `certum_revision/tools/seed_demo.py` (ver §2). Se descartó `data/demo.xml`
      porque no carga en bases de producción.
- [ ] **Reportes de avance** (PDF/Excel) por proceso y consolidado.
- [ ] **Panel de avance** interno (dashboard) más completo.
- [ ] Icono de la app (`static/description/icon.png`) con la marca Certum Global.
      La carpeta `static/description/` **no existe todavía**.
- [ ] **Manual del proveedor** (falta el tercer rol): armar plantillas, iniciar
      procesos, publicar y fijar los días de revisión, corregir observaciones y
      decidir solicitudes de plazo. Reutiliza `manuales/fuentes/manual_kit.py`.
- [ ] **Documents**: decidir si se integra `documents.document` o se mantiene
      `ir.attachment` (actual). Aditivo, no bloqueante.
- [x] ~~**Notificaciones por correo** al publicar/observar/aprobar~~ — hecho el
      2026-07-04 (3 `mail.template` + `models/notify.py`).

**Módulo 1 — decisiones abiertas (§15 del plan):**
- [ ] ¿El "cliente" es usuario portal externo o interno revisando a su nombre?
- [ ] ¿Apertura de procesos: solo cron, solo manual, o ambos? (hoy: ambos)
- [ ] ¿Un único checklist maestro o varios por sector/tipo de proveedor?
- [ ] ¿"Listo en carpeta" = estado aprobado, o además copiar a
      `documents.document`?

**Módulo 2 — futuro:**
- [ ] Generador de documentos que alimente los ítems del checklist vía
      `doc_template_code`. Ver `PLAN_modulo_generador_documentos.md`.

---

## 6. Documentos de referencia

- `PLAN_modulo1_revision_aceptacion.md` — plan detallado del Módulo 1.
- `PLAN_modulo_generador_documentos.md` — plan del Módulo 2.
- `certum_revision/README.md` — puesta en marcha y rutas del módulo.
- `manuales/` — manuales de usuario en PDF (administrador interno y cliente);
  fuentes reproducibles en `manuales/fuentes/`.
- `odoo-portal-architecture/` — receta de arquitectura (skill) que rige el proyecto.
- Brandbook: `../CERTUM/BRANDBOOK - CG.pdf`.
