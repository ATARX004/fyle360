# FYLE 360 — Revisión documental (`certum_revision`)

Odoo 18 Enterprise · modelos 100 % en código (sin Studio) · portal y panel de
administración propios. Producto de Certum Global.

> **Nombre:** desde la 18.0.2.0.0 el producto se llama **FYLE 360**. El nombre
> técnico sigue siendo `certum_revision` (y los modelos `certum.rev.*`): está
> instalado en producción con datos reales, y renombrarlo obligaría a migrarlos
> y rompería los enlaces de los correos ya enviados.

> **Fuente de verdad operativa:** `../PROJECT.md` (estado, despliegue, changelog
> y roadmap). Este README describe el módulo; los `PLAN_*.md` son documentos
> históricos y **están desactualizados**.

## Qué hace

El **proveedor** arma sus plantillas de requisitos (árbol de carpetas + ítems) e
inicia procesos con sus clientes. Publica el documento de cada ítem; el
**cliente** lo descarga y lo aprueba u observa dentro de un plazo. Todo bajo
control de tiempos, con trazabilidad permanente y avisos por correo.

Toda la operación vive en **paneles web propios**; el backend de Odoo queda como
motor, no como interfaz: el módulo **no tiene menús ni vistas de backend**.

**Navegación:** un único menú lateral (`sr_menu` en `views/portal_common.xml`,
datos en `certum.rev.proceso.fyle_menu()`), pegado al borde izquierdo como en
VALIDA y en el panel del e-learning. Sus entradas salen del rol **global** del
usuario; para el personal de Certum, *Administración* es un grupo plegable con
Empresas y roles, Plantillas, Proyectos, Correos y Ajustes. Cada página puede
abrir un documento concreto con `?item=<id>` en la URL del proyecto.

## Instalación

1. Copiar `certum_revision/` a la ruta de addons y actualizar la lista de apps.
2. Instalar **Certum Global — Flujo de Revisión y Aceptación**.
3. No hace falta asignar grupos: el ACL y el menú van directos a
   `base.group_user`, así que **todo usuario interno tiene acceso** tras el `-u`.

> Para actualizar una instalación existente usar **`-u`**, nunca `-i`. Antes de
> lanzarlo, comprobar que no queden consolas abiertas:
> `ps aux | grep "odoo-bin shell" | grep -v grep` — una sesión olvidada retiene
> `ir_attachment` y hace fallar el `ALTER TABLE`. Detalle en `../PROJECT.md` §2.

## Puesta en marcha

1. **Certum interno** entra a `/my/certum/admin/empresas` y, por cada empresa: asigna el
   **rol** (proveedor / cliente), vincula al proveedor **qué clientes** puede
   elegir, y registra los **niveles** del personal (1 = máxima autoridad).
2. **Proveedor** entra a `/my/plantillas`, construye su plantilla y pulsa
   *Iniciar proceso* (cliente + fecha de inicio + plazo + referencia opcional).
3. **Cliente** entra a `/my/revisiones` y revisa.

Datos de prueba listos para usar: `tools/seed_demo.py` (ver `../PROJECT.md` §2).

## Roles y quién decide qué

| Configuración | Quién la fija |
|---|---|
| Rol de empresa, clientes por proveedor, niveles del personal | Certum interno |
| Modo de revisión del expediente (cualquiera / niveles / participantes) | Nivel 1 del **cliente** |
| Cadena de revisores de **un requisito** | El **proveedor** |
| Días de revisión de cada documento | El **proveedor**, en la primera publicación |
| Ampliación del plazo general del expediente | La pide el cliente, la concede el proveedor |
| Ampliación de los días de revisión de **un documento** | La pide un revisor, la concede el **proveedor**, que además elige **a quién** se los da |
| Dónde se retoma la revisión tras corregir | Nadie: el sistema vuelve a **quien observó**, con sus días otra vez. Las aprobaciones previas se conservan |
| Devolver un turno que venció sin revisar | El **proveedor** (o Certum interno). Se bloquea si alguien posterior ya aprobó u observó |
| Deshacer la última publicación | El **proveedor**. Se bloquea en cuanto un revisor decide sobre la versión nueva |
| Borrar archivos publicados | El **proveedor**, solo mientras nadie haya aprobado ni observado el documento |
| Sustituir el documento final ya aprobado | El **proveedor**. No reabre la revisión ni genera versión, pero deja traza |
| A quién se difunde un documento aprobado | El **proveedor** (o Certum interno), entre los **contactos de la empresa cliente**. Sin correos sueltos |
| Qué avisa el sistema y desde dónde | Certum interno, en `/my/certum/admin/correos` |
| Quién recibe copia de los avisos de un cliente | Certum interno, en Correos → Copias por cliente |
| Cerrar el proyecto | El **proveedor** (o Certum interno), a mano. Aprobarlo todo **no** lo cierra |

