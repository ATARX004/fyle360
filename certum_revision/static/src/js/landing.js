/* FYLE 360 · Landing pública (/fyle360)
   - Barra superior con fondo al desplazarse y botón flotante de WhatsApp
   - Bloques que aparecen al entrar en pantalla (una vez)
   - Escenas animadas que explican el producto sin texto largo. Cada escena
     corre solo mientras se ve (IntersectionObserver) y se pausa al salir:
       ciclo   el anillo del logo: publica → revisa → corrige → aprueba
       flujo   el documento viaja entre los carriles del proveedor y el cliente
       panel   el inicio de la plataforma, como cliente o como proveedor
       avisos  los correos entran en la bandeja uno a uno
   Sin dependencias. Con prefers-reduced-motion se muestra el estado final. */
(function () {
    'use strict';

    var quieto = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var nav = document.querySelector('.fl-nav');
    var flota = document.querySelector('.fl-wa-flota');
    var hero = document.querySelector('.fl-hero');

    function alDesplazar() {
        var y = window.scrollY;
        if (nav) nav.classList.toggle('is-scrolled', y > 20);
        if (flota && hero) flota.classList.toggle('is-visible', y > hero.offsetHeight * 0.7);
    }
    window.addEventListener('scroll', alDesplazar, { passive: true });
    alDesplazar();

    var bloques = document.querySelectorAll('[data-revela]');
    if ('IntersectionObserver' in window && !quieto) {
        var obsBloques = new IntersectionObserver(function (entradas) {
            entradas.forEach(function (e) {
                if (e.isIntersecting) {
                    e.target.classList.add('is-visto');
                    obsBloques.unobserve(e.target);
                }
            });
        }, { threshold: 0.15 });
        bloques.forEach(function (b) { obsBloques.observe(b); });
    } else {
        bloques.forEach(function (b) { b.classList.add('is-visto'); });
    }

    // ── Escenas ──────────────────────────────────────────────────────
    // Cada una es {pasos, ms, pintar(i)}: pintar dibuja el paso i.
    function escena(el, pasos, ms, pintar) {
        var i = 0, reloj = null;
        pintar(0);
        if (quieto) { pintar(pasos - 1); return; }
        function arrancar() {
            if (reloj) return;
            reloj = setInterval(function () {
                if (document.hidden) return;
                i = (i + 1) % pasos;
                pintar(i);
            }, ms);
        }
        function parar() { clearInterval(reloj); reloj = null; }
        if ('IntersectionObserver' in window) {
            new IntersectionObserver(function (e) {
                if (e[0].isIntersecting) arrancar(); else parar();
            }, { threshold: 0.3 }).observe(el);
        } else {
            arrancar();
        }
        return { reiniciar: function () { i = 0; pintar(0); } };
    }

    // El ciclo del héroe.
    var ciclo = document.querySelector('.fl-ciclo');
    if (ciclo) {
        var CICLO = [
            { id: 'publica', texto: 'Publicado hoy' },
            { id: 'revisa', texto: 'En revisión, quedan 3 días' },
            { id: 'corrige', texto: 'Observado: falta una firma' },
            { id: 'aprueba', texto: 'Aprobado' }
        ];
        var estado = ciclo.querySelector('.fl-doc-estado');
        escena(ciclo, CICLO.length, 2400, function (i) {
            ciclo.querySelectorAll('[data-paso]').forEach(function (el) {
                el.classList.toggle('is-on', el.dataset.paso === CICLO[i].id);
            });
            estado.dataset.estado = CICLO[i].id;
            estado.textContent = CICLO[i].texto;
        });
    }

    // Los carriles: la ficha salta de hito en hito y la ruta se va dibujando.
    var flujo = document.querySelector('[data-escena="flujo"]');
    if (flujo) {
        var HITOS = [
            { x: '14%', y: '28%', ruta: 0, nota: 'El proveedor sube el documento y al revisor le llega el aviso.' },
            { x: '36%', y: '72%', ruta: 26, nota: 'El cliente lo revisa dentro de su plazo.' },
            { x: '58%', y: '28%', ruta: 52, nota: '¿Observado? Vuelve al proveedor con el comentario.' },
            { x: '80%', y: '72%', ruta: 78, nota: 'La corrección vuelve a quien observó, y se aprueba.' },
            { x: '95%', y: '50%', ruta: 100, nota: 'Lo aprobado queda en el repositorio, listo para difundir.' }
        ];
        var ficha = flujo.querySelector('.fl-ficha');
        var ruta = flujo.querySelector('.fl-ruta-viva');
        var nota = flujo.querySelector('.fl-carril-nota');
        escena(flujo, HITOS.length + 1, 1900, function (i) {
            // El paso extra es una pausa con todo recorrido antes de volver.
            var h = HITOS[Math.min(i, HITOS.length - 1)];
            ficha.style.setProperty('--x', h.x);
            ficha.style.setProperty('--y', h.y);
            ruta.style.strokeDasharray = h.ruta + ' 100';
            nota.textContent = h.nota;
            flujo.querySelectorAll('.fl-hito').forEach(function (el) {
                var n = parseInt(el.dataset.hito, 10);
                var actual = Math.min(i, HITOS.length - 1);
                el.classList.toggle('is-on', n === actual);
                el.classList.toggle('is-hecho', n < actual);
            });
        });
    }

    // El panel: los estados cambian solos y el anillo crece. El botón de rol
    // cambia lo que la persona tiene pendiente.
    var panel = document.querySelector('[data-escena="panel"]');
    if (panel) {
        var filas = panel.querySelectorAll('.fl-app-lista li');
        var anillo = panel.querySelector('.fl-app-anillo-v');
        var pct = panel.querySelector('.fl-app-anillo span');
        var ETIQ = { pendiente: 'Pendiente', publicado: 'Publicado', observado: 'Observado', aprobado: 'Aprobado' };
        // Estados de las cuatro filas en cada paso.
        var GUION = [
            ['pendiente', 'pendiente', 'pendiente', 'pendiente'],
            ['publicado', 'pendiente', 'pendiente', 'pendiente'],
            ['publicado', 'publicado', 'pendiente', 'pendiente'],
            ['aprobado', 'publicado', 'publicado', 'pendiente'],
            ['aprobado', 'observado', 'publicado', 'publicado'],
            ['aprobado', 'publicado', 'aprobado', 'publicado'],
            ['aprobado', 'aprobado', 'aprobado', 'aprobado']
        ];
        var anterior = GUION[0];
        escena(panel, GUION.length + 1, 1500, function (i) {
            var paso = GUION[Math.min(i, GUION.length - 1)];
            var aprobados = 0;
            filas.forEach(function (li, n) {
                var em = li.querySelector('em');
                if (paso[n] !== anterior[n]) {
                    li.classList.add('is-cambio');
                    setTimeout(function () { li.classList.remove('is-cambio'); }, 700);
                }
                em.dataset.estado = paso[n];
                em.textContent = ETIQ[paso[n]];
                if (paso[n] === 'aprobado') aprobados++;
            });
            anterior = paso;
            var v = Math.round(aprobados / filas.length * 100);
            anillo.style.strokeDasharray = v + ' 100';
            pct.textContent = v + '%';
        });
        var botones = document.querySelectorAll('.fl-rol button');
        botones.forEach(function (b) {
            b.addEventListener('click', function () {
                var rol = b.dataset.rol;
                botones.forEach(function (o) {
                    o.classList.toggle('is-on', o === b);
                    o.setAttribute('aria-selected', o === b ? 'true' : 'false');
                });
                panel.dataset.rol = rol;
                var small = panel.querySelector('.fl-app-cab small');
                var num = panel.querySelector('.fl-app-cab strong');
                small.textContent = small.getAttribute('data-txt-' + rol);
                num.textContent = num.getAttribute('data-num-' + rol);
            });
        });
    }

    // La bandeja: entra un correo cada poco; al final se vacía y empieza.
    var bandeja = document.querySelector('[data-escena="avisos"]');
    if (bandeja) {
        var correos = bandeja.querySelectorAll('.fl-correo');
        escena(bandeja, correos.length + 2, 1300, function (i) {
            correos.forEach(function (c, n) {
                c.classList.toggle('is-visible', n < i);
                c.classList.toggle('is-nuevo', n === i - 1);
            });
        });
    }
})();
