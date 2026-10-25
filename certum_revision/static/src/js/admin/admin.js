/* ═══════════════════════════════════════════════════════════════════
   FYLE 360 · Panel de administración (vanilla JS, sin dependencias)
   - Pestañas por #ancla dentro de una pantalla (data-sr-pestanas)
   - Formularios data-sr-ajax: se envían sin recargar; la respuesta trae
     el aviso, los errores por campo y los trozos data-sr-fragmento
   - data-sr-confirmar: pide confirmación antes de enviar (con o sin AJAX)
   - Marcar todos + contador (data-sr-marcar-todo / -grupo / -contador)
   Reutiliza toast y withLoading de window.srPortal (portal_base.js).
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var panel = document.querySelector('.sr-adm');
    if (!panel) return;

    var api = window.srPortal || {};
    var toast = api.toast || function (m) { window.alert(m); };
    var withLoading = api.withLoading || function (b, p) { return p; };

    // ── Pestañas ─────────────────────────────────────────────────────
    var barra = panel.querySelector('[data-sr-pestanas]');
    var secciones = Array.prototype.slice.call(panel.querySelectorAll('.sr-adm-seccion'));

    function mostrar(id, enfocar) {
        if (!barra || !secciones.length) return;
        var existe = secciones.some(function (s) { return s.id === id; });
        if (!existe) id = secciones[0].id;
        secciones.forEach(function (s) { s.hidden = s.id !== id; });
        barra.querySelectorAll('[data-sr-pestana]').forEach(function (a) {
            var on = a.dataset.srPestana === id;
            a.classList.toggle('is-on', on);
            a.setAttribute('aria-selected', on ? 'true' : 'false');
            if (on && enfocar) a.focus();
        });
    }

    // Al cambiar de pestaña la página no salta hasta la sección: la barra
    // queda donde estaba, justo debajo de la navegación.
    function alinearBarra() {
        var arriba = barra.getBoundingClientRect().top;
        if (arriba < 90 || arriba > window.innerHeight * 0.6) {
            window.scrollTo(0, window.scrollY + arriba - 100);
        }
    }

    if (barra) {
        panel.classList.add('con-pestanas');
        if (location.hash) {
            mostrar(location.hash.slice(1));
            // El navegador ya saltó al ancla antes de que corriera esto.
            setTimeout(alinearBarra, 0);
        } else {
            mostrar('');
        }
        barra.addEventListener('click', function (ev) {
            var tab = ev.target.closest('[data-sr-pestana]');
            if (!tab) return;
            ev.preventDefault();
            history.replaceState(null, '', '#' + tab.dataset.srPestana);
            mostrar(tab.dataset.srPestana);
            alinearBarra();
        });
        window.addEventListener('hashchange', function () {
            mostrar((location.hash || '').slice(1));
        });
        // Flechas izquierda/derecha entre pestañas, como en una tablist.
        barra.addEventListener('keydown', function (ev) {
            if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
            var tabs = Array.prototype.slice.call(barra.querySelectorAll('[data-sr-pestana]'));
            var i = tabs.indexOf(document.activeElement);
            if (i < 0) return;
            var j = (i + (ev.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
            history.replaceState(null, '', '#' + tabs[j].dataset.srPestana);
            mostrar(tabs[j].dataset.srPestana, true);
            ev.preventDefault();
        });
    }

    // ── Marcar todos ─────────────────────────────────────────────────
    function contar(grupo) {
        var n = panel.querySelectorAll('[data-sr-grupo="' + grupo + '"]:checked').length;
        panel.querySelectorAll('[data-sr-contador="' + grupo + '"]').forEach(function (c) {
            c.textContent = n;
        });
    }

    panel.addEventListener('change', function (ev) {
        var t = ev.target;
        if (t.dataset.srMarcarTodo) {
            panel.querySelectorAll('[data-sr-grupo="' + t.dataset.srMarcarTodo + '"]').forEach(function (c) {
                c.checked = t.checked;
            });
            contar(t.dataset.srMarcarTodo);
        } else if (t.dataset.srGrupo) {
            contar(t.dataset.srGrupo);
        }
    });

    // ── Formularios ──────────────────────────────────────────────────
    function limpiarErrores(form) {
        form.querySelectorAll('.is-invalid').forEach(function (el) { el.classList.remove('is-invalid'); });
        form.querySelectorAll('.sr-adm-error').forEach(function (el) { el.remove(); });
    }

    function marcarErrores(form, errores) {
        var primero = null;
        Object.keys(errores || {}).forEach(function (campo) {
            var input = form.querySelector('[name="' + campo + '"], [data-sr-campo="' + campo + '"]');
            if (!input) return;
            input.classList.add('is-invalid');
            input.setAttribute('aria-invalid', 'true');
            var msg = document.createElement('small');
            msg.className = 'sr-adm-error';
            msg.textContent = errores[campo];
            input.insertAdjacentElement('afterend', msg);
            primero = primero || input;
        });
        if (primero) primero.focus();
    }

    function repintar(fragmentos) {
        Object.keys(fragmentos || {}).forEach(function (nombre) {
            panel.querySelectorAll('[data-sr-fragmento="' + nombre + '"]').forEach(function (el) {
                el.innerHTML = fragmentos[nombre];
            });
        });
        // Lo repintado vuelve con sus casillas desmarcadas.
        panel.querySelectorAll('[data-sr-contador]').forEach(function (c) {
            contar(c.dataset.srContador);
        });
    }

    function actualizarResumen(form) {
        // Al guardar una plantilla, su cabecera refleja si quedó activa.
        var caso = form.closest('.sr-adm-caso');
        var check = form.querySelector('input[name="activo"]');
        if (!caso || !check) return;
        var pill = caso.querySelector('summary .sr-adm-pill');
        if (!pill) return;
        pill.dataset.tono = check.checked ? 'ok' : 'neutro';
        pill.textContent = check.checked ? 'Activa' : 'Desactivada';
    }

    panel.addEventListener('submit', function (ev) {
        var form = ev.target;
        var pregunta = form.dataset.srConfirmar;
        if (pregunta && !window.confirm(pregunta)) {
            ev.preventDefault();
            return;
        }
        if (!form.dataset.srAjax) return;  // envío normal: recarga con el aviso
        ev.preventDefault();
        var boton = form.querySelector('[type="submit"]') || form;
        limpiarErrores(form);
        var envio = fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        }).then(function (resp) {
            return resp.json().catch(function () {
                return { ok: false, error: 'Respuesta inesperada del servidor. Recargue la página.' };
            });
        }).then(function (d) {
            if (d.ok) {
                toast(d.mensaje || 'Hecho.', 'ok');
                actualizarResumen(form);
                repintar(d.fragmentos);
            } else {
                toast(d.error || 'No se pudo completar.', 'err');
                marcarErrores(form, d.errores);
            }
        }).catch(function () {
            toast('Sin conexión con el servidor. Inténtelo de nuevo.', 'err');
        });
        if (boton.classList) withLoading(boton, envio);
    });
})();