## Rutas portal (contrato estable — no cambiarlas al refactorizar)

### Hub y administración
| Ruta | Actor | Descripción |
|---|---|---|
| `GET /fyle360` | público | Landing comercial: «Ir a la plataforma» y «Contratar el servicio» (WhatsApp) |
| `GET /my/certum` | todos | Inicio: el resumen de cada rol (interno: lo que pide atención; cliente: lo que tiene por revisar; proveedor: lo que tiene por corregir y publicar) |
| `GET /my/certum/admin` | interno | Lleva al Inicio (el resumen ya no es pantalla aparte) |
| `GET /my/certum/admin/proyectos` | interno | Todos los proyectos, con filtros (sustituye a la lista del backend) |
| `POST /my/certum/admin/proyecto/<id>/abrir` · `/fuera-plazo` | interno | Abre un borrador · lo marca fuera de plazo |
| `GET /my/certum/admin/empresas` | interno | Rol de cada compañía, clientes y niveles (antes en `/my/certum/admin`) |
| `GET /my/certum/admin/ajustes` | interno | Plazos y límites; tareas programadas |
| `POST /my/certum/admin/ajustes/guardar` | interno | Guarda plazos y límites |
| `POST /my/certum/admin/ajustes/contacto` | interno | WhatsApp y correo comercial de la landing |
| `POST /my/certum/admin/ajustes/cron/<id>/ejecutar` · `/activar` | interno | Lanza una tarea ya · la enciende o apaga |
| `POST /my/certum/admin/rol` | interno | Asigna rol a una compañía |
| `POST /my/certum/admin/clientes` | interno | Clientes elegibles por proveedor |
| `GET /my/certum/admin/personal/<company_id>` | interno | Contactos y niveles (JSON) |
| `POST /my/certum/admin/nivel` | interno | Fija el nivel de un contacto |

### Plantillas (proveedor / interno)
| Ruta | Descripción |
|---|---|
| `GET /my/plantillas` · `POST /my/plantilla/crear` | Listado y alta |
| `GET /my/plantilla/<cid>` · `POST /my/plantilla/<cid>/editar` | Editor y cabecera |
| `POST /my/plantilla/<cid>/carpeta/{crear,<fid>/editar,<fid>/eliminar}` | Árbol de carpetas |
| `POST /my/plantilla/<cid>/item/{crear,<iid>/editar,<iid>/eliminar}` | Ítems |
| `POST /my/plantilla/<cid>/iniciar` | Crea el proceso y lo abre |

### Proceso
| Ruta | Actor | Descripción |
|---|---|---|
| `GET /my/procesos` | proveedor | Sus procesos |
| `GET /my/revisiones` | cliente | Procesos de sus proveedores |
| `GET /my/proceso/<id>` | ambos | Detalle (pestañas por carpeta raíz + drawer) |
| `GET /my/proceso/<id>/descargar` | proveedor / interno | ZIP de los documentos aprobados (el cliente **no**) |
| `POST /my/proceso/<id>/politica` | cliente nivel 1 | Modo de revisión |
| `POST /my/proceso/<id>/revisores` | cliente nivel 1 | Participantes del proceso |
| `POST /my/proceso/<id>/solicitar-plazo` | cliente | Pide ampliación |
| `POST /my/solicitud/<id>/autorizar` | cliente | Autoriza por jerarquía |
| `POST /my/solicitud/<id>/decidir` | proveedor | Aprueba o rechaza |

### Ítem
| Ruta | Actor | Descripción |
|---|---|---|
| `GET /my/item/<id>/panel` | ambos | JSON del drawer |
| `POST /my/item/<id>/publicar` | proveedor | Publica o corrige |
| `POST /my/item/<id>/revisores` | proveedor | Cadena de revisores del requisito |
| `POST /my/item/<id>/aprobar` · `/observar` | cliente | Revisión |
| `POST /my/item/<id>/comentar` | ambos | Hilo |
| `GET /my/item/<id>/download/<att_id>` | ambos | Descarga con verificación |
| `POST /my/item/<id>/ampliacion/pedir` | cliente | Un revisor pide más días para revisar |
| `POST /my/item/<id>/ampliacion/conceder` | proveedor | Concede días; `beneficiario_id` elige a quién (vacío = turno actual) |
| `POST /my/ampliacion/<id>/rechazar` | proveedor | Rechaza la solicitud |
| `POST /my/item/<id>/revertir` | proveedor / interno | Devuelve el turno al revisor que dejó vencer su ventana, con `dias` |
| `POST /my/item/<id>/deshacer-publicacion` | proveedor | Retira la última versión y restaura la anterior |
| `POST /my/item/<id>/borrar-documento` | proveedor | Elimina un archivo (`attachment_id`) de un documento sin revisar |
| `POST /my/item/<id>/reemplazar-final` | proveedor | Sustituye el documento de un ítem aprobado, sin versión |
| `POST /my/proceso/<id>/cerrar` | proveedor / interno | Cierra el proyecto (exige todo aprobado) |
| `POST /my/proceso/<id>/reabrir` | proveedor / interno | Vuelve a abrirlo para reorganizarlo |

