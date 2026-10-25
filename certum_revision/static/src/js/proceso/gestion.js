/* ═══════════════════════════════════════════════════════════════════
   FYLE 360 · Gestión del proceso
   - Política de revisión (nivel 1 del cliente): modo + capas
   - Solicitudes de ampliación de plazo (crear, autorizar, decidir)
   Vanilla JS. Se auto-limita a la pantalla de detalle (#srProcGestion).
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var root = document.getElementById('srProcGestion');
    if (!root) return;
    var proceso = root.dataset.proceso;

    function csrf() { var e = document.getElementById('srCsrf'); return e ? e.value : ''; }

    function toast(msg, type) {
        var box = document.getElementById('srToasts');
        if (!box) return;
        var t = document.createElement('div');
        t.className = 'sr-toast ' + (type || 'ok');
        t.textContent = msg;
        box.appendChild(t);
        setTimeout(function () { t.classList.add('out'); }, 3000);
        setTimeout(function () { t.remove(); }, 3500);
    }

    function post(url, obj) {
        var fd = new FormData();
        Object.keys(obj).forEach(function (k) { fd.append(k, obj[k]); });
        fd.append('csrf_token', csrf());
        return fetch(url, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: fd,
        }).then(function (r) {
            return r.json().catch(function () {
                return { ok: false, error: 'Respuesta inesperada del servidor.' };
            });
        });
    }

    function done(btn, d, okMsg) {
        btn.classList.remove('is-loading');
        if (d && d.ok) {
            toast(okMsg, 'ok');
            setTimeout(function () { location.reload(); }, 600);
        } else {
            toast((d && d.error) || 'No se pudo completar la acción.', 'err');
        }
    }

    // ── Participantes del proceso (cadena de personas, en orden) ──────
    var partData = { contactos: [], participantes: [] };
    var partState = [];
    var partNames = {};

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function initParticipantes() {
        var raw = document.getElementById('srPartData');
        var box = document.getElementById('srPartBox');
        if (!raw || !box) return;
        try { partData = JSON.parse(raw.textContent || '{}'); } catch (e) { return; }
        (partData.contactos || []).forEach(function (c) { partNames[c.id] = c.name; });
        partState = (partData.participantes || []).slice();
        renderParticipantes();
        syncPartVisible();
    }

    // El editor solo tiene sentido en modo 'personas': se muestra u oculta
    // según lo que haya elegido el usuario en el desplegable, sin recargar.
    function syncPartVisible() {
        var box = document.getElementById('srPartBox');
        var sel = document.getElementById('srPolModo');
        if (!box) return;
        var modo = sel ? sel.value : (box.dataset.abierto === '1' ? 'personas' : '');
        box.classList.toggle('is-open', modo === 'personas');
        var capas = document.getElementById('srPolCapas');
        if (capas) capas.style.display = (modo === 'secuencial') ? '' : 'none';
    }

    function renderParticipantes() {
        var chain = document.getElementById('srPartChain');
        var pool = document.getElementById('srPartPool');
        if (!chain) return;
        chain.innerHTML = partState.length
            ? partState.map(function (id, i) {
                var ultimo = (i === partState.length - 1);
                return '<div class="sr-chain-item' + (ultimo ? ' es-final' : '') + '">' +
                    '<span class="sr-chain-num">' + (i + 1) + '</span>' +
                    '<span class="sr-chain-name">' + esc(partNames[id] || id) + '</span>' +
                    (ultimo ? '<span class="sr-chain-tag">máxima autoridad</span>' : '') +
                    '<button type="button" class="sr-chain-x" data-part-rm="' + id +
                    '" title="Quitar">&times;</button></div>';
            }).join('')
            : '<p class="sr-muted sr-mini">Sin participantes designados todavía.</p>';
        if (!pool) return;
        var libres = (partData.contactos || []).filter(function (c) {
            return partState.indexOf(c.id) === -1;
        });
        pool.innerHTML = libres.length
            ? libres.map(function (c) {
                var niv = c.nivel ? ' · nivel ' + c.nivel : '';
                return '<button type="button" class="sr-chain-add" data-part-add="' +
                    c.id + '">+ ' + esc(c.name) + esc(niv) + '</button>';
            }).join('')
            : '<p class="sr-muted sr-mini">No quedan contactos por añadir.</p>';
    }

    root.addEventListener('change', function (ev) {
        if (ev.target && ev.target.id === 'srPolModo') syncPartVisible();
    });

    root.addEventListener('click', function (ev) {
        // Añadir / quitar participante (no usan data-act)
        var add = ev.target.closest('[data-part-add]');
        if (add) {
            var idA = parseInt(add.dataset.partAdd, 10);
            if (partState.indexOf(idA) === -1) partState.push(idA);
            renderParticipantes();
            return;
        }
        var rm = ev.target.closest('[data-part-rm]');
        if (rm) {
            var idR = parseInt(rm.dataset.partRm, 10);
            partState = partState.filter(function (x) { return x !== idR; });
            renderParticipantes();
            return;
        }

        var btn = ev.target.closest('[data-act]');
        if (!btn) return;
        var act = btn.dataset.act;

        if (act === 'guardar-participantes') {
            btn.classList.add('is-loading');
            post('/my/proceso/' + proceso + '/revisores',
                 { partner_ids: partState.join(',') })
                .then(function (d) { done(btn, d, 'Participantes guardados.'); })
                .catch(function () { done(btn, null); });
            return;
        }

        if (act === 'guardar-politica') {
            var modo = document.getElementById('srPolModo').value;
            var capas = document.getElementById('srPolCapas').value || '1';
            if (modo === 'personas' && !partState.length) {
                toast('Designa al menos un participante.', 'err');
                return;
            }
            btn.classList.add('is-loading');
            // En modo 'personas' hay que guardar la cadena ANTES del modo: el
            // servidor rechaza el modo si todavía no hay participantes.
            var previo = (modo === 'personas')
                ? post('/my/proceso/' + proceso + '/revisores',
                       { partner_ids: partState.join(',') })
                : Promise.resolve({ ok: true });
            previo.then(function (r) {
                if (!r || !r.ok) { done(btn, r); return; }
                return post('/my/proceso/' + proceso + '/politica',
                            { modo: modo, capas: capas })
                    .then(function (d) { done(btn, d, 'Política guardada.'); });
            }).catch(function () { done(btn, null); });
            return;
        }
        if (act === 'toggle-solicitar') {
            var box = document.getElementById('srSolicitarBox');
            if (box) box.classList.toggle('is-open');
            return;
        }
        if (act === 'enviar-solicitud') {
            var dias = document.getElementById('srSolDias').value;
            if (!dias || parseInt(dias, 10) <= 0) return toast('Indica los días adicionales.', 'err');
            var motivo = document.getElementById('srSolMotivo').value || '';
            btn.classList.add('is-loading');
            post('/my/proceso/' + proceso + '/solicitar-plazo', { dias: dias, motivo: motivo })
                .then(function (d) { done(btn, d, 'Solicitud enviada.'); })
                .catch(function () { done(btn, null); });
            return;
        }
        if (act === 'autorizar' || act === 'decidir') {
            var row = btn.closest('.sr-sol-row');
            if (!row) return;
            var url = act === 'autorizar'
                ? '/my/solicitud/' + row.dataset.sol + '/autorizar'
                : '/my/solicitud/' + row.dataset.sol + '/decidir';
            btn.classList.add('is-loading');
            post(url, { decision: btn.dataset.decision })
                .then(function (d) { done(btn, d, 'Hecho.'); })
                .catch(function () { done(btn, null); });
        }
    });

    initParticipantes();
})();
