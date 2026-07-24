// Login-screen guards. These mirror the desktop build's fixes: the operator
// cannot see a masked field, so the two things that silently break sign-in —
// Caps Lock and the Persian keyboard layout — have to announce themselves.
(function () {
  "use strict";

  var pw = document.getElementById("password");
  var user = document.getElementById("username");
  var reveal = document.getElementById("reveal");
  var capsHint = document.getElementById("capsHint");
  var layoutHint = document.getElementById("layoutHint");
  if (!pw) return;

  // Show/hide the password so a mistyped credential is visible before submit.
  if (reveal) {
    reveal.addEventListener("click", function () {
      var shown = pw.type === "text";
      pw.type = shown ? "password" : "text";
      reveal.setAttribute("aria-label", shown ? "نمایش رمز عبور" : "پنهان کردن رمز عبور");
      reveal.classList.toggle("is-on", !shown);
      pw.focus();
    });
  }

  // Characters only a Persian keyboard layout produces: Arabic/Persian letter
  // blocks plus the Eastern-Arabic digit ranges. ASCII is never flagged, so a
  // correctly typed password stays quiet.
  var PERSIAN = /[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/;

  function checkLayout() {
    var bad = PERSIAN.test(pw.value) || (user && PERSIAN.test(user.value));
    if (layoutHint) layoutHint.hidden = !bad;
  }

  function checkCaps(event) {
    if (!capsHint || typeof event.getModifierState !== "function") return;
    capsHint.hidden = !event.getModifierState("CapsLock");
  }

  ["input", "keyup", "keydown"].forEach(function (evt) {
    pw.addEventListener(evt, checkLayout);
    if (user) user.addEventListener(evt, checkLayout);
  });
  pw.addEventListener("keydown", checkCaps);
  pw.addEventListener("keyup", checkCaps);
  checkLayout();
})();