### Difusión y repositorio
| Ruta | Actor | Descripción |
|---|---|---|
| `GET /my/proceso/<id>/difusion/datos` | proveedor / interno | Qué se puede difundir y a quién (JSON del modal) |
| `POST /my/proceso/<id>/difusion/enviar` | proveedor / interno | Difunde `item_ids` a `partner_ids` (contactos del cliente) |
| `GET /my/repositorio` | cualquiera | Lo difundido a quien mira, agrupado por proyecto |
| `GET /my/repositorio/<item_id>/descargar` | difundido | Descarga con verificación del permiso |

### Administración de correos
| Ruta | Actor | Descripción |
|---|---|---|
| `GET /my/certum/admin/correos` | interno | Plantillas, copias por cliente, historial, recuperación y remitente |
| `GET /my/certum/admin/correos/caso/<id>/vista-previa` | interno | El correo pintado con datos de muestra |
| `POST /my/certum/admin/correos/caso/<id>/guardar` · `/probar` | interno | Guarda una plantilla · manda una prueba |
| `POST /my/certum/admin/correos/copias/<partner_id>/guardar` | interno | Copias (CC) de un cliente |
| `POST /my/certum/admin/correos/remitente/guardar` | interno | Servidor, nombre, contacto y pausa |
| `POST /my/certum/admin/correos/envio/<id>/reintentar` | interno | Reintenta uno fallido o atascado |
| `POST /my/certum/admin/correos/reintentar-fallidos` | interno | Reintenta todos los fallidos (50 por vez) |
| `POST /my/certum/admin/correos/recuperar` | interno | Manda lo que el cron no mandó (`clave` marcadas) |

## Configuración (`ir.config_parameter`)

Se editan en **Administración → Ajustes** (con validación y límites), no en el
backend.

| Clave | Default | Uso |
|---|---|---|
| `certum_revision.plazo_dias` | 30 | Plazo del proceso: `fecha_inicio + N` |
| `certum_revision.dias_correccion` | 3 | Días extra al proveedor tras observar |
| `certum_revision.dias_urgente` | 7 | Umbral del semáforo URGENTE |
| `certum_revision.dias_critico` | 3 | Umbral del semáforo CRÍTICO |
| `certum_revision.max_upload_mb` | 50 | Tamaño máximo por archivo |
| `certum_revision.max_zip_mb` | 200 | Tope del paquete ZIP |
| `certum_revision.dias_purga_versiones` | 10 | Días antes de depurar versiones superadas |
| `certum_revision.dias_apertura` | 90 | (legacy) solo para el cron de apertura automática |

## Tareas programadas

| Cron | Cada | Qué hace |
|---|---|---|
| `cron_abrir_procesos` | 1 día | Abre borradores próximos a vencer |
| `cron_control_plazo` | 1 día | Marca *fuera de plazo* lo vencido |
| `cron_auto_aprobar_revision` | 6 h | Auto-aprueba o avanza la cadena al vencer la ventana |
| `cron_purgar_versiones` | 1 día | Borra el contenido de las versiones superadas |
| `cron_correos_enviar` | 5 min | Manda la cola de correos (y se despierta al encolar) |
| `cron_correos_diario` | 1 día, 8:00 Lima | Avisos por fecha y lo que un disparador no encoló |

Todas se ven, se encienden o apagan y se lanzan a mano en **Administración →
Ajustes → Tareas programadas**.

## Notas de desarrollo

- **Zona horaria:** Odoo guarda los `Datetime` en UTC; **todo lo que ve o decide
  el negocio va en hora de Lima**. La conversión ocurre solo en
  `models/tz_utils.py` (`today_lima`, `fmt_lima`, `fin_de_dia_utc`). Nunca hacer
  `strftime` directo sobre un `Datetime` de Odoo: mostraría UTC.
