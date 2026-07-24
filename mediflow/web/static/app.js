// Guards for every page that takes a password. The operator cannot see a
// masked field, so the two things that silently break credentials — Caps Lock
// and the Persian keyboard layout — have to announce themselves. This is the
// browser-side twin of mediflow/core/keyboard.py.
(function () {
  "use strict";

  var fields = Array.prototype.slice.call(
    document.querySelectorAll('input[type="password"]'));
  var username = document.getElementById("username");
  if (username) fields.push(username);
  if (!fields.length) return;

  var reveal = document.getElementById("reveal");
  var pw = document.getElementById("password");
  var capsHint = document.getElementById("capsHint");
  var layoutHint = document.getElementById("layoutHint");

  // Show/hide, so a mistyped credential is visible before submitting.
  if (reveal && pw) {
    reveal.addEventListener("click", function () {
      var shown = pw.type === "text";
      pw.type = shown ? "password" : "text";
      reveal.setAttribute("aria-label", shown ? "نمایش رمز عبور" : "پنهان کردن رمز عبور");
      pw.focus();
    });
  }

  // Characters only a Persian layout produces. ASCII is never matched, so a
  // correctly typed password stays quiet.
  var PERSIAN = /[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/;

  function checkLayout() {
    if (!layoutHint) return;
    var bad = fields.some(function (f) { return PERSIAN.test(f.value); });
    layoutHint.hidden = !bad;
  }

  function checkCaps(event) {
    if (!capsHint || typeof event.getModifierState !== "function") return;
    capsHint.hidden = !event.getModifierState("CapsLock");
  }

  fields.forEach(function (f) {
    ["input", "keyup", "keydown"].forEach(function (evt) {
      f.addEventListener(evt, checkLayout);
    });
    f.addEventListener("keydown", checkCaps);
    f.addEventListener("keyup", checkCaps);
  });
  checkLayout();
})();

// Copy-to-clipboard for the one-time temporary password. It is shown once and
// stored nowhere readable, so making it easy to capture matters.
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var el = document.getElementById(btn.getAttribute("data-copy"));
    if (!el) return;
    var text = el.textContent.trim();
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "کپی شد";
      setTimeout(function () { btn.textContent = old; }, 1500);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, done);
    } else {
      // http://127.0.0.1 is not a secure context in every browser, so fall
      // back to the legacy path rather than silently doing nothing.
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (err) { /* ignore */ }
      document.body.removeChild(ta); done();
    }
  });
})();
