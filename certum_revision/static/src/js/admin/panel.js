/* ═══════════════════════════════════════════════════════════════════
   Certum Global · Revisión · Panel administrador (asignación de roles)
   - Filtro de búsqueda en vivo (sin recargar)
   - Selector segmentado de rol por fila → POST AJAX + toast
   Vanilla JS, sin dependencias. Sigue el patrón de portal_base.js
   (fetch con X-Requested-With, FormData + csrf_token, toasts sr-*).
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var list = document.getElementById('srAdminList');
    var search = document.getElementById('srAdminSearch');
    // Solo actúa en la pantalla de administración.
    if (!list && !search) return;

    var ROL_LABEL = {
        proveedor: 'Proveedor', cliente: 'Cliente',
        interno: 'Interno', '': 'sin rol'
    };

    // ── Utilidades (locales y ligeras) ───────────────────────────────
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

    // ── Filtro de búsqueda en vivo ───────────────────────────────────
    var noMatch = document.getElementById('srAdminNoMatch');

    function applyFilter() {
        if (!list || !search) return;
        var q = (search.value || '').trim().toLowerCase();
        var visible = 0;
        list.querySelectorAll('.sr-admin-row').forEach(function (row) {
            var name = row.dataset.name || '';
            var show = !q || name.indexOf(q) !== -1;
            row.classList.toggle('is-hidden', !show);
            if (show) visible++;
        });
        if (noMatch) noMatch.classList.toggle('is-hidden', visible !== 0);
    }

    if (search) {
        search.addEventListener('input', applyFilter);
        // Evita el submit/recarga: el filtrado ya ocurre en vivo.
        var form = search.closest('form');
        if (form) form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            applyFilter();
        });
    }

    // ── Selector de rol (POST AJAX por fila) ─────────────────────────
    function setRow(row, rol) {
        row.dataset.rol = rol || '';
        row.querySelectorAll('.sr-seg-btn').forEach(function (b) {
            b.setAttribute('aria-pressed', (b.dataset.rol || '') === (rol || '') ? 'true' : 'false');
        });
    }

    if (list) list.addEventListener('click', function (ev) {
        var btn = ev.target.closest('.sr-seg-btn');
        if (!btn) return;
        var row = btn.closest('.sr-admin-row');
        if (!row || row.classList.contains('is-saving')) return;

        var rol = btn.dataset.rol || '';
        var actual = row.dataset.rol || '';
        if (rol === actual) return;  // sin cambios

        var partnerId = row.dataset.partner;
        var previo = actual;

        // Actualización optimista + bloqueo mientras guarda.
        setRow(row, rol);
        row.classList.add('is-saving');

        var fd = new FormData();
        fd.append('partner_id', partnerId);
        fd.append('rol', rol);

        postForm('/my/certum/admin/rol', fd).then(function (data) {
            row.classList.remove('is-saving');
            if (data && data.ok) {
                row.classList.remove('is-updated');
                void row.offsetWidth;  // reinicia la animación
                row.classList.add('is-updated');
                toast('Rol actualizado a ' + (ROL_LABEL[rol] || rol) + '.', 'ok');
            } else {
                setRow(row, previo);  // revierte
                toast((data && data.error) || 'No se pudo actualizar el rol.', 'err');
            }
        }).catch(function () {
            row.classList.remove('is-saving');
            setRow(row, previo);
            toast('Error de conexión.', 'err');
        });
    });

    // ── Clientes asignables de un proveedor (modal) ──────────────────
    var modal = document.getElementById('srModalClientes');
    var cliList = document.getElementById('srCliList');
    var cliSearch = document.getElementById('srCliSearch');
    var cliEmpresa = document.getElementById('srCliEmpresa');
    var currentCliRow = null;

    function filterCli() {
        if (!cliList) return;
        var q = (cliSearch && cliSearch.value || '').trim().toLowerCase();
        cliList.querySelectorAll('.sr-cli-item').forEach(function (it) {
            var n = it.dataset.name || '';
            it.classList.toggle('is-hidden', !!q && n.indexOf(q) === -1);
        });
    }

    function syncItem(item) {
        var chk = item.querySelector('.sr-cli-check');
        if (chk) item.classList.toggle('is-checked', chk.checked);
    }

    function openClientes(row) {
        if (!modal) return;
        currentCliRow = row;
        var h3 = row.querySelector('.sr-admin-row-txt h3');
        cliEmpresa.textContent = h3 ? h3.textContent : 'la empresa';
        var btn = row.querySelector('[data-act="clientes"]');
        var assigned = (btn && btn.dataset.clientes || '').split(',').filter(Boolean);
        modal.querySelectorAll('.sr-cli-check').forEach(function (chk) {
            chk.checked = assigned.indexOf(chk.value) !== -1;
            syncItem(chk.closest('.sr-cli-item'));
        });
        if (cliSearch) cliSearch.value = '';
        filterCli();
        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeClientes() {
        if (!modal) return;
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden', 'true');
        currentCliRow = null;
    }

    function saveClientes(btn) {
        if (!currentCliRow) return;
        var row = currentCliRow;
        var ids = [];
        modal.querySelectorAll('.sr-cli-check:checked').forEach(function (chk) {
            ids.push(chk.value);
        });
        var fd = new FormData();
        fd.append('partner_id', row.dataset.partner);
        fd.append('cliente_ids', ids.join(','));
        btn.classList.add('is-loading');
        postForm('/my/certum/admin/clientes', fd).then(function (data) {
            btn.classList.remove('is-loading');
            if (data && data.ok) {
                var b = row.querySelector('[data-act="clientes"]');
                b.dataset.clientes = (data.cliente_ids || []).join(',');
                var cnt = b.querySelector('.sr-cli-count');
                if (cnt) cnt.textContent = data.count != null ? data.count : ids.length;
                toast('Clientes actualizados.', 'ok');
                closeClientes();
            } else {
                toast((data && data.error) || 'No se pudo guardar.', 'err');
            }
        }).catch(function () {
            btn.classList.remove('is-loading');
            toast('Error de conexión.', 'err');
        });
    }

    if (list) list.addEventListener('click', function (ev) {
        var cbtn = ev.target.closest('[data-act="clientes"]');
        if (!cbtn) return;
        var row = cbtn.closest('.sr-admin-row');
        if (row) openClientes(row);
    });

    if (modal) {
        modal.addEventListener('click', function (ev) {
            if (ev.target === modal) return closeClientes();
            if (ev.target.closest('[data-act="cerrar-clientes"]')) return closeClientes();
            var saver = ev.target.closest('[data-act="guardar-clientes"]');
            if (saver) return saveClientes(saver);
            var item = ev.target.closest('.sr-cli-item');
            if (item) setTimeout(function () { syncItem(item); }, 0);
        });
        if (cliSearch) cliSearch.addEventListener('input', filterCli);
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && modal.classList.contains('is-open')) closeClientes();
        });
    }

    // ── Init ─────────────────────────────────────────────────────────
    if (document.readyState !== 'loading') {
        applyFilter();
    } else {
        document.addEventListener('DOMContentLoaded', applyFilter);
    }
})();
