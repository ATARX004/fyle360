/* ═══════════════════════════════════════════════════════════════════
   Certum Global · Revisión · Motor del portal (vanilla JS, sin dependencias)
   - Pestañas flotantes por carpeta (filtrado client-side)
   - Drawer lateral del ítem cargado por AJAX (/my/item/<id>/panel)
   - Publicar (drag & drop), aprobar, observar y comentar vía fetch
   - Progress rings animados, toasts, skeleton
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var app = document.querySelector('.sr-app');
    if (!app) return;

    // ── Utilidades ───────────────────────────────────────────────────
    function csrf() {
        var el = document.getElementById('srCsrf');
        return el ? el.value : '';
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function icon(name) {
        return '<svg class="sr-ico" aria-hidden="true"><use href="#' + name + '"/></svg>';
    }

    // Fila de archivo del drawer. Un adjunto depurado conserva su registro
    // (nombre, fecha, autor) pero ya no tiene contenido: no se ofrece descarga.
    function fileRow(a, vigente) {
        var cls = 'sr-dw-file' + (vigente ? ' vigente' : '') + (a.purgado ? ' purgado' : '');
        var meta = esc(a.fecha) + (vigente ? ' · vigente' : '');
        if (a.purgado) {
            meta += a.purgado_fecha ? ' · depurado el ' + esc(a.purgado_fecha) : ' · depurado';
        }
        var accion = a.purgado
            ? '<span class="sr-dw-file-purgado" title="El contenido fue eliminado por antigüedad; el registro se conserva.">sin archivo</span>'
            : '<a href="' + esc(a.url) + '" title="Descargar">' + icon('i-download') + '</a>';
        return '<div class="' + cls + '">' + icon('i-doc') +
            '<div style="flex:1"><div class="name">' + esc(a.name) + '</div>' +
            '<div class="meta">' + meta + '</div></div>' + accion + '</div>';
    }

    var STATE_LABEL = {
        pendiente: 'Pendiente', publicado: 'Publicado',
        observado: 'Observado', aprobado: 'Aprobado'
    };
    var ROL_LABEL = { proveedor: 'Proveedor', cliente: 'Cliente', interno: 'Certum Global' };

    function toast(msg, type) {
        var box = document.getElementById('srToasts');
        if (!box) return;
        var t = document.createElement('div');
        t.className = 'sr-toast ' + (type || 'ok');
        t.innerHTML = icon(type === 'err' ? 'i-alert' : 'i-check-circle') + esc(msg);
        box.appendChild(t);
        setTimeout(function () { t.classList.add('out'); }, 3200);
        setTimeout(function () { t.remove(); }, 3700);
    }

    function ajax(url, opts) {
        opts = opts || {};
        opts.headers = Object.assign({ 'X-Requested-With': 'XMLHttpRequest' }, opts.headers || {});
        return fetch(url, opts).then(function (resp) {
            return resp.json().catch(function () {
                return { ok: false, error: 'Respuesta inesperada del servidor.' };
            });
        });
    }

    function postForm(url, formData) {
        formData.append('csrf_token', csrf());
        return ajax(url, { method: 'POST', body: formData });
    }

    // ── Progress rings ───────────────────────────────────────────────
    var RING_C = 188.5; // 2πr, r=30
    function initRings(root) {
        (root || document).querySelectorAll('.sr-ring').forEach(function (ring) {
            var fg = ring.querySelector('.sr-ring-fg');
            if (!fg) return;
            var pct = Math.max(0, Math.min(100, parseInt(ring.dataset.avance || '0', 10)));
            requestAnimationFrame(function () {
                setTimeout(function () {
                    fg.style.strokeDashoffset = (RING_C * (1 - pct / 100)).toFixed(1);
                }, 120);
            });
        });
    }

    // ── Directorio: filtros por estado y plegado de carpetas ─────────
    // Dos dimensiones independientes que se aplican juntas:
    //   filtroEstado  -> all | pendiente | publicado | observado | aprobado | mios
    //   plegadas      -> ramas que el usuario cerró (por su parent_path)
    var filtroEstado = 'all';
    var plegadas = {};

    function hayCarpetas() {
        var d = document.getElementById('srItems');
        return !!(d && d.querySelector('.sr-dir-folder'));
    }

    function estaPlegada(rama) {
        // En tarjetas o tabla no se dibujan carpetas: el plegado heredado del
        // directorio no debe ocultar nada.
        if (!hayCarpetas()) return false;
        // Una fila esta oculta si CUALQUIER ancestro suyo esta plegado.
        for (var k in plegadas) {
            if (plegadas[k] && rama && rama.indexOf(k) === 0) return true;
        }
        return false;
    }

    function casaEstado(fila) {
        if (filtroEstado === 'all') return true;
        if (filtroEstado === 'mios') return fila.dataset.mio === '1';
        return fila.dataset.state === filtroEstado;
    }

    function aplicarFiltros() {
        var dir = document.getElementById('srItems');
        if (!dir) return;
        var visibles = 0;
        // Paso 1. Qué documentos CASAN el filtro. Se calcula aparte del
        // plegado a propósito: una carpeta plegada sigue teniendo contenido,
        // y si se mezclaban ambas cosas la carpeta se ocultaba a sí misma al
        // plegarla y ya no había forma de volver a abrirla.
        var conCoincidencias = {};
        var coincidencias = 0;
        var filas = dir.querySelectorAll('.sr-fitem');
        filas.forEach(function (fila) {
            if (casaEstado(fila)) {
                conCoincidencias[fila.dataset.rama] = true;
                coincidencias++;
            }
        });

        // Paso 2. Visibilidad real de los documentos: casar el filtro y no
        // colgar de una carpeta plegada.
        filas.forEach(function (fila) {
            var ok = casaEstado(fila) && !estaPlegada(fila.dataset.rama);
            fila.classList.toggle('is-hidden', !ok);
            if (ok) visibles++;
        });

        // Paso 3. Carpetas: se muestran si tienen algo que casa el filtro
        // (aunque esté plegado) y no cuelgan de un ancestro plegado.
        dir.querySelectorAll('.sr-dir-folder').forEach(function (fila) {
            var sub = fila.dataset.sub || '';
            var relevante = filtroEstado === 'all';
            if (!relevante) {
                for (var rama in conCoincidencias) {
                    if (rama.indexOf(sub) === 0) { relevante = true; break; }
                }
            }
            var ok = relevante && !estaPlegada(fila.dataset.rama);
            fila.classList.toggle('is-hidden', !ok);
            fila.classList.toggle('is-plegada', !!plegadas[sub]);
        });

        var vacio = document.getElementById('srDirVacio');
        if (vacio) vacio.hidden = coincidencias > 0;
    }

    function initDirectorio() {
        var dir = document.getElementById('srItems');
        var filtros = document.getElementById('srFiltros');
        if (!dir) return;

        if (filtros) {
            filtros.addEventListener('click', function (ev) {
                var plegar = ev.target.closest('[data-act="plegar-todo"]');
                if (plegar) {
                    var cont = document.getElementById('srItems');
                    var todas = cont ? cont.querySelectorAll('.sr-dir-folder') : [];
                    // Si ya esta todo plegado, el boton despliega.
                    var hayAbiertas = false;
                    todas.forEach(function (f) {
                        if (!plegadas[f.dataset.sub || '']) hayAbiertas = true;
                    });
                    plegadas = {};
                    if (hayAbiertas) {
                        todas.forEach(function (f) { plegadas[f.dataset.sub || ''] = true; });
                    }
                    aplicarFiltros();
                    return;
                }
                var chip = ev.target.closest('.sr-fchip[data-estado]');
                if (!chip) return;
                filtros.querySelectorAll('.sr-fchip[data-estado]').forEach(function (c) {
                    c.classList.remove('is-active');
                });
                chip.classList.add('is-active');
                filtroEstado = chip.dataset.estado;
                aplicarFiltros();
            });
        }

        // Plegar/desplegar una carpeta. Se delega desde DOCUMENT, no desde
        // #srItems: el refresco AJAX sustituye ese nodo entero, y las escuchas
        // colgadas de él morían con el nodo viejo (las flechas dejaban de
        // responder tras el primer refresco).
        function alternarCarpeta(destino) {
            var f = destino && destino.closest && destino.closest('.sr-dir-folder');
            if (!f || !document.getElementById('srItems').contains(f)) return false;
            var sub = f.dataset.sub || '';
            plegadas[sub] = !plegadas[sub];
            aplicarFiltros();
            return true;
        }

        document.addEventListener('click', function (ev) {
            // Los botones del modo edición tienen su propia acción.
            if (ev.target.closest('[data-act]')) return;
            alternarCarpeta(ev.target);
        });
        document.addEventListener('keydown', function (ev) {
            if (ev.key !== 'Enter' && ev.key !== ' ') return;
            if (alternarCarpeta(ev.target)) ev.preventDefault();
        });

        aplicarFiltros();
    }

    // ── Refresco del árbol sin recargar la página ────────────────────
    // Vive aquí porque este módulo es el dueño del directorio; lo usan tanto
    // el selector de orden como el módulo de reorganización.
    var ordenActual = 'plantilla';
    var formatoActual = 'directorio';

    function refrescarArbol(orden, formato) {
        var gest = document.getElementById('srProcGestion');
        if (!gest) return Promise.resolve();
        if (orden) ordenActual = orden;
        if (formato) formatoActual = formato;
        var url = '/my/proceso/' + gest.dataset.proceso + '/arbol?orden=' +
                  encodeURIComponent(ordenActual) + '&formato=' +
                  encodeURIComponent(formatoActual);
        var cont = document.getElementById('srItems');
        if (cont) cont.classList.add('is-cargando');
        return ajax(url).then(function (d) {
            if (cont) cont.classList.remove('is-cargando');
            if (!d || !d.ok) {
                toast('No se pudo refrescar la vista.', 'err');
                return d;
            }
            var tmp = document.createElement('div');
            tmp.innerHTML = d.html;
            var nuevo = tmp.querySelector('#srItems');
            if (nuevo && cont) cont.parentNode.replaceChild(nuevo, cont);
            actualizarCabecera(d);
            // El filtro y el plegado son estado del navegador: hay que
            // reaplicarlos o el usuario pierde de vista dónde estaba.
            aplicarFiltros();
            return d;
        }).catch(function () {
            if (cont) cont.classList.remove('is-cargando');
            toast('Error de conexión al refrescar.', 'err');
        });
    }

    function actualizarCabecera(d) {
        document.querySelectorAll('.sr-fchip[data-estado]').forEach(function (chip) {
            var n = d.conteo && d.conteo[chip.dataset.estado];
            var badge = chip.querySelector('.sr-fcount');
            if (badge && n !== undefined) badge.textContent = n;
        });
        var ring = document.querySelector('.sr-proc-head-side .sr-ring');
        if (ring && d.avance !== undefined) {
            ring.dataset.avance = d.avance;
            var lbl = ring.querySelector('.sr-ring-label');
            if (lbl) lbl.textContent = d.avance + '%';
            initRings(ring.parentNode);
        }
        var cnt = document.querySelector('.sr-btn-zip .sr-btn-count');
        if (cnt && d.n_aprobados !== undefined) cnt.textContent = d.n_aprobados;
        var box = document.getElementById('srDiffBox');
        if (box) {
            var hay = d.diff && d.diff.total;
            box.hidden = !hay;
            var res = box.querySelector('.sr-diff-resumen');
            if (res) res.textContent = d.diff_resumen || '';
        }
    }

    // Orden y formato: mismo comportamiento, se recuerdan entre visitas y
    // se aplican por AJAX. Si lo guardado difiere de lo que pintó el servidor,
    // se hace UN refresco al cargar.
    function initPreferencias() {
        var selOrden = document.getElementById('srOrden');
        var selFormato = document.getElementById('srFormato');
        if (!selOrden && !selFormato) return;
        if (selOrden) ordenActual = selOrden.value || 'plantilla';
        if (selFormato) formatoActual = selFormato.value || 'directorio';

        var pedir = false;
        try {
            var o = window.localStorage.getItem('srOrden');
            var f = window.localStorage.getItem('srFormato');
            if (selOrden && o && o !== ordenActual) {
                selOrden.value = o; ordenActual = o; pedir = true;
            }
            if (selFormato && f && f !== formatoActual) {
                selFormato.value = f; formatoActual = f; pedir = true;
            }
        } catch (e) { /* almacenamiento no disponible: se ignora */ }
        if (pedir) refrescarArbol();

        function alCambiar(sel, clave, esFormato) {
            if (!sel) return;
            sel.addEventListener('change', function () {
                try { window.localStorage.setItem(clave, sel.value); } catch (e) {}
                refrescarArbol(esFormato ? null : sel.value,
                               esFormato ? sel.value : null);
            });
        }
        alCambiar(selOrden, 'srOrden', false);
        alCambiar(selFormato, 'srFormato', true);
    }

    // API para el módulo de reorganización.
    window.srPortal = {
        refrescarArbol: refrescarArbol,
        refrescarDirectorio: aplicarFiltros,
        initRings: initRings
    };

    // ── Drawer del ítem ──────────────────────────────────────────────
    var drawer = document.getElementById('srDrawer');
    var backdrop = document.getElementById('srBackdrop');
    var body = document.getElementById('srDrawerBody');
    var skeletonHTML = body ? body.innerHTML : '';
    var currentItem = null;

    function openDrawer(itemId) {
        currentItem = itemId;
        body.innerHTML = skeletonHTML;
        drawer.classList.add('is-open');
        backdrop.classList.add('is-open');
        document.body.style.overflow = 'hidden';
        ajax('/my/item/' + itemId + '/panel').then(function (data) {
            if (!data.ok) {
                toast(data.error || 'No se pudo cargar el ítem.', 'err');
                closeDrawer();
                return;
            }
            renderPanel(data);
        }).catch(function () {
            toast('Error de conexión.', 'err');
            closeDrawer();
        });
    }

    function closeDrawer() {
        drawer.classList.remove('is-open');
        backdrop.classList.remove('is-open');
        document.body.style.overflow = '';
        currentItem = null;
    }

    backdrop && backdrop.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape') closeDrawer();
    });

    // ── Render del panel ─────────────────────────────────────────────
    function renderPanel(data) {
        var it = data.item, acc = data.acciones;
        var html = '';

        html += '<div class="sr-dw-head"><div>' +
            '<span class="sr-chip" data-state="' + esc(it.state) + '">' + esc(it.state_label) + '</span>' +
            '<h3>' + esc(it.name) + '</h3>' +
            '<p class="sr-muted sr-mini">' + icon('i-folder') + esc(it.carpeta) +
            (it.required ? ' · Obligatorio' : '') + '</p>' +
            '</div><button type="button" class="sr-dw-close" data-act="close" aria-label="Cerrar">' +
            icon('i-x') + '</button></div>';

        // Barra de avance por la cadena de revision
        var av = data.avance || {};
        if (av.label) {
            html += '<div class="sr-dw-avance" data-tono="' + esc(av.tono || 'idle') + '">' +
                '<div class="sr-dw-avance-top"><span>' + esc(av.titulo || av.label) + '</span>' +
                '<b>' + esc(av.label) + '</b></div>' +
                '<div class="sr-dw-avance-track"><span style="width:' +
                (av.pct || 0) + '%"></span></div></div>';
        }

        if (it.description) {
            html += '<p class="sr-muted" style="font-size:.92rem">' + esc(it.description) + '</p>';
        }

        // Info de la ventana de revisión / cadena (niveles o a medida)
        var rev = data.revision || {};
        if (it.state === 'publicado' && rev.total_pasos) {
            html += '<div class="sr-dw-note">' + icon('i-clock') + '<span>' +
                'Revisión por ' + (rev.a_medida ? 'cadena a medida' : 'capas') +
                ' · paso ' + esc(rev.paso_actual) + '/' + esc(rev.total_pasos) +
                ' · corresponde a <b>' + esc(rev.revisor_actual) + '</b>' +
                (rev.limite_revision ? ' · límite ' + esc(rev.limite_revision) : '') +
                '</span></div>';
        } else if (it.state === 'publicado' && rev.limite_revision) {
            html += '<div class="sr-dw-note">' + icon('i-clock') +
                '<span>El cliente tiene hasta <b>' + esc(rev.limite_revision) +
                '</b> para revisar (si no, se aprueba solo)</span></div>';
        }

        // Ampliación de la ventana de revisión (asunto interno del cliente)
        var amp = data.ampliaciones || {};
        if (amp.puede_pedir || (amp.lista && amp.lista.length)) {
            html += '<div class="sr-dw-section"><h4>' + icon('i-clock') +
                'Días de revisión</h4>';
            if (amp.lista && amp.lista.length) {
                amp.lista.forEach(function (a) {
                    var det = a.estado === 'concedida'
                        ? '+' + a.dias_concedidos + ' día(s) concedidos'
                        : (a.dias_pedidos ? a.dias_pedidos + ' día(s) pedidos' : '');
                    // A quién fueron y si ya entraron en una ventana o siguen
                    // esperando el turno de esa persona.
                    if (a.beneficiario) det += ' · para ' + a.beneficiario;
                    html += '<div class="sr-amp-row" data-estado="' + esc(a.estado) + '">' +
                        '<div class="sr-amp-txt"><b>' + esc(a.solicitante) + '</b> · ' +
                        esc(det) + (a.reservada ? ' <span class="sr-amp-tag">reservados' +
                        '</span>' : '') + (a.motivo ? '<br/><span class="sr-muted">' +
                        esc(a.motivo) + '</span>' : '') + '</div>' +
                        '<span class="sr-amp-estado">' + esc(a.estado_label) + '</span>';
                    if (a.estado === 'pendiente' && amp.puede_conceder) {
                        html += '<span class="sr-amp-acciones">' +
                            '<button type="button" class="sr-btn sr-btn-ok sr-btn-sm" ' +
                            'data-act="amp-conceder" data-amp="' + a.id + '" data-dias="' +
                            (a.dias_pedidos || 1) + '" data-benef="' +
                            (a.solicitante_id || '') + '">Conceder</button>' +
                            '<button type="button" class="sr-btn sr-btn-warn sr-btn-sm" ' +
                            'data-act="amp-rechazar" data-amp="' + a.id + '">Rechazar</button>' +
                            '</span>';
                    }
                    html += '</div>';
                });
            }
            if (amp.puede_pedir || amp.puede_conceder) {
                html += '<div class="sr-amp-form">' +
                    '<input type="number" id="srAmpDias" min="1" max="60" value="3" ' +
                    'aria-label="Días adicionales"/>' +
                    '<input type="text" id="srAmpMotivo" placeholder="Motivo (opcional)…"/>';
                // A quién van los días. Si se elige un revisor cuyo turno aún
                // no llegó, los días quedan reservados hasta que le toque.
                if (amp.puede_conceder && amp.beneficiarios && amp.beneficiarios.length) {
                    html += '<label class="sr-amp-benef"><span>Para</span>' +
                        '<select id="srAmpBenef"><option value="">' +
                        'Quien tenga el turno ahora</option>';
                    amp.beneficiarios.forEach(function (b) {
                        html += '<option value="' + b.id + '">' + esc(b.name) +
                            ' · paso ' + b.paso + (b.actual ? ' (turno actual)' : '') +
                            '</option>';
                    });
                    html += '</select></label>';
                }
                if (amp.puede_pedir) {
                    html += '<button type="button" class="sr-btn sr-btn-ghost" ' +
                        'data-act="amp-pedir">' + icon('i-plus') +
                        'Pedir días al proveedor</button>';
                }
                if (amp.puede_conceder) {
                    html += '<button type="button" class="sr-btn sr-btn-primary" ' +
                        'data-act="amp-dar">' + icon('i-check') + 'Dar días</button>';
                }
                html += '</div>';
                html += '<p class="sr-muted sr-mini">' + (amp.puede_conceder
                    ? 'Puedes conceder días aunque nadie los haya pedido. El tope ' +
                      'sigue siendo el plazo general del expediente.'
                    : 'Los días de revisión los concede el proveedor, que es quien ' +
                      'los fijó al publicar el documento.') + '</p>';
            }
            html += '</div>';
        }

        // Cadena de revisores del ítem (la designa el PROVEEDOR)
        var cfg = data.config_revisores || {};
        if (cfg.puede) {
            html += '<div class="sr-dw-section"><h4>' + icon('i-shield') + 'Cadena de revisión a medida</h4>' +
                '<p class="sr-muted sr-mini">Elige, en orden, qué personas del cliente revisan este requisito; la última es la máxima autoridad. Sin selección se aplica la política del expediente.</p>' +
                '<div class="sr-chain" id="srChain"></div>' +
                '<div class="sr-chain-pool" id="srChainPool"></div>' +
                '<div class="sr-publish-actions"><button type="button" class="sr-btn sr-btn-primary" data-act="guardar-revisores">' +
                icon('i-check') + 'Guardar cadena</button></div></div>';
        }
        if (it.state === 'observado' && rev.limite_correccion) {
            html += '<div class="sr-dw-note warn">' + icon('i-alert') +
                '<span>El proveedor puede corregir hasta <b>' + esc(rev.limite_correccion) + '</b></span></div>';
            // La corrección no reinicia la cadena: vuelve a quien observó, con
            // sus días otra vez, y desde ahí sigue al resto.
            if (rev.reanuda_quien) {
                html += '<div class="sr-dw-note">' + icon('i-clock') +
                    '<span>Al subir la corrección volverá a <b>' +
                    esc(rev.reanuda_quien) + '</b> (paso ' + rev.reanuda_en +
                    ' de ' + rev.total_pasos + '), con sus días de revisión de ' +
                    'nuevo. Las aprobaciones anteriores se mantienen.</span></div>';
            }
        }

        // Turno vencido: el proveedor puede devolverlo si nadie decidio despues.
        var rvn = rev.reversion || {};
        if (rvn.hubo_omision) {
            html += '<div class="sr-dw-section"><h4>' + icon('i-clock') +
                'Turno vencido</h4>';
            if (rvn.puede) {
                html += '<p class="sr-muted sr-mini"><b>' + esc(rvn.quien) +
                    '</b> (paso ' + rvn.paso + ') dejó vencer su plazo y el ' +
                    'sistema siguió adelante. Puedes devolverle el turno con ' +
                    'los días que necesite.</p>' +
                    '<div class="sr-amp-form">' +
                    '<input type="number" id="srRevDias" min="1" max="60" value="' +
                    (rvn.dias_sugeridos || 1) + '" aria-label="Días para revisar"/>' +
                    '<button type="button" class="sr-btn sr-btn-primary" ' +
                    'data-act="revertir">' + icon('i-check') +
                    'Devolver el turno</button></div>' +
                    '<p class="sr-muted sr-mini">Si el documento estaba aprobado ' +
                    'por vencimiento, se reabre. Se avisa por correo al cliente.</p>';
            } else {
                html += '<p class="sr-muted sr-mini">' + esc(rvn.motivo) + '</p>';
            }
            html += '</div>';
        }

        // Acciones del cliente (revisar)
        if (acc.aprobar || acc.observar) {
            html += '<div class="sr-dw-section"><h4>' + icon('i-eye') + 'Revisión</h4>' +
                '<div class="sr-review-actions">' +
                (acc.aprobar ? '<button type="button" class="sr-btn sr-btn-ok" data-act="aprobar">' + icon('i-check') + 'Aprobar</button>' : '') +
                (acc.observar ? '<button type="button" class="sr-btn sr-btn-warn" data-act="toggle-observar">' + icon('i-alert') + 'Observar</button>' : '') +
                '</div>' +
                '<div class="sr-observe-box" id="srObserveBox">' +
                '<textarea id="srObserveText" placeholder="Indica qué debe corregir el proveedor…"></textarea>' +
                '<label class="sr-drop sr-drop-sm" id="srObsDrop">' + icon('i-paperclip') +
                '<span id="srObsDropText">En caso de haber dejado comentarios en el documento, súbelo por aquí (opcional)</span>' +
                '<input type="file" id="srObsFile"/></label>' +
                '<button type="button" class="sr-btn sr-btn-warn" data-act="observar">' + icon('i-send') + 'Enviar observación</button>' +
                '</div></div>';
        }
        if (it.state === 'aprobado') {
            html += '<div class="sr-dw-section"><div class="sr-confirm">' +
                icon('i-check-circle') + 'Ítem aprobado y listo en su carpeta.</div></div>';
        }

        // Publicación del proveedor
        if (acc.publicar) {
            html += '<div class="sr-dw-section"><h4>' + icon('i-upload') +
                (it.state === 'observado' ? 'Corregir y volver a publicar' : 'Publicar documento') + '</h4>' +
                '<label class="sr-drop" id="srDrop">' + icon('i-upload') +
                '<span id="srDropText">Arrastra tu archivo aquí o haz clic para elegirlo</span>' +
                '<input type="file" id="srFile"/></label>';
            if (acc.primera_publicacion) {
                html += '<label class="sr-field-inline"><span>' + icon('i-clock') +
                    'Días que tendrá el cliente para revisar</span>' +
                    '<input type="number" id="srDiasRevision" min="1" max="365" value="5"/></label>';
            } else if (rev.dias_revision) {
                html += '<p class="sr-muted sr-mini">' + icon('i-clock') +
                    'El cliente tendrá ' + esc(rev.dias_revision) + ' días para revisar.</p>';
            }
            html += '<div class="sr-publish-actions">' +
                '<button type="button" class="sr-btn sr-btn-primary" data-act="publicar" disabled>' +
                icon('i-send') + 'Publicar</button></div></div>';
        }

        // Documentos
        html += '<div class="sr-dw-section"><h4>' + icon('i-paperclip') + 'Documentos</h4>';
        if (it.attachments.length) {
            it.attachments.forEach(function (a) { html += fileRow(a, a.vigente); });
            if (it.attachments.length > 1) {
                html += '<p class="sr-dw-note">Solo se conserva la versión vigente. ' +
                    'Las anteriores se depuran por antigüedad: se borra el archivo, ' +
                    'pero queda el registro de que existió. Guarde una copia si la necesita.</p>';
            }
        } else {
            html += '<p class="sr-muted sr-mini">Aún no hay documentos publicados.</p>';
        }
        html += '</div>';

        // Adjuntos del cliente (documentos con marcas)
        if (it.attachments_cliente && it.attachments_cliente.length) {
            html += '<div class="sr-dw-section"><h4>' + icon('i-paperclip') + 'Adjuntos del cliente</h4>';
            it.attachments_cliente.forEach(function (a) { html += fileRow(a, false); });
            html += '</div>';
        }

        // Hilo de comentarios
        html += '<div class="sr-dw-section"><h4>' + icon('i-comment') + 'Conversación</h4>' +
            '<div class="sr-thread">';
        if (it.comments.length) {
            it.comments.forEach(function (c) {
                html += '<div class="sr-msg rol-' + esc(c.rol) + (c.propio ? ' propio' : '') + '">' +
                    '<div class="who">' + esc(c.autor) + ' · ' + esc(ROL_LABEL[c.rol] || c.rol) + '</div>' +
                    '<div class="body">' + esc(c.body) + '</div>' +
                    '<div class="when">' + esc(c.fecha) + '</div></div>';
            });
        } else {
            html += '<p class="sr-muted sr-mini">Sin comentarios todavía.</p>';
        }
        html += '</div>';
        if (data.acciones.comentar) {
            html += '<div class="sr-comment-form">' +
                '<textarea id="srCommentText" placeholder="Escribe un comentario…"></textarea>' +
                '<button type="button" class="sr-btn sr-btn-primary" data-act="comentar" aria-label="Enviar">' +
                icon('i-send') + '</button></div>';
        }
        html += '</div>';

        // Trazabilidad (quién aprobó/observó y cuándo)
        if (it.trazas && it.trazas.length) {
            html += '<div class="sr-dw-section"><h4>' + icon('i-shield') + 'Trazabilidad</h4>' +
                '<div class="sr-traza">';
            it.trazas.forEach(function (t) {
                html += '<div class="sr-traza-row" data-accion="' + esc(t.accion) + '">' +
                    '<span class="sr-traza-dot"></span><div>' +
                    '<b>' + esc(t.accion_label) + '</b> · ' + esc(t.autor) +
                    (t.nivel ? ' <span class="sr-traza-nivel">N' + esc(t.nivel) + '</span>' : '') +
                    '<div class="when">' + esc(t.fecha) + '</div>' +
                    (t.comentario ? '<div class="sr-traza-c">' + esc(t.comentario) + '</div>' : '') +
                    '</div></div>';
            });
            html += '</div></div>';
        }

        body.innerHTML = html;
        initDropzone();
        initChain(data.config_revisores);
        syncCard(it, data);
    }

    // ── Cadena de revisores a medida (config del nivel 1 del cliente) ─
    var chainState = [];
    var chainContactos = {};

    function initChain(cfg) {
        if (!cfg || !cfg.puede) return;
        chainState = (cfg.revisores || []).map(function (r) { return r.id; });
        chainContactos = {};
        (cfg.contactos || []).forEach(function (c) { chainContactos[c.id] = c.name; });
        renderChain();
    }

    function renderChain() {
        var chain = document.getElementById('srChain');
        var pool = document.getElementById('srChainPool');
        if (!chain || !pool) return;
        chain.innerHTML = chainState.length
            ? chainState.map(function (id, i) {
                return '<div class="sr-chain-item"><span class="sr-chain-num">' + (i + 1) +
                    '</span><span class="sr-chain-name">' + esc(chainContactos[id] || id) +
                    '</span><button type="button" class="sr-chain-x" data-chain-rm="' + id + '">' +
                    icon('i-x') + '</button></div>';
            }).join('')
            : '<p class="sr-muted sr-mini">Sin revisores a medida (se usa la jerarquía por niveles).</p>';
        pool.innerHTML = Object.keys(chainContactos).filter(function (id) {
            return chainState.indexOf(parseInt(id, 10)) === -1;
        }).map(function (id) {
            return '<button type="button" class="sr-chain-add" data-chain-add="' + id + '">' +
                icon('i-plus') + esc(chainContactos[id]) + '</button>';
        }).join('');
    }

    // Sincroniza la tarjeta del grid con el nuevo estado del ítem
    function syncCard(it, data) {
        var card = document.querySelector('.sr-item[data-item="' + it.id + '"]');
        if (!card) return;
        if (card.dataset.state !== it.state) {
            card.dataset.state = it.state;
            var chip = card.querySelector('.sr-item-chip, .sr-dir-chip');
            if (chip) {
                chip.dataset.state = it.state;
                chip.textContent = STATE_LABEL[it.state] || it.state;
            }
            card.classList.remove('is-updated');
            void card.offsetWidth;
            card.classList.add('is-updated');
        }
        if (data && typeof data.avance === 'number') {
            document.querySelectorAll('.sr-ring').forEach(function (ring) {
                ring.dataset.avance = Math.round(data.avance);
                var label = ring.querySelector('.sr-ring-label');
                if (label) label.textContent = Math.round(data.avance) + '%';
            });
            initRings(document);
        }
    }

    // ── Dropzone ─────────────────────────────────────────────────────
    var pickedFile = null;
    var pickedObsFile = null;

    function initDropzone() {
        var drop = document.getElementById('srDrop');
        var input = document.getElementById('srFile');
        pickedFile = null;
        pickedObsFile = null;

        // Adjunto opcional del cliente al observar
        var obsInput = document.getElementById('srObsFile');
        if (obsInput) {
            obsInput.addEventListener('change', function () {
                pickedObsFile = obsInput.files[0] || null;
                var t = document.getElementById('srObsDropText');
                if (t) t.innerHTML = pickedObsFile
                    ? '<span class="picked">' + esc(pickedObsFile.name) + '</span>'
                    : 'En caso de haber dejado comentarios en el documento, súbelo por aquí (opcional)';
            });
        }
        if (!drop || !input) return;

        function setFile(f) {
            pickedFile = f || null;
            var txt = document.getElementById('srDropText');
            var btn = body.querySelector('[data-act="publicar"]');
            if (pickedFile) {
                txt.innerHTML = '<span class="picked">' + esc(pickedFile.name) + '</span>';
                btn && btn.removeAttribute('disabled');
            } else {
                txt.textContent = 'Arrastra tu archivo aquí o haz clic para elegirlo';
                btn && btn.setAttribute('disabled', 'disabled');
            }
        }
        input.addEventListener('change', function () { setFile(input.files[0]); });
        ['dragenter', 'dragover'].forEach(function (evName) {
            drop.addEventListener(evName, function (ev) {
                ev.preventDefault(); drop.classList.add('is-over');
            });
        });
        ['dragleave', 'drop'].forEach(function (evName) {
            drop.addEventListener(evName, function (ev) {
                ev.preventDefault(); drop.classList.remove('is-over');
            });
        });
        drop.addEventListener('drop', function (ev) {
            if (ev.dataTransfer.files.length) setFile(ev.dataTransfer.files[0]);
        });
    }

    // ── Acciones (delegación en el drawer) ───────────────────────────
    function withLoading(btn, promise) {
        btn.classList.add('is-loading');
        return promise.finally(function () { btn.classList.remove('is-loading'); });
    }

    function handleResult(data, okMsg) {
        if (data.ok) {
            toast(okMsg, 'ok');
            renderPanel(data);
        } else {
            toast(data.error || 'No se pudo completar la acción.', 'err');
        }
    }

    body && body.addEventListener('click', function (ev) {
        // Cadena a medida: añadir / quitar revisor (no usan data-act)
        var addBtn = ev.target.closest('[data-chain-add]');
        if (addBtn) {
            chainState.push(parseInt(addBtn.dataset.chainAdd, 10));
            renderChain();
            return;
        }
        var rmBtn = ev.target.closest('[data-chain-rm]');
        if (rmBtn) {
            var rid = parseInt(rmBtn.dataset.chainRm, 10);
            chainState = chainState.filter(function (x) { return x !== rid; });
            renderChain();
            return;
        }

        var btn = ev.target.closest('[data-act]');
        if (!btn || !currentItem) return;
        var act = btn.dataset.act;

        if (act === 'close') return closeDrawer();

        if (act === 'guardar-revisores') {
            var fdR = new FormData();
            fdR.append('partner_ids', chainState.join(','));
            withLoading(btn, postForm('/my/item/' + currentItem + '/revisores', fdR)
                .then(function (d) {
                    if (d.ok) { toast('Cadena guardada.', 'ok'); openDrawer(currentItem); }
                    else toast(d.error || 'No se pudo guardar la cadena.', 'err');
                }));
            return;
        }

        // ── Días de revisión: pedir, dar, conceder, rechazar ──────────
        // El aviso lo decide el servidor: solo él sabe si los días
        // entraron en la ventana viva o quedaron reservados para un turno
        // que aún no ha llegado.
        function msgAmp(accion, d) {
            if (accion === 'amp-pedir') return 'Solicitud enviada al proveedor.';
            if (d.reservada) return 'Días reservados: se sumarán cuando le toque el turno.';
            return 'Días concedidos.' + (d.limite ? ' Nuevo límite: ' + d.limite : '');
        }
        if (act === 'amp-pedir' || act === 'amp-dar') {
            var elD = document.getElementById('srAmpDias');
            var dias = parseInt(elD && elD.value, 10);
            if (!dias || dias < 1) return toast('Indica cuántos días.', 'err');
            var elM = document.getElementById('srAmpMotivo');
            var fdA = new FormData();
            fdA.append('dias', dias);
            fdA.append('motivo', (elM && elM.value) || '');
            var elB = document.getElementById('srAmpBenef');
            if (elB) fdA.append('beneficiario_id', elB.value || '');
            var rutaA = act === 'amp-pedir' ? '/ampliacion/pedir' : '/ampliacion/conceder';
            withLoading(btn, postForm('/my/item/' + currentItem + rutaA, fdA)
                .then(function (d) {
                    if (d.ok) { toast(msgAmp(act, d), 'ok'); openDrawer(currentItem); }
                    else toast(d.error || 'No se pudo completar.', 'err');
                }));
            return;
        }
        if (act === 'amp-conceder') {
            var fdC = new FormData();
            fdC.append('dias', btn.dataset.dias || '1');
            fdC.append('ampliacion_id', btn.dataset.amp);
            // Los días de una solicitud van a quien la pidió, no al turno actual.
            if (btn.dataset.benef) fdC.append('beneficiario_id', btn.dataset.benef);
            withLoading(btn, postForm('/my/item/' + currentItem + '/ampliacion/conceder', fdC)
                .then(function (d) {
                    if (d.ok) {
                        toast(msgAmp('amp-conceder', d), 'ok');
                        openDrawer(currentItem);
                    } else toast(d.error || 'No se pudo conceder.', 'err');
                }));
            return;
        }
        if (act === 'revertir') {
            var elRD = document.getElementById('srRevDias');
            var diasR = parseInt(elRD && elRD.value, 10);
            if (!diasR || diasR < 1) return toast('Indica cuántos días.', 'err');
            if (!confirm('Se devolverá el turno a ese revisor con ' + diasR +
                         ' día(s). Si el documento estaba aprobado por ' +
                         'vencimiento, volverá a revisión. ¿Continuar?')) return;
            var fdV = new FormData();
            fdV.append('dias', diasR);
            withLoading(btn, postForm('/my/item/' + currentItem + '/revertir', fdV)
                .then(function (d) {
                    if (d.ok) {
                        toast('Turno devuelto. Nuevo plazo: ' + (d.limite || ''), 'ok');
                        openDrawer(currentItem);
                        refrescarArbol();
                    } else toast(d.error || 'No se pudo devolver el turno.', 'err');
                }));
            return;
        }
        if (act === 'amp-rechazar') {
            withLoading(btn, postForm('/my/ampliacion/' + btn.dataset.amp + '/rechazar',
                                      new FormData())
                .then(function (d) {
                    if (d.ok) { toast('Solicitud rechazada.', 'ok'); openDrawer(currentItem); }
                    else toast(d.error || 'No se pudo rechazar.', 'err');
                }));
            return;
        }

        if (act === 'toggle-observar') {
            var box = document.getElementById('srObserveBox');
            box && box.classList.toggle('is-open');
            return;
        }
        if (act === 'publicar') {
            if (!pickedFile) return toast('Elige un archivo primero.', 'err');
            var fd = new FormData();
            fd.append('archivo', pickedFile);
            var diasEl = document.getElementById('srDiasRevision');
            if (diasEl) {
                if (!diasEl.value || parseInt(diasEl.value, 10) <= 0)
                    return toast('Indica cuántos días tendrá el cliente para revisar.', 'err');
                fd.append('dias_revision', diasEl.value);
            }
            withLoading(btn, postForm('/my/item/' + currentItem + '/publicar', fd)
                .then(function (d) { handleResult(d, 'Documento publicado.'); }));
            return;
        }
        if (act === 'aprobar') {
            var fdA = new FormData();
            withLoading(btn, postForm('/my/item/' + currentItem + '/aprobar', fdA)
                .then(function (d) { handleResult(d, 'Ítem aprobado.'); }));
            return;
        }
        if (act === 'observar') {
            var textEl = document.getElementById('srObserveText');
            var comentario = (textEl && textEl.value || '').trim();
            if (!comentario) return toast('Indica qué debe corregir el proveedor.', 'err');
            var fdO = new FormData();
            fdO.append('comentario', comentario);
            if (pickedObsFile) fdO.append('archivo', pickedObsFile);
            withLoading(btn, postForm('/my/item/' + currentItem + '/observar', fdO)
                .then(function (d) { handleResult(d, 'Observación enviada.'); }));
            return;
        }
        if (act === 'comentar') {
            var cEl = document.getElementById('srCommentText');
            var bodyTxt = (cEl && cEl.value || '').trim();
            if (!bodyTxt) return toast('Escribe un comentario.', 'err');
            var fdC = new FormData();
            fdC.append('body', bodyTxt);
            withLoading(btn, postForm('/my/item/' + currentItem + '/comentar', fdC)
                .then(function (d) { handleResult(d, 'Comentario enviado.'); }));
        }
    });

    // ── Apertura del drawer desde las tarjetas ───────────────────────
    document.addEventListener('click', function (ev) {
        var card = ev.target.closest('.sr-item[data-item]');
        if (card) openDrawer(card.dataset.item);
    });
    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter') return;
        var card = ev.target.closest && ev.target.closest('.sr-item[data-item]');
        if (card) openDrawer(card.dataset.item);
    });

    // ── Init ─────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        initRings(document);
        initDirectorio();
        initPreferencias();
    });
    if (document.readyState !== 'loading') {
        initRings(document);
        initDirectorio();
        initPreferencias();
    }
})();
