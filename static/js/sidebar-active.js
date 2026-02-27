/**
 * Sidebar Active State & Mobile Toggle
 * ─────────────────────────────────────
 * Automatically highlights the current nav item
 * and handles mobile sidebar open/close.
 */
(function () {
    'use strict';

    // ─── Active State ───
    const path = window.location.pathname;
    const navItems = document.querySelectorAll('.sidebar .nav-item[data-nav]');

    // Map data-nav values to URL patterns
    const navPatterns = {
        dashboard:     ['/dashboard', '/home', '/'],
        collections:   ['/collections'],
        drawings:      ['/drawings', '/technical-drawings'],
        suppliers:     ['/suppliers', '/fornecedores'],
        oaz_banco:     ['/oaz-banco', '/oaz_banco'],
        activity_logs: ['/activity-logs', '/activity_logs'],
        settings:      ['/settings', '/configuracoes'],
        fichas:        ['/fichas'],
    };

    let matched = false;

    navItems.forEach(item => {
        item.classList.remove('active');

        const nav = item.getAttribute('data-nav');
        const patterns = navPatterns[nav] || [];

        for (const pattern of patterns) {
            if (path === pattern || path.startsWith(pattern + '/')) {
                item.classList.add('active');
                matched = true;
                return;
            }
        }
    });

    // Fallback: match by href comparison
    if (!matched) {
        navItems.forEach(item => {
            const href = item.getAttribute('href');
            if (href && href !== '#' && (path === href || path.startsWith(href))) {
                item.classList.add('active');
            }
        });
    }

    // ─── Mobile Toggle ───
    const menuBtn = document.getElementById('mobileMenuBtn');
    const sidebar = document.getElementById('sidebar');

    if (menuBtn && sidebar) {
        menuBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });

        // Close sidebar when clicking outside
        document.addEventListener('click', (e) => {
            if (sidebar.classList.contains('open') &&
                !sidebar.contains(e.target) &&
                !menuBtn.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }
})();
