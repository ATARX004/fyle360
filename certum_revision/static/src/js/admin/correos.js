/* Certum Global · Revisión · Panel de avisos por correo
   Guardado y prueba por AJAX, sin recargar la página. */
(function () {
    'use strict';

    var form = document.getElementById('srCorreosForm');
    if (!form) return;

    var api = window.srPortal || {};
    var toast = api.toast || function (m) { alert(m); };
    var postForm = api.postForm;
    var withLoading = api.withLoading || function (b, p) { return p; };

    // Los interruptores por evento viajan como una lista de códigos activos:
    // así el servidor no tiene que adivinar qué casillas existen, y añadir un
    // aviso nuevo al catálogo no obliga a tocar este archivo.
    function activos() {
        return Array.prototype.slice
            .call(form.querySelectorAll('.sr-ev-on'))
            .filter(function (c) { return c.checked; })
            .map(function (c) { return c.dataset.code; })
            .join(',');
    }

    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-act]');
        if (!btn) return;
        var act = btn.dataset.act;

        if (act === 'correos-guardar') {
            if (!postForm) { form.submit(); return; }
            var fd = new FormData(form);
            fd.set('activos', activos());
            fd.set('enviar', document.getElementById('srEnviar').checked ? '1' : '0');
            withLoading(btn, postForm('/my/certum/admin/correos/guardar', fd)
                .then(function (d) {
                    if (d && d.ok) toast('Configuración guardada.', 'ok');
                    else toast((d && d.error) || 'No se pudo guardar.', 'err');
                }));
            return;
        }

        if (act === 'correos-prueba') {
            var el = document.getElementById('srPruebaPara');
            var para = (el && el.value || '').trim();
            if (!para) return toast('Indica una dirección de correo.', 'err');
            if (!postForm) return;
            var fdP = new FormData();
            fdP.append('para', para);
            fdP.append('csrf_token', form.querySelector('[name=csrf_token]').value);
            withLoading(btn, postForm('/my/certum/admin/correos/prueba', fdP)
                .then(function (d) {
                    if (d && d.ok) toast(d.mensaje || 'Correo de prueba enviado.', 'ok');
                    else toast((d && d.error) || 'No se pudo enviar.', 'err');
                }));
            return;
        }
    });

    // El interruptor general apaga visualmente la lista de avisos: con el
    // envío desactivado, marcar eventos no hace nada y conviene que se vea.
    var general = document.getElementById('srEnviar');
    var lista = form.querySelector('.sr-ev-list');
    function sincronizar() {
        if (lista) lista.classList.toggle('is-off', !general.checked);
    }
    if (general && lista) {
        general.addEventListener('change', sincronizar);
        sincronizar();
    }
})();
