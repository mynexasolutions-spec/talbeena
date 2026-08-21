// Prevent Turbo from intercepting admin links
    document.addEventListener("turbo:click", function(e) {
      const link = e.target.closest("a");
      if (link && link.getAttribute("href")?.startsWith("/admin")) {
        e.preventDefault();
        window.location.href = link.href;
      }
    });

    // Re-initialize nav interactions on every Turbo navigation
    document.addEventListener("turbo:load", initNav);

    // Document-level click-outside handler (registered once, uses live lookups)
    document.addEventListener('click', function(e) {
      var m = document.getElementById('mobileMenu');
      var h = document.getElementById('hamburger');
      if (m && m.classList.contains('open') && !e.target.closest('.main-nav') && !e.target.closest('.mobile-menu')) {
        m.classList.remove('open');
        if (h) h.classList.remove('open');
      }
      var msb = document.getElementById('mobileSearchBar');
      if (msb && msb.classList.contains('open') && !e.target.closest('.mobile-search-bar') && !e.target.closest('.search-toggle-btn')) {
        msb.classList.remove('open');
      }
    });

    function initNav() {
      var h = document.getElementById('hamburger');
      var m = document.getElementById('mobileMenu');
      if (h && m && !h.dataset.navBound) {
        h.dataset.navBound = '1';
        h.addEventListener('click', function(e) {
          e.stopPropagation();
          h.classList.toggle('open');
          m.classList.toggle('open');
        });
      }
      var sb = document.getElementById('searchToggleBtn');
      var msb = document.getElementById('mobileSearchBar');
      if (sb && msb && !sb.dataset.searchBound) {
        sb.dataset.searchBound = '1';
        sb.addEventListener('click', function(e) {
          e.stopPropagation();
          msb.classList.toggle('open');
        });
      }
    }

    // Call directly for initial page load (turbo:load may fire before this script)
    initNav();
