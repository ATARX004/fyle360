/* ═══════════════════════════════════════════════════════════════════
   Certum Global · Revisión · Gestión del proceso
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

    root.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-act]');
        if (!btn) return;
        var act = btn.dataset.act;

        if (act === 'guardar-politica') {
            var modo = document.getElementById('srPolModo').value;
            var capas = document.getElementById('srPolCapas').value || '1';
            btn.classList.add('is-loading');
            post('/my/proceso/' + proceso + '/politica', { modo: modo, capas: capas })
                .then(function (d) { done(btn, d, 'Política guardada.'); })
                .catch(function () { done(btn, null); });
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
})();
