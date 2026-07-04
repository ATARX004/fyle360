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

    // ── Init ─────────────────────────────────────────────────────────
    if (document.readyState !== 'loading') {
        applyFilter();
    } else {
        document.addEventListener('DOMContentLoaded', applyFilter);
    }
})();