- **Validación central** de acciones por estado/rol:
  `controllers/helpers.py::_get_item_error`.
- **Cadena de revisión**, precedencia en `models/item.py::_cadena`: cadena propia
  del ítem → participantes del proceso → capas por nivel → cualquiera. En una
  cadena, el **orden es turno, no jerarquía**: el primero revisa primero y el
  **último es la máxima autoridad** (al revés que los niveles, donde 1 manda).
- **Seguridad en dos capas:** ACL + record rules, y control fino por
  rol/propiedad/fase en cada endpoint. Nunca confiar solo en la ACL.
- Tras editar XML: `-u certum_revision`. CSS/JS: `?debug=assets`.
- Empaquetar con `python ../tools_make_zip.py` (nunca `Compress-Archive`).
- Gancho del Módulo 2: `doc_template_code` en los ítems.

## Vocabulario

En la **interfaz** el expediente de revisión se llama **proyecto**. En el
**código** el modelo sigue siendo `certum.rev.proceso` y las rutas siguen
siendo `/my/procesos` y `/my/proceso/<id>`: son contrato estable y aparecen en
correos ya enviados, así que renombrarlas rompería enlaces sin ganar nada.
Al tocar textos visibles, usa siempre **proyecto**.

## Correo

Misma metodología que los correos del e-learning (`dv_custom_website_slides`,
T-30). Todo vive en `models/correo.py`:

- **`certum.rev.correo.caso`** — las 9 plantillas (`data/correo_data.xml`, con
  `noupdate`): si está activa, asunto, texto plano con variables `{nombre}`,
  `{documento}`… (lista en `VARIABLES`), botón y días de antelación. Son **las
  mismas para todos los clientes**: salen de FYLE 360. Nada de `mail.template`:
  nadie puede meter Jinja ni HTML desde el panel.
- **`certum.rev.correo.envio`** — una fila por correo y persona: la cola, el
  historial y el seguro contra duplicados (`clave` única: caso, persona,
  registro y referencia).
- El marco del correo es `views/correo_layout.xml`: FYLE 360 arriba, la ficha
  del proyecto, la lista de documentos o la cita (observación, mensaje) según
  el caso, y Certum Global al pie.

Reglas:

1. **Un disparador solo encola** (`avisar()`), en un savepoint: publicar
   funciona con el SMTP caído. La cola la manda su cron al momento.
2. **Antes de mandar se vuelve a mirar** (`_vigente`): lo que dejó de ser
   cierto queda como «No se envió» con el motivo.
3. **Nada sale dos veces**: la Recuperación del panel cruza lo que debería
   haber salido (`_candidatos`) con lo que ya existe. Las referencias de los
   disparadores (`ref_*`) y las de la recuperación son las mismas.
4. **Lo anterior a `certum_revision.correo_desde`** (se fija en el primer
   `-u`) no se avisa.

**Remitente**: se **elige** uno de los `ir.mail_server` ya configurados en Odoo
y el correo sale desde su buzón (`from_filter` o usuario SMTP): Office 365 no
deja usar otro. Nombre (`correo_nombre`, «FYLE 360») y contacto de soporte
(`correo_contacto`) se editan en el panel. `correo_pausado = 1` detiene todo lo
automático; lo que tocaba aparece en Recuperación.

**Copias por cliente**: `res.partner.certum_correo_cc` en la empresa cliente.
Se aplican a los avisos de **sus** proyectos y solo en el **primer** correo de
cada aviso (con un correo por persona, ponerlas en todos mandaría N copias).

Para añadir un aviso: un registro en `data/correo_data.xml`, sus candidatos en
`_candidatos()` si va por fecha, su `_vigente()` y la llamada a `avisar()`. El
panel se pinta leyendo las plantillas: no hay que tocar la interfaz.

> ⚠️ **Sin un `ir.mail_server` configurado no sale ningún correo**: el panel lo
> avisa en grande en Resumen y en Correos.

## Cierre del proyecto

Aprobar el último documento **no** cierra el proyecto: lo deja
`listo_para_cerrar()` y sigue en `revision`. Cerrar es un acto deliberado
(`cerrar_proyecto()`), y se puede deshacer (`reabrir_proyecto()`).

El motivo es concreto: con `state = 'completado'`, `puede_reestructurar()` pasa
a False y el proyecto queda congelado —ni reorganizar, ni renombrar, ni añadir
lo que faltó—, justo cuando más se suele querer retocarlo. Nada más debe poner
`completado`: si hace falta reaccionar a «se aprobó el último», el sitio es
`listo_para_cerrar()`, no un cierre automático.
