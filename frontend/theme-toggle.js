/* Light / dark theme switch.

   The choice is stored per browser and applied as `data-theme` on <html>. The
   light palette lives in theme-light.css, which only recolours things, so no
   component moves or resizes when the theme changes. */
(function () {
  'use strict';

  var KEY = 'tt-theme';
  var root = document.documentElement;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function apply(theme) {
    if (theme === 'light') root.setAttribute('data-theme', 'light');
    else root.removeAttribute('data-theme');
    var button = document.getElementById('theme-toggle');
    if (button) {
      var light = theme === 'light';
      button.setAttribute('aria-pressed', String(light));
      button.setAttribute('aria-label', light ? 'Switch to dark mode' : 'Switch to light mode');
      button.setAttribute('title', light ? 'Dark theme' : 'Light theme');
    }
    try { localStorage.setItem(KEY, theme); } catch (e) { /* private mode */ }
  }

  function wire() {
    var button = document.getElementById('theme-toggle');
    if (button) {
      button.addEventListener('click', function () {
        apply(root.getAttribute('data-theme') === 'light' ? 'dark' : 'light');
      });
    }
    // Re-apply so the button glyph matches a theme restored before load.
    apply(root.getAttribute('data-theme') === 'light' ? 'light' : 'dark');
  }

  // Apply before first paint so there is no flash of the wrong theme.
  var saved = stored();
  if (saved === 'light') root.setAttribute('data-theme', 'light');

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
