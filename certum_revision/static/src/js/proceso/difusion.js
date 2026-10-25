/* FYLE 360 · Difundir documentación aprobada
   Modal para elegir documentos y personas del cliente a quienes entregarles
   la documentación terminada. El correo lleva enlace al repositorio, no
   adjunto, así que difundir es dar PERMISO: por eso confirma antes. */
(function () {
    'use strict';

    var app = document.querySelector('.sr-app');
    if (!app) return;

    var api = window.srPortal || {};
    var toast = api.toast || function (m) { alert(m); };
    var postForm = api.postForm;
    var withLoading = api.withLoading || function (b, p) { return p; };

    var procesoId = (function () {
        var m = window.location.pathname.match(/\/my\/proceso\/(\d+)/);
        return m ? m[1] : null;
    })();

    var modal = null;
    var datos = null;
    // Salto de linea para los avisos de confirm().
    var NL = String.fromCharCode(10);

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function icon(n) {
        return '<svg class="sr-ico" aria-hidden="true"><use href="#' + n + '"/></svg>';
    }

    function cerrar() {
        if (modal) { modal.remove(); modal = null; }
    }

    function marcados(sel) {
        return Array.prototype.slice.call(modal.querySelectorAll(sel))
            .filter(function (c) { return c.checked; })
            .map(function (c) { return c.value; });
    }

    function pintar() {
        var h = '<div class="sr-modal-card sr-dif-card">' +
            '<header class="sr-modal-head">' +
            '<h3>' + icon('i-send') + 'Difundir documentación</h3>' +
            '<button type="button" class="sr-dw-close" data-act="dif-cerrar" ' +
            'aria-label="Cerrar">' + icon('i-x') + '</button></header>' +
            '<div class="sr-dif-cuerpo">';

        if (!datos.documentos.length) {
            h += '<p class="sr-muted">Todavía no hay documentos aprobados que difundir.</p>';
        } else {
            h += '<div class="sr-dif-col"><h4>' + icon('i-doc') + 'Qué se envía</h4>' +
                '<label class="sr-dif-todos"><input type="checkbox" data-todos="doc"/>' +
                '<span>Todos los aprobados</span></label>';
            datos.documentos.forEach(function (d) {
                h += '<label class="sr-dif-row"><input type="checkbox" class="sr-dif-doc" ' +
                    'value="' + d.id + '"/><span class="sr-dif-txt"><b>' + esc(d.name) +
                    '</b><small class="sr-muted">' + esc(d.carpeta || d.archivo) +
                    (d.difundido ? ' · ya difundido a ' + d.difundido + ' persona(s)' : '') +
                    '</small></span></label>';
            });
            h += '</div>';

            h += '<div class="sr-dif-col"><h4>' + icon('i-user') + 'A quién · ' +
                esc(datos.cliente) + '</h4>';
            if (!datos.personas.length) {
                h += '<p class="sr-muted sr-mini">Esta empresa no tiene contactos ' +
                    'registrados. Añádalos en Contactos antes de difundir.</p>';
            } else {
                h += '<label class="sr-dif-todos"><input type="checkbox" data-todos="per"/>' +
                    '<span>Todos los que tienen correo</span></label>';
                datos.personas.forEach(function (p) {
                    // Sin correo no se puede difundir: se muestra deshabilitado
                    // con el motivo, en vez de dejar que falle el envío al final.
                    h += '<label class="sr-dif-row' + (p.listo ? '' : ' is-off') +
                        '"><input type="checkbox" class="sr-dif-per" value="' + p.id +
                        '"' + (p.listo ? '' : ' disabled="disabled"') + '/>' +
                        '<span class="sr-dif-txt"><b>' + esc(p.name) + '</b>' +
                        '<small class="sr-muted">' +
                        (p.listo ? esc(p.email) : 'Sin correo: complételo en el contacto') +
                        (p.listo && !p.tiene_usuario
                            ? ' · <span class="sr-dif-nuevo">se le creará usuario</span>'
                            : '') +
                        '</small></span></label>';
                });
            }
            h += '</div>';

            h += '<label class="sr-field sr-dif-msg"><span>Mensaje (opcional)</span>' +
                '<textarea id="srDifMsg" rows="2" ' +
                'placeholder="Se incluirá en el correo…"></textarea></label>' +
                '<p class="sr-muted sr-mini">' + icon('i-shield') +
                ' El correo lleva un <b>enlace</b>, no el archivo: quien lo reciba verá ' +
                'siempre la versión vigente, y solo él. Quien no tenga usuario del ' +
                'portal recibirá además una invitación para crear su contraseña.</p>';
        }

        if (datos.historial && datos.historial.length) {
            h += '<details class="sr-dif-hist"><summary>Difusiones anteriores</summary>';
            datos.historial.forEach(function (x) {
                h += '<div class="sr-dif-hist-row"><b>' + esc(x.fecha) + '</b> · ' +
                    x.documentos + ' documento(s) a ' + esc(x.personas) +
                    '<small class="sr-muted"> · por ' + esc(x.quien) + '</small></div>';
            });
            h += '</details>';
        }

        h += '</div><footer class="sr-modal-actions">' +
            '<button type="button" class="sr-btn sr-btn-ghost" data-act="dif-cerrar">Cancelar</button>';
        if (datos.documentos.length) {
            h += '<button type="button" class="sr-btn sr-btn-primary" data-act="dif-enviar">' +
                icon('i-send') + 'Difundir</button>';
        }
        h += '</footer></div>';

        modal.innerHTML = h;
    }

    function abrir() {
        if (!procesoId || !postForm) return;
        cerrar();
        modal = document.createElement('div');
        modal.className = 'sr-modal is-open';
        modal.id = 'srDifModal';
        modal.innerHTML = '<div class="sr-modal-card sr-dif-card">' +
            '<p class="sr-muted">Cargando…</p></div>';
        // Dentro de .sr-app: fuera de ahí no existen las variables de color y
        // el modal saldría transparente.
        app.appendChild(modal);

        fetch('/my/proceso/' + procesoId + '/difusion/datos',
              { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d || !d.ok) {
                    toast((d && d.error) || 'No se pudo cargar.', 'err');
                    return cerrar();
                }
                datos = d;
                pintar();
            })
            .catch(function () { toast('Error de conexión.', 'err'); cerrar(); });
    }

    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-act]');
        if (!btn) return;
        var act = btn.dataset.act;

        if (act === 'abrir-difusion') { abrir(); return; }
        if (act === 'dif-cerrar') { cerrar(); return; }

        if (act === 'dif-enviar') {
            var docs = marcados('.sr-dif-doc');
            var pers = marcados('.sr-dif-per');
            if (!docs.length) return toast('Elige al menos un documento.', 'err');
            if (!pers.length) return toast('Elige al menos una persona.', 'err');

            var nuevos = datos.personas.filter(function (p) {
                return !p.tiene_usuario && pers.indexOf(String(p.id)) !== -1;
            }).length;
            // Difundir da acceso permanente a documentacion: se confirma.
            if (!confirm('Se enviará ' + docs.length + ' documento(s) a ' +
                         pers.length + ' persona(s).' + NL + NL +
                         'Podrán consultarlos en el portal en adelante.' +
                         (nuevos ? NL + NL + 'A ' + nuevos + ' de ellas se les creará ' +
                                   'un usuario del portal y recibirán una invitación.'
                                 : '') + NL + NL + '¿Difundir?')) return;

            var fd = new FormData();
            fd.append('item_ids', docs.join(','));
            fd.append('partner_ids', pers.join(','));
            var m = document.getElementById('srDifMsg');
            fd.append('mensaje', (m && m.value) || '');
            withLoading(btn, postForm('/my/proceso/' + procesoId + '/difusion/enviar', fd)
                .then(function (d) {
                    if (!d || !d.ok) return toast((d && d.error) || 'No se pudo difundir.', 'err');
                    toast('Difundido a ' + d.personas + ' persona(s).' +
                          (d.usuarios_creados
                              ? ' Se crearon ' + d.usuarios_creados + ' usuario(s).' : ''), 'ok');
                    cerrar();
                }));
            return;
        }
    });

    // "Todos" de cada columna
    document.addEventListener('change', function (ev) {
        var todos = ev.target.closest('[data-todos]');
        if (!todos || !modal) return;
        var clase = todos.dataset.todos === 'doc' ? '.sr-dif-doc' : '.sr-dif-per';
        modal.querySelectorAll(clase).forEach(function (c) {
            if (!c.disabled) c.checked = todos.checked;
        });
    });

    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && modal) cerrar();
    });

})();
