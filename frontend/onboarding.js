/* First-visit guidance.

   The question cards in #start-modal ("Is my region warming?") are the
   friendliest way into the app, so they are shown once to a new visitor and
   are always one click away afterwards from the header's "Start here" button.

   This deliberately does not rely on the legacy startup sequence, which can
   hide modals while the catalogue and other screens initialise. It retries a
   few times early on, and stops retrying the moment the visitor interacts. */
(function () {
  'use strict';

  var KEY = 'tt-seen-start';
  var shown = false;
  var userActed = false;

  function modal() { return document.getElementById('start-modal'); }

  function seen() {
    try { return localStorage.getItem(KEY) === '1'; } catch (err) { return true; }
  }

  function markSeen() {
    try { localStorage.setItem(KEY, '1'); } catch (err) { /* private mode */ }
  }

  function open() {
    var m = modal();
    if (!m) return false;
    // Clear any stale state first. A leftover "open" class on a hidden modal
    // (which this app can be left in) would otherwise make the dialog look
    // present to guards like ours while never actually showing.
    m.classList.remove('open');
    m.hidden = true;
    void m.offsetWidth;
    if (typeof window.showModal === 'function') window.showModal(m);
    else { m.hidden = false; m.classList.add('open'); }
    var close = document.getElementById('start-close');
    if (close) close.focus();
    return true;
  }

  function anyModalOpen() {
    var modals = document.querySelectorAll('.modal-backdrop');
    for (var i = 0; i < modals.length; i++) {
      var el = modals[i];
      // Judge by what is actually on screen, not by a class name.
      if (el.hidden) continue;
      if (el.offsetWidth || el.offsetHeight) return true;
    }
    return false;
  }

  function maybeOpenFirstVisit() {
    if (shown || userActed || seen()) return;
    if (!modal()) return;
    if (anyModalOpen()) return;          // never fight another dialog
    if (open()) shown = true;
  }

  function wire() {
    var button = document.getElementById('start-open');
    if (button) {
      button.addEventListener('click', function () { open(); });
    }

    var m = modal();
    if (m) {
      // Any dismissal counts as seen, so it does not reopen on every reload.
      m.addEventListener('click', function (e) {
        if (e.target === m) markSeen();
      }, true);
      var close = document.getElementById('start-close');
      if (close) close.addEventListener('click', markSeen);
      m.querySelectorAll('.start-card').forEach(function (card) {
        card.addEventListener('click', markSeen);
      });
    }

    // Stop trying once the visitor is clearly driving.
    ['pointerdown', 'keydown', 'wheel'].forEach(function (type) {
      window.addEventListener(type, function () { userActed = true; },
        { once: true, passive: true });
    });

    maybeOpenFirstVisit();
    [300, 900, 1800].forEach(function (ms) { setTimeout(maybeOpenFirstVisit, ms); });
  }

  window.TerraOnboarding = { open: open, markSeen: markSeen };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
