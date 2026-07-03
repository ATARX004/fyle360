/* Certum Global · Revisión · Hub: contadores animados de los KPIs */
(function () {
    'use strict';

    function animateCounters() {
        var counters = document.querySelectorAll('.sr-kpi-value[data-count]');
        if (!counters.length) return;
        counters.forEach(function (el) {
            var target = parseInt(el.dataset.count || '0', 10);
            if (!target) { el.textContent = '0'; return; }
            var dur = 900, start = null;
            function tick(ts) {
                if (!start) start = ts;
                var p = Math.min((ts - start) / dur, 1);
                // easeOutCubic
                var eased = 1 - Math.pow(1 - p, 3);
                el.textContent = Math.round(target * eased);
                if (p < 1) requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        });
    }

    if (document.readyState !== 'loading') animateCounters();
    else document.addEventListener('DOMContentLoaded', animateCounters);
})();
