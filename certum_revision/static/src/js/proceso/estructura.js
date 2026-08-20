/* ═══════════════════════════════════════════════════════════════════
   Certum Global · Revisión · Reorganizar un expediente ya iniciado
   - Modo edición sobre la vista de directorio
   - Crear, renombrar, mover y quitar carpetas y documentos
   - Guardar la estructura resultante como una plantilla NUEVA
   Mover NO altera el curso: estados, archivos, plazos, comentarios y
   trazabilidad viajan con el documento, no con la carpeta.
   ═══════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var dir = document.getElementById('srItems');
    var gest = document.getElementById('srProcGestion');
    if (!dir || !gest) return;
    var PROC = gest.dataset.proceso;

    var destinos = [];
    var raw = document.getElementById('srDestinos');
    if (raw) {
        try { destinos = JSON.parse(raw.textContent || '[]'); } catch (e) { destinos = []; }
    }

    function csrf() {
        var e = document.getElementById('srCsrf');
        return e ? e.value : '';
    }

    function toast(msg, tipo) {
        var box = document.getElementById('srToasts');
        if (!box) { if (tipo === 'err') window.alert(msg); return; }
        var t = document.createElement('div');
        t.className = 'sr-toast ' + (tipo || 'ok');
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
            body: fd
        }).then(function (r) {
            return r.json().catch(function () {
                return { ok: false, error: 'Respuesta inesperada del servidor.' };
            });
        });
    }

    // Toda operación termina recargando: la estructura cambia el árbol entero
    // (rutas, contadores, avance), y rehacerlo en el navegador se desincroniza.
    function hecho(d, msg) {
        if (d && d.ok) {
            toast(msg, 'ok');
            setTimeout(function () { window.location.reload(); }, 500);
        } else {
            toast((d && d.error) || 'No se pudo completar la acción.', 'err');
        }
    }

    function url(sufijo) {
        return '/my/proceso/' + PROC + sufijo;
    }

    // Selector de destino: se pide por prompt con la lista numerada. Es simple
    // y funciona igual en móvil que en escritorio; el arrastrar y soltar puede
    // venir después si hace falta.
    function pedirDestino(titulo, excluirRama) {
        var opciones = destinos.filter(function (c) {
            // Al mover una carpeta no puede ofrecerse a sí misma ni a su
            // descendencia: seria un ciclo.
            return !excluirRama || c.rama.indexOf(excluirRama) !== 0;
        });
        var lineas = [titulo, '', '0 = raíz (sin carpeta)'];
        opciones.forEach(function (c, i) {
            lineas.push((i + 1) + ' = ' + c.ruta);
        });
        lineas.push('', 'Escribe el número del destino:');
        var resp = window.prompt(lineas.join('\n'), '0');
        if (resp === null) return undefined;          // cancelado
        var n = parseInt(resp, 10);
        if (isNaN(n) || n < 0 || n > opciones.length) {
            toast('Número de destino no válido.', 'err');
            return undefined;
        }
        return n === 0 ? '' : String(opciones[n - 1].id);
    }

    // ── Modo edición ─────────────────────────────────────────────────
    function toggleEdicion() {
        var on = document.body.classList.toggle('sr-editando');
        var chip = document.querySelector('[data-act="toggle-edicion"]');
        if (chip) chip.classList.toggle('is-active', on);
    }

    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-act]');
        if (!btn) return;
        var act = btn.dataset.act;
        var id = btn.dataset.id;
        var nombre = btn.dataset.name || 'este elemento';

        if (act === 'toggle-edicion') {
            ev.preventDefault();
            return toggleEdicion();
        }

        // Las acciones de estructura no deben abrir el panel del documento
        // ni plegar la carpeta sobre la que se pulsa.
        var propias = ['sub-carpeta', 'renombrar-carpeta', 'mover-carpeta',
                       'eliminar-carpeta', 'mover-item', 'eliminar-item',
                       'nueva-carpeta-raiz', 'nuevo-doc', 'guardar-plantilla'];
        if (propias.indexOf(act) === -1) return;
        ev.preventDefault();
        ev.stopPropagation();

        if (act === 'nueva-carpeta-raiz' || act === 'sub-carpeta') {
            var nom = window.prompt(act === 'sub-carpeta'
                ? 'Nombre de la subcarpeta dentro de "' + nombre + '":'
                : 'Nombre de la nueva carpeta:', '');
            if (!nom || !nom.trim()) return;
            var datos = { name: nom.trim() };
            if (act === 'sub-carpeta') datos.parent_id = id;
            return post(url('/carpeta/crear'), datos)
                .then(function (d) { hecho(d, 'Carpeta creada.'); });
        }

        if (act === 'renombrar-carpeta') {
            var nuevo = window.prompt('Nuevo nombre de la carpeta:', nombre);
            if (!nuevo || !nuevo.trim() || nuevo === nombre) return;
            return post(url('/carpeta/' + id + '/editar'), { name: nuevo.trim() })
                .then(function (d) { hecho(d, 'Carpeta renombrada.'); });
        }

        if (act === 'mover-carpeta') {
            var propia = destinos.filter(function (c) {
                return String(c.id) === String(id);
            })[0];
            var destino = pedirDestino(
                'Mover la carpeta "' + nombre + '" dentro de:',
                propia ? propia.rama : null);
            if (destino === undefined) return;
            return post(url('/carpeta/' + id + '/mover'), { parent_id: destino })
                .then(function (d) { hecho(d, 'Carpeta movida.'); });
        }

        if (act === 'eliminar-carpeta') {
            if (!window.confirm('¿Eliminar la carpeta "' + nombre + '"?\n\n' +
                    'Se eliminan también sus subcarpetas. Los documentos NO se ' +
                    'borran: quedan sin carpeta, conservando su estado y su ' +
                    'historial.')) return;
            return post(url('/carpeta/' + id + '/eliminar'), {})
                .then(function (d) { hecho(d, 'Carpeta eliminada.'); });
        }

        if (act === 'nuevo-doc') {
            var dn = window.prompt('Nombre del nuevo documento:', '');
            if (!dn || !dn.trim()) return;
            var dest = pedirDestino('Guardar "' + dn.trim() + '" en:');
            if (dest === undefined) return;
            return post(url('/item/crear'), { name: dn.trim(), carpeta_id: dest })
                .then(function (d) {
                    hecho(d, 'Documento añadido. El avance del expediente se ' +
                             'recalcula con el nuevo total.');
                });
        }

        if (act === 'mover-item') {
            var destino2 = pedirDestino('Mover "' + nombre + '" a:');
            if (destino2 === undefined) return;
            return post(url('/item/' + id + '/mover'), { carpeta_id: destino2 })
                .then(function (d) { hecho(d, 'Documento movido. Su revisión sigue igual.'); });
        }

        if (act === 'eliminar-item') {
            if (btn.dataset.limpio !== '1') {
                return toast('Solo se pueden quitar documentos pendientes y sin ' +
                             'historial. Este ya tiene archivos, comentarios o ' +
                             'trazabilidad.', 'err');
            }
            if (!window.confirm('¿Quitar el documento "' + nombre + '" del expediente?')) return;
            return post(url('/item/' + id + '/eliminar'), {})
                .then(function (d) { hecho(d, 'Documento quitado.'); });
        }

        if (act === 'guardar-plantilla') {
            var sugerido = (document.querySelector('.sr-proc-head-info h1') || {}).textContent || '';
            var nombrePlantilla = window.prompt(
                'Nombre de la plantilla NUEVA.\n\n' +
                'La plantilla original no se toca: se crea una copia aparte y ' +
                'tú decides después si retiras la antigua.',
                (sugerido.trim() || 'Plantilla') + ' (rev.)');
            if (nombrePlantilla === null) return;
            btn.classList.add('is-loading');
            return post(url('/guardar-plantilla'), { name: nombrePlantilla })
                .then(function (d) {
                    btn.classList.remove('is-loading');
                    if (!d || !d.ok) {
                        return toast((d && d.error) || 'No se pudo guardar.', 'err');
                    }
                    toast('Plantilla ' + d.code + ' creada.', 'ok');
                    setTimeout(function () { window.location = d.redirect; }, 700);
                });
        }
    });
})();
