/* ═══════════════════════════════════════════════════════════════════
   Certum Global · Revisión · Reorganizar un expediente ya iniciado
   - Modo edición sobre la vista de directorio
   - Modal propio (sin prompt del navegador) para crear, renombrar y mover
   - Todo por AJAX: el árbol se re-renderiza en el servidor y se sustituye,
     sin recargar la página ni perder el filtro ni el plegado
   Mover NO altera el curso: estados, archivos, plazos, comentarios y
   trazabilidad viajan con el documento, no con la carpeta.
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var gest = document.getElementById('srProcGestion');
    if (!gest || !document.getElementById('srItems')) return;
    var PROC = gest.dataset.proceso;

    // ── Utilidades ───────────────────────────────────────────────────
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function csrf() {
        var e = document.getElementById('srCsrf');
        return e ? e.value : '';
    }

    function toast(msg, tipo) {
        var box = document.getElementById('srToasts');
        if (!box) return;
        var t = document.createElement('div');
        t.className = 'sr-toast ' + (tipo || 'ok');
        t.textContent = msg;
        box.appendChild(t);
        setTimeout(function () { t.classList.add('out'); }, 3200);
        setTimeout(function () { t.remove(); }, 3700);
    }

    function post(sufijo, obj) {
        var fd = new FormData();
        Object.keys(obj || {}).forEach(function (k) { fd.append(k, obj[k]); });
        fd.append('csrf_token', csrf());
        return fetch('/my/proceso/' + PROC + sufijo, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: fd
        }).then(function (r) {
            return r.json().catch(function () {
                return { ok: false, error: 'Respuesta inesperada del servidor.' };
            });
        });
    }

    // Destinos disponibles: se releen tras cada refresco porque el árbol cambia.
    function leerDestinos() {
        var raw = document.getElementById('srDestinos');
        if (!raw) return [];
        try { return JSON.parse(raw.textContent || '[]'); } catch (e) { return []; }
    }
    var destinos = leerDestinos();

    // El refresco del árbol lo implementa portal_base, que es el dueño del
    // directorio: aquí solo se delega, para no tener dos versiones.
    function refrescar(msg) {
        var api = window.srPortal;
        if (!api || !api.refrescarArbol) { window.location.reload(); return; }
        return api.refrescarArbol().then(function () {
            destinos = leerDestinos();
            if (msg) toast(msg, 'ok');
        });
    }

    // ── Modal propio ─────────────────────────────────────────────────
    var modal = null;

    function cerrarModal() {
        if (!modal) return;
        modal.classList.remove('is-open');
        document.body.style.overflow = '';
        setTimeout(function () {
            if (modal && modal.parentNode) modal.parentNode.removeChild(modal);
            modal = null;
        }, 160);
    }

    /**
     * Abre un modal. `campos` es el HTML del cuerpo; `onAceptar(form)` recibe
     * el formulario y devuelve una promesa (o nada para cerrar sin más).
     */
    function abrirModal(opts) {
        cerrarModal();
        modal = document.createElement('div');
        modal.className = 'sr-modal sr-modal-estructura';
        modal.innerHTML =
            '<div class="sr-modal-card sr-anim-up">' +
            '<div class="sr-modal-head"><h3>' + esc(opts.titulo) + '</h3>' +
            '<button type="button" class="sr-dw-close" data-cerrar="1" aria-label="Cerrar">' +
            '<svg class="sr-ico"><use href="#i-x"/></svg></button></div>' +
            '<form class="sr-form" id="srFormEstructura">' +
            (opts.nota ? '<p class="sr-modal-nota">' + opts.nota + '</p>' : '') +
            opts.campos +
            '<div class="sr-modal-actions">' +
            '<button type="button" class="sr-btn sr-btn-ghost" data-cerrar="1">Cancelar</button>' +
            '<button type="submit" class="sr-btn ' + (opts.peligro ? 'sr-btn-warn' : 'sr-btn-primary') + '">' +
            esc(opts.aceptar || 'Guardar') + '</button>' +
            '</div></form></div>';
        // Se cuelga de .sr-app y NO de <body>: las variables de color y de
        // sombra están declaradas en .sr-app, y fuera de ahí el modal salía
        // transparente por no resolverse var(--sr-surface).
        (document.querySelector('.sr-app') || document.body).appendChild(modal);
        document.body.style.overflow = 'hidden';
        requestAnimationFrame(function () { modal.classList.add('is-open'); });

        var primero = modal.querySelector('input[type="text"], textarea, input[type="radio"]');
        if (primero) primero.focus();

        modal.addEventListener('click', function (ev) {
            if (ev.target === modal || ev.target.closest('[data-cerrar]')) {
                ev.preventDefault();
                cerrarModal();
            }
        });
        modal.querySelector('#srFormEstructura').addEventListener('submit', function (ev) {
            ev.preventDefault();
            var btn = ev.target.querySelector('button[type="submit"]');
            btn.classList.add('is-loading');
            var res = opts.onAceptar(ev.target);
            if (res && res.then) {
                res.then(function () { btn.classList.remove('is-loading'); });
            } else {
                cerrarModal();
            }
        });
    }

    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && modal) cerrarModal();
    });

    /**
     * Selector de carpeta destino.
     *
     * Se usa un <select> con la RUTA COMPLETA en cada opción, que es el mismo
     * patrón que el editor de plantillas lleva usando en producción. La lista
     * de radios con sangría que había antes quedaba con los nombres invisibles
     * y una barra de desplazamiento horizontal: dependía de un equilibrio
     * frágil de flex y desbordes que no compensa mantener.
     */
    function campoDestino(excluirRama, seleccionado) {
        var opciones = destinos.filter(function (c) {
            return !excluirRama || c.rama.indexOf(excluirRama) !== 0;
        });
        var html = '<label class="sr-field"><span>Carpeta de destino</span>' +
            '<select name="carpeta_id">' +
            '<option value=""' + (!seleccionado ? ' selected="selected"' : '') +
            '>Raíz del proyecto (sin carpeta)</option>';
        opciones.forEach(function (c) {
            var sel = String(c.id) === String(seleccionado) ? ' selected="selected"' : '';
            html += '<option value="' + c.id + '"' + sel + '>' + esc(c.ruta) + '</option>';
        });
        html += '</select>';
        if (!opciones.length) {
            html += '<small class="sr-muted sr-mini">Este proyecto todavía no ' +
                'tiene carpetas: el documento quedará en la raíz.</small>';
        }
        return html + '</label>';
    }

    function campoTexto(nombre, etiqueta, valor, placeholder) {
        return '<label class="sr-field"><span>' + esc(etiqueta) + '</span>' +
            '<input type="text" name="' + nombre + '" maxlength="200" required="required" ' +
            'value="' + esc(valor || '') + '" placeholder="' + esc(placeholder || '') + '"/></label>';
    }

    function valor(form, nombre) {
        var el = form.elements[nombre];
        if (!el) return '';
        if (el.length && el[0] && el[0].type === 'radio') {
            for (var i = 0; i < el.length; i++) {
                if (el[i].checked) return el[i].value;
            }
            return '';
        }
        return (el.value || '').trim();
    }

    function tras(promesa, msg) {
        return promesa.then(function (d) {
            if (!d || !d.ok) {
                toast((d && d.error) || 'No se pudo completar la acción.', 'err');
                return;
            }
            cerrarModal();
            return refrescar(msg);
        });
    }

    // ── Acciones ─────────────────────────────────────────────────────
    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-act]');
        if (!btn) return;
        var act = btn.dataset.act;
        var id = btn.dataset.id;
        var nombre = btn.dataset.name || '';

        if (act === 'toggle-edicion') {
            ev.preventDefault();
            var on = document.body.classList.toggle('sr-editando');
            btn.classList.toggle('is-active', on);
            return;
        }

        var MIAS = ['sub-carpeta', 'renombrar-carpeta', 'mover-carpeta',
                    'eliminar-carpeta', 'mover-item', 'eliminar-item',
                    'nueva-carpeta-raiz', 'nuevo-doc', 'guardar-plantilla'];
        if (MIAS.indexOf(act) === -1) return;
        // No debe abrir el panel del documento ni plegar la carpeta.
        ev.preventDefault();
        ev.stopPropagation();

        if (act === 'nueva-carpeta-raiz' || act === 'sub-carpeta') {
            return abrirModal({
                titulo: act === 'sub-carpeta'
                    ? 'Nueva subcarpeta en «' + nombre + '»' : 'Nueva carpeta',
                campos: campoTexto('name', 'Nombre de la carpeta', '',
                                   'Ej. 7.5 Información documentada'),
                aceptar: 'Crear carpeta',
                onAceptar: function (f) {
                    var datos = { name: valor(f, 'name') };
                    if (act === 'sub-carpeta') datos.parent_id = id;
                    return tras(post('/carpeta/crear', datos), 'Carpeta creada.');
                }
            });
        }

        if (act === 'renombrar-carpeta') {
            return abrirModal({
                titulo: 'Renombrar carpeta',
                campos: campoTexto('name', 'Nombre de la carpeta', nombre),
                onAceptar: function (f) {
                    return tras(post('/carpeta/' + id + '/editar',
                                     { name: valor(f, 'name') }), 'Carpeta renombrada.');
                }
            });
        }

        if (act === 'mover-carpeta') {
            var propia = destinos.filter(function (c) {
                return String(c.id) === String(id);
            })[0];
            return abrirModal({
                titulo: 'Mover «' + nombre + '»',
                nota: 'Los documentos de la carpeta se mueven con ella y ' +
                      '<b>conservan su estado, sus archivos y su historial</b>.',
                campos: campoDestino(propia ? propia.rama : null),
                aceptar: 'Mover',
                onAceptar: function (f) {
                    return tras(post('/carpeta/' + id + '/mover',
                                     { parent_id: valor(f, 'carpeta_id') }),
                                'Carpeta movida.');
                }
            });
        }

        if (act === 'eliminar-carpeta') {
            return abrirModal({
                titulo: 'Eliminar «' + nombre + '»',
                nota: 'Se eliminan también sus subcarpetas. Los documentos ' +
                      '<b>no se borran</b>: quedan sin carpeta, conservando su ' +
                      'estado y todo su historial.',
                campos: '',
                aceptar: 'Eliminar carpeta',
                peligro: true,
                onAceptar: function () {
                    return tras(post('/carpeta/' + id + '/eliminar', {}),
                                'Carpeta eliminada.');
                }
            });
        }

        if (act === 'nuevo-doc') {
            return abrirModal({
                titulo: 'Nuevo documento',
                nota: 'Se añadirá como <b>pendiente</b>. El avance del ' +
                      'proyecto se recalcula con el nuevo total.',
                campos: campoTexto('name', 'Nombre del documento', '',
                                   'Ej. SIG-FOR-002 Lista Maestra') +
                        '<label class="sr-field"><span>Descripción <small class="sr-muted">(opcional)</small></span>' +
                        '<textarea name="description" maxlength="2000" ' +
                        'placeholder="Qué se espera exactamente de este documento"></textarea></label>' +
                        '<label class="sr-check"><input type="checkbox" name="required" checked="checked"/>' +
                        '<span>Obligatorio para completar el proyecto</span></label>' +
                        campoDestino(),
                aceptar: 'Añadir documento',
                onAceptar: function (f) {
                    return tras(post('/item/crear', {
                        name: valor(f, 'name'),
                        description: valor(f, 'description'),
                        required: f.elements.required.checked ? '1' : '0',
                        carpeta_id: valor(f, 'carpeta_id')
                    }), 'Documento añadido.');
                }
            });
        }

        if (act === 'mover-item') {
            return abrirModal({
                titulo: 'Mover «' + nombre + '»',
                nota: 'Mover un documento <b>no altera su revisión</b>: mantiene ' +
                      'su estado, sus archivos, sus plazos, sus comentarios y su ' +
                      'trazabilidad.',
                campos: campoDestino(),
                aceptar: 'Mover',
                onAceptar: function (f) {
                    return tras(post('/item/' + id + '/mover',
                                     { carpeta_id: valor(f, 'carpeta_id') }),
                                'Documento movido. Su revisión sigue igual.');
                }
            });
        }

        if (act === 'eliminar-item') {
            if (btn.dataset.limpio !== '1') {
                return toast('Solo se pueden quitar documentos pendientes y sin ' +
                             'historial. Este ya tiene archivos, comentarios o ' +
                             'trazabilidad.', 'err');
            }
            return abrirModal({
                titulo: 'Quitar «' + nombre + '»',
                nota: 'Este documento sigue pendiente y no tiene historial, así ' +
                      'que puede quitarse del proyecto sin perder nada.',
                campos: '',
                aceptar: 'Quitar documento',
                peligro: true,
                onAceptar: function () {
                    return tras(post('/item/' + id + '/eliminar', {}),
                                'Documento quitado.');
                }
            });
        }

        if (act === 'guardar-plantilla') {
            var titulo = (document.querySelector('.sr-proc-head-info h1') || {}).textContent || '';
            return abrirModal({
                titulo: 'Guardar como plantilla nueva',
                nota: 'Se crea una plantilla <b>nueva</b> con la estructura actual ' +
                      'del proyecto. La plantilla original <b>no se toca</b>: ' +
                      'tú decides después si la retiras.',
                campos: campoTexto('name', 'Nombre de la nueva plantilla',
                                   (titulo.trim() || 'Plantilla') + ' (rev.)'),
                aceptar: 'Crear plantilla',
                onAceptar: function (f) {
                    return post('/guardar-plantilla', { name: valor(f, 'name') })
                        .then(function (d) {
                            if (!d || !d.ok) {
                                toast((d && d.error) || 'No se pudo guardar.', 'err');
                                return;
                            }
                            cerrarModal();
                            toast('Plantilla ' + d.code + ' creada.', 'ok');
                            setTimeout(function () { window.location = d.redirect; }, 800);
                        });
                }
            });
        }
    });
})();
