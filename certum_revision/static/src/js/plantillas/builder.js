/* ═══════════════════════════════════════════════════════════════════
   Certum Global · Revisión · Constructor de plantillas (vanilla JS)
   - Listado: modal "nueva plantilla" -> crea y redirige al editor.
   - Editor: CRUD de carpetas e ítems por AJAX (sin recargar), con toasts,
     acordeón, y modal para iniciar proceso.
   Reutiliza el patrón de portal_base.js: csrf(), ajax(), postForm(), toast().
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var app = document.querySelector('.sr-app');
    if (!app) return;

    // ── Utilidades (mismo patrón que portal_base.js) ─────────────────
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
    function withLoading(btn, promise) {
        if (btn) btn.classList.add('is-loading');
        return promise.finally(function () { if (btn) btn.classList.remove('is-loading'); });
    }

    // ── Modales (genéricas) ──────────────────────────────────────────
    function openModal(id) {
        var m = document.getElementById(id);
        if (!m) return;
        m.classList.add('is-open');
        m.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        var focusable = m.querySelector('input, select, textarea');
        if (focusable) setTimeout(function () { focusable.focus(); }, 60);
    }
    function closeModals() {
        document.querySelectorAll('.sr-modal.is-open').forEach(function (m) {
            m.classList.remove('is-open');
            m.setAttribute('aria-hidden', 'true');
        });
        document.body.style.overflow = '';
    }
    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape') closeModals();
    });
    document.addEventListener('click', function (ev) {
        // Cerrar al hacer clic fuera de la tarjeta del modal
        if (ev.target.classList && ev.target.classList.contains('sr-modal')) closeModals();
        var closer = ev.target.closest && ev.target.closest('[data-act="cerrar-modal"]');
        if (closer) closeModals();
    });

    /* ══════════════════════════════════════════════════════════════
       LISTADO: crear nueva plantilla
       ══════════════════════════════════════════════════════════════ */
    function initListado() {
        var form = document.getElementById('srFormNueva');
        if (!form) return; // no estamos en el listado

        document.addEventListener('click', function (ev) {
            var b = ev.target.closest('[data-act="nueva-plantilla"]');
            if (b) openModal('srModalNueva');
        });

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var name = (document.getElementById('srNuevaName').value || '').trim();
            if (!name) return toast('Indica un nombre para la plantilla.', 'err');
            var plazo = document.getElementById('srNuevaPlazo').value || '30';
            var btn = form.querySelector('[data-act="guardar-nueva"]');
            var fd = new FormData();
            fd.append('name', name);
            fd.append('plazo_dias', plazo);
            withLoading(btn, postForm('/my/plantilla/crear', fd).then(function (d) {
                if (d.ok && d.redirect) {
                    toast('Plantilla creada.', 'ok');
                    window.location.href = d.redirect;
                } else {
                    toast(d.error || 'No se pudo crear la plantilla.', 'err');
                }
            }).catch(function () { toast('Error de conexión.', 'err'); }));
        });
    }

    /* ══════════════════════════════════════════════════════════════
       EDITOR: estado + render + CRUD
       ══════════════════════════════════════════════════════════════ */
    function initEditor() {
        var editor = document.getElementById('srEditor');
        var raw = document.getElementById('srChecklistData');
        if (!editor || !raw) return; // no estamos en el editor

        var CID = editor.dataset.cid;
        var state = {};
        try { state = JSON.parse(raw.textContent || '{}'); } catch (e) { state = {}; }

        var canvas = document.getElementById('srCanvas');
        var UNFILED = '__none__';

        // Estado del modal reutilizable (carpeta / ítem: crear o editar)
        var editingFolder = null;   // id o null (crear)
        var editingItem = null;     // id o null (crear)

        // ── Render del lienzo ────────────────────────────────────────
        function itemsOf(folderId) {
            return (state.items || []).filter(function (it) {
                return (it.folder_id || 0) === (folderId || 0);
            });
        }

        function renderItem(it) {
            var req = it.required;
            return '<div class="sr-plt-item' + (req ? ' required' : '') +
                '" data-item="' + it.id + '">' +
                '<div class="sr-plt-item-ico">' + icon('i-doc') + '</div>' +
                '<div class="sr-plt-item-txt">' +
                '<div class="name">' + esc(it.name) + '</div>' +
                (it.description ? '<div class="desc">' + esc(it.description) + '</div>' : '') +
                '</div>' +
                '<span class="sr-req-badge' + (req ? '' : ' optional') + '">' +
                (req ? 'Obligatorio' : 'Opcional') + '</span>' +
                '<div class="sr-plt-item-tools">' +
                '<button type="button" class="sr-icon-btn" data-act="editar-item" data-id="' + it.id + '" title="Editar ítem" aria-label="Editar ítem">' + icon('i-refresh') + '</button>' +
                '<button type="button" class="sr-icon-btn danger" data-act="eliminar-item" data-id="' + it.id + '" title="Eliminar ítem" aria-label="Eliminar ítem">' + icon('i-x') + '</button>' +
                '</div></div>';
        }

        function renderFolderBlock(folder) {
            // folder === null -> bloque "Sin carpeta"
            var fid = folder ? folder.id : 0;
            var items = itemsOf(fid);
            var head, tools = '';
            var nivel = folder ? (folder.nivel || 0) : 0;
            var tope = (state.max_profundidad || 5);
            if (folder) {
                tools = '<div class="sr-folder-tools">';
                // Solo se ofrece subcarpeta si queda profundidad disponible.
                if (nivel + 1 < tope) {
                    tools += '<button type="button" class="sr-icon-btn" data-act="subcarpeta" data-id="' + folder.id + '" title="Nueva subcarpeta" aria-label="Nueva subcarpeta">' + icon('i-plus') + '</button>';
                }
                tools += '<button type="button" class="sr-icon-btn" data-act="renombrar-carpeta" data-id="' + folder.id + '" title="Renombrar" aria-label="Renombrar carpeta">' + icon('i-refresh') + '</button>' +
                    '<button type="button" class="sr-icon-btn danger" data-act="eliminar-carpeta" data-id="' + folder.id + '" title="Eliminar" aria-label="Eliminar carpeta">' + icon('i-x') + '</button>' +
                    '</div>';
                head = esc(folder.name);
            } else {
                head = 'Sin carpeta';
            }
            var body = items.length
                ? items.map(renderItem).join('')
                : '<div class="sr-folder-empty">No hay ítems en esta carpeta todavía.</div>';
            var nsub = folder ? (state.folders || []).filter(function (f) {
                return f.parent_id === folder.id;
            }).length : 0;
            var subTxt = nsub ? ' · ' + nsub + ' subcarpeta' + (nsub === 1 ? '' : 's') : '';
            return '<section class="sr-folder' + (folder ? '' : ' no-carpeta') +
                '" data-folder="' + fid + '" data-nivel="' + nivel + '"' +
                (nivel ? ' style="margin-left:' + (nivel * 22) + 'px"' : '') + '>' +
                '<div class="sr-folder-head" data-act="toggle-carpeta">' +
                '<div class="sr-folder-ico">' + icon('i-folder') + '</div>' +
                '<div class="sr-folder-titles">' +
                '<h3>' + head + '</h3>' +
                '<span class="count">' + items.length + ' ítem' + (items.length === 1 ? '' : 's') + subTxt + '</span>' +
                '</div>' + tools +
                '<svg class="sr-ico sr-folder-chevron" aria-hidden="true"><use href="#i-chevron-r"/></svg>' +
                '</div>' +
                '<div class="sr-folder-body">' + body + '</div>' +
                '</section>';
        }

        function render() {
            var html = '';
            (state.folders || []).forEach(function (f) { html += renderFolderBlock(f); });
            // Bloque "sin carpeta" solo si hay ítems huérfanos
            if (itemsOf(0).length) html += renderFolderBlock(null);

            if (!html) {
                html = '<div class="sr-empty">' +
                    '<svg class="sr-ico sr-empty-ico"><use href="#i-folder"/></svg>' +
                    '<h3>Plantilla vacía</h3>' +
                    '<p class="sr-muted">Añade una carpeta y ítems para empezar a construir tu checklist.</p>' +
                    '</div>';
            }
            canvas.innerHTML = html;
            updateCounts();
            refreshItemFolderSelect();
        }

        function updateCounts() {
            var cf = document.getElementById('srCntFolders');
            var ci = document.getElementById('srCntItems');
            if (cf) cf.textContent = (state.folders || []).length;
            if (ci) ci.textContent = (state.items || []).length;
        }

        function applyState(newState) {
            if (newState) state = newState;
            render();
        }

        // Rellena el <select> de carpeta del modal de ítem
        function refreshItemFolderSelect() {
            var sel = document.getElementById('srItemFolder');
            if (!sel) return;
            var opts = '<option value="">Sin carpeta</option>';
            (state.folders || []).forEach(function (f) {
                // Ruta completa en vez de sangria: los navegadores colapsan
                // los espacios de un <option>, y 'Padre / Hija' se lee mejor.
                opts += '<option value="' + f.id + '">' +
                    esc(f.ruta || f.name) + '</option>';
            });
            sel.innerHTML = opts;
        }

        // ── Cabecera (nombre + plazo) ────────────────────────────────
        function openHeadModal() {
            document.getElementById('srHeadName').value = state.name || '';
            document.getElementById('srHeadPlazo').value = state.plazo_dias || 0;
            openModal('srModalHead');
        }
        var formHead = document.getElementById('srFormHead');
        formHead && formHead.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var name = (document.getElementById('srHeadName').value || '').trim();
            if (!name) return toast('El nombre no puede quedar vacío.', 'err');
            var plazo = document.getElementById('srHeadPlazo').value || '0';
            var btn = formHead.querySelector('[data-act="guardar-cabecera"]');
            var fd = new FormData();
            fd.append('name', name);
            fd.append('plazo_dias', plazo);
            withLoading(btn, postForm('/my/plantilla/' + CID + '/editar', fd).then(function (d) {
                if (!d.ok) return toast(d.error || 'No se pudo guardar.', 'err');
                applyState(d.checklist);
                var nameEl = document.getElementById('srPltName');
                var plazoEl = document.getElementById('srPltPlazo');
                if (nameEl) nameEl.textContent = state.name;
                if (plazoEl) plazoEl.textContent = state.plazo_dias;
                toast('Plantilla actualizada.', 'ok');
                closeModals();
            }).catch(function () { toast('Error de conexión.', 'err'); }));
        });

        // ── Carpeta: crear / renombrar ───────────────────────────────
        var folderParent = null;   // padre al crear una subcarpeta

        function openFolderModal(folder, parentId) {
            editingFolder = folder ? folder.id : null;
            folderParent = parentId || null;
            var padre = folderParent
                ? (state.folders || []).find(function (f) { return f.id === folderParent; })
                : null;
            document.getElementById('srFolderTitle').textContent = folder
                ? 'Renombrar carpeta'
                : (padre ? 'Nueva subcarpeta en "' + padre.name + '"' : 'Nueva carpeta');
            document.getElementById('srFolderId').value = folder ? folder.id : '';
            document.getElementById('srFolderName').value = folder ? folder.name : '';
            openModal('srModalFolder');
        }
        var formFolder = document.getElementById('srFormFolder');
        formFolder && formFolder.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var name = (document.getElementById('srFolderName').value || '').trim();
            if (!name) return toast('Indica un nombre para la carpeta.', 'err');
            var btn = formFolder.querySelector('[data-act="guardar-carpeta"]');
            var fd = new FormData();
            fd.append('name', name);
            if (!editingFolder && folderParent) fd.append('parent_id', folderParent);
            var url = editingFolder
                ? '/my/plantilla/' + CID + '/carpeta/' + editingFolder + '/editar'
                : '/my/plantilla/' + CID + '/carpeta/crear';
            withLoading(btn, postForm(url, fd).then(function (d) {
                if (!d.ok) return toast(d.error || 'No se pudo guardar la carpeta.', 'err');
                applyState(d.checklist);
                toast(editingFolder ? 'Carpeta actualizada.' : 'Carpeta creada.', 'ok');
                closeModals();
            }).catch(function () { toast('Error de conexión.', 'err'); }));
        });

        function deleteFolder(id) {
            var folder = (state.folders || []).find(function (f) { return f.id === id; });
            var label = folder ? '"' + folder.name + '"' : 'esta carpeta';
            var nsub = (state.folders || []).filter(function (f) {
                return f.parent_id === id;
            }).length;
            var extra = nsub
                ? ' Se eliminaran tambien sus ' + nsub + ' subcarpeta(s).'
                : '';
            if (!window.confirm('¿Eliminar la carpeta ' + label + '?' + extra +
                                ' Sus ítems quedarán sin carpeta.')) return;
            var fd = new FormData();
            postForm('/my/plantilla/' + CID + '/carpeta/' + id + '/eliminar', fd).then(function (d) {
                if (!d.ok) return toast(d.error || 'No se pudo eliminar.', 'err');
                applyState(d.checklist);
                toast('Carpeta eliminada.', 'ok');
            }).catch(function () { toast('Error de conexión.', 'err'); });
        }

        // ── Ítem: crear / editar ─────────────────────────────────────
        function openItemModal(item, presetFolderId) {
            editingItem = item ? item.id : null;
            document.getElementById('srItemTitle').textContent =
                item ? 'Editar ítem' : 'Nuevo ítem';
            document.getElementById('srItemId').value = item ? item.id : '';
            document.getElementById('srItemName').value = item ? item.name : '';
            document.getElementById('srItemDesc').value = item ? (item.description || '') : '';
            document.getElementById('srItemRequired').checked = item ? !!item.required : true;
            refreshItemFolderSelect();
            var sel = document.getElementById('srItemFolder');
            var fv = item ? (item.folder_id || '') : (presetFolderId || '');
            if (sel) sel.value = fv ? String(fv) : '';
            openModal('srModalItem');
        }
        var formItem = document.getElementById('srFormItem');
        formItem && formItem.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var name = (document.getElementById('srItemName').value || '').trim();
            if (!name) return toast('Indica un nombre para el ítem.', 'err');
            var btn = formItem.querySelector('[data-act="guardar-item"]');
            var fd = new FormData();
            fd.append('name', name);
            fd.append('description', document.getElementById('srItemDesc').value || '');
            fd.append('required', document.getElementById('srItemRequired').checked ? '1' : '0');
            fd.append('folder_id', document.getElementById('srItemFolder').value || '');
            var url = editingItem
                ? '/my/plantilla/' + CID + '/item/' + editingItem + '/editar'
                : '/my/plantilla/' + CID + '/item/crear';
            withLoading(btn, postForm(url, fd).then(function (d) {
                if (!d.ok) return toast(d.error || 'No se pudo guardar el ítem.', 'err');
                applyState(d.checklist);
                toast(editingItem ? 'Ítem actualizado.' : 'Ítem añadido.', 'ok');
                closeModals();
            }).catch(function () { toast('Error de conexión.', 'err'); }));
        });

        function deleteItem(id) {
            var item = (state.items || []).find(function (i) { return i.id === id; });
            var label = item ? '"' + item.name + '"' : 'este ítem';
            if (!window.confirm('¿Eliminar el ítem ' + label + '?')) return;
            var card = canvas.querySelector('.sr-plt-item[data-item="' + id + '"]');
            if (card) card.classList.add('is-removing');
            var fd = new FormData();
            postForm('/my/plantilla/' + CID + '/item/' + id + '/eliminar', fd).then(function (d) {
                if (!d.ok) {
                    if (card) card.classList.remove('is-removing');
                    return toast(d.error || 'No se pudo eliminar.', 'err');
                }
                applyState(d.checklist);
                toast('Ítem eliminado.', 'ok');
            }).catch(function () {
                if (card) card.classList.remove('is-removing');
                toast('Error de conexión.', 'err');
            });
        }

        // ── Iniciar proceso ──────────────────────────────────────────
        var formIniciar = document.getElementById('srFormIniciar');
        formIniciar && formIniciar.addEventListener('submit', function (ev) {
            ev.preventDefault();
            var cliente = document.getElementById('srIniciarCliente').value;
            if (!cliente) return toast('Elige la empresa cliente.', 'err');
            if (!(state.items || []).length) return toast('La plantilla no tiene ítems.', 'err');
            var provEl = document.getElementById('srIniciarProveedor');
            if (provEl && !provEl.value) return toast('Elige la empresa proveedora.', 'err');
            var btn = formIniciar.querySelector('[data-act="confirmar-iniciar"]');
            var fd = new FormData();
            fd.append('cliente_id', cliente);
            if (provEl) fd.append('proveedor_id', provEl.value || '');
            fd.append('fecha_inicio', document.getElementById('srIniciarFecha').value || '');
            fd.append('plazo_dias', document.getElementById('srIniciarPlazo').value || '0');
            var refEl = document.getElementById('srIniciarRef');
            fd.append('referencia', refEl ? (refEl.value || '') : '');
            withLoading(btn, postForm('/my/plantilla/' + CID + '/iniciar', fd).then(function (d) {
                if (d.ok && d.redirect) {
                    toast('Proyecto iniciado.', 'ok');
                    window.location.href = d.redirect;
                } else {
                    toast(d.error || 'No se pudo iniciar el proyecto.', 'err');
                }
            }).catch(function () { toast('Error de conexión.', 'err'); }));
        });

        // ── Delegación de eventos del editor ─────────────────────────
        document.addEventListener('click', function (ev) {
            var act = ev.target.closest('[data-act]');
            if (!act) return;
            var kind = act.dataset.act;

            if (kind === 'editar-cabecera') return openHeadModal();
            if (kind === 'nueva-carpeta') return openFolderModal(null);
            if (kind === 'nuevo-item') return openItemModal(null, null);
            if (kind === 'abrir-iniciar') {
                if (!(state.items || []).length) {
                    return toast('Añade al menos un ítem antes de iniciar.', 'err');
                }
                return openModal('srModalIniciar');
            }
            if (kind === 'renombrar-carpeta') {
                var f = (state.folders || []).find(function (x) { return x.id === parseInt(act.dataset.id, 10); });
                return openFolderModal(f || null);
            }
            if (kind === 'subcarpeta') {
                // El clic en el boton no debe plegar/desplegar la carpeta.
                ev.stopPropagation();
                return openFolderModal(null, parseInt(act.dataset.id, 10));
            }
            if (kind === 'eliminar-carpeta') return deleteFolder(parseInt(act.dataset.id, 10));
            if (kind === 'editar-item') {
                var it = (state.items || []).find(function (x) { return x.id === parseInt(act.dataset.id, 10); });
                return openItemModal(it || null, null);
            }
            if (kind === 'eliminar-item') return deleteItem(parseInt(act.dataset.id, 10));
            if (kind === 'toggle-carpeta') {
                var sec = act.closest('.sr-folder');
                if (sec) sec.classList.toggle('is-collapsed');
            }
        });

        // Primer render
        render();
    }

    // ── Init ─────────────────────────────────────────────────────────
    function boot() {
        initListado();
        initEditor();
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
