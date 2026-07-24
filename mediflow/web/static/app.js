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

// Invoice builder: add/remove line rows and keep the totals live. The server
// recomputes everything on submit — this is only so the cashier sees the
// amount before committing, never the source of truth.
(function () {
  "use strict";
  var form = document.getElementById("invoiceForm");
  if (!form) return;

  var rows = document.getElementById("lineRows");
  var addBtn = document.getElementById("addLine");
  var num = function (v) { var n = parseFloat(v); return isFinite(n) ? n : 0; };
  var fmt = function (n) { return Math.round(n).toString(); };

  function recalc() {
    var subtotal = 0;
    Array.prototype.forEach.call(rows.querySelectorAll(".line-row"), function (row) {
      var qty = num(row.querySelector(".qty").value) || 0;
      var price = num(row.querySelector(".price").value);
      var line = qty * price;
      subtotal += line;
      row.querySelector(".line-total").textContent = fmt(line);
    });
    var discount = num(document.getElementById("discount").value);
    var tax = num(document.getElementById("tax").value);
    document.getElementById("sumSubtotal").textContent = fmt(subtotal);
    document.getElementById("sumDiscount").textContent = fmt(discount);
    document.getElementById("sumTax").textContent = fmt(tax);
    document.getElementById("sumTotal").textContent = fmt(subtotal - discount + tax);
  }

  addBtn.addEventListener("click", function () {
    var copy = rows.querySelector(".line-row").cloneNode(true);
    Array.prototype.forEach.call(copy.querySelectorAll("input"), function (i) {
      i.value = i.classList.contains("qty") ? "1" : "";
    });
    copy.querySelector(".line-total").textContent = "0";
    rows.appendChild(copy);
  });

  rows.addEventListener("click", function (e) {
    if (!e.target.closest(".remove-line")) return;
    // Always leave one row, otherwise "add" has nothing to clone from.
    if (rows.querySelectorAll(".line-row").length > 1) {
      e.target.closest(".line-row").remove();
    } else {
      Array.prototype.forEach.call(rows.querySelectorAll("input"), function (i) {
        i.value = i.classList.contains("qty") ? "1" : "";
      });
    }
    recalc();
  });

  form.addEventListener("input", recalc);
  recalc();
})();

// Journal entry builder. Double-entry bookkeeping requires the debit and
// credit columns to match exactly; the service rejects anything else. Showing
// the running difference means the accountant sees the imbalance while typing
// instead of after submitting a finished entry.
(function () {
  "use strict";
  var form = document.getElementById("journalForm");
  if (!form) return;

  var rows = document.getElementById("journalRows");
  var hint = document.getElementById("balanceHint");
  var num = function (v) { var n = parseFloat(v); return isFinite(n) ? n : 0; };
  var fmt = function (n) { return Math.round(n).toString(); };

  function recalc() {
    var debit = 0, credit = 0;
    Array.prototype.forEach.call(rows.querySelectorAll(".jline"), function (row) {
      debit += num(row.querySelector(".debit").value);
      credit += num(row.querySelector(".credit").value);
    });
    var diff = debit - credit;
    document.getElementById("sumDebit").textContent = fmt(debit);
    document.getElementById("sumCredit").textContent = fmt(credit);
    document.getElementById("sumDiff").textContent = fmt(diff);

    if (debit === 0 && credit === 0) {
      hint.textContent = ""; hint.className = "hint";
    } else if (Math.abs(diff) < 0.005) {
      hint.textContent = "سند متوازن است.";
      hint.className = "hint balanced";
    } else {
      hint.textContent = "سند متوازن نیست — اختلاف " + fmt(Math.abs(diff));
      hint.className = "hint warn";
    }
  }

  document.getElementById("addJline").addEventListener("click", function () {
    var copy = rows.querySelector(".jline").cloneNode(true);
    Array.prototype.forEach.call(copy.querySelectorAll("input"), function (i) { i.value = ""; });
    copy.querySelector(".acct").selectedIndex = 0;
    rows.appendChild(copy);
  });

  rows.addEventListener("click", function (e) {
    if (!e.target.closest(".remove-jline")) return;
    // Keep two rows: an entry needs at least two lines to balance at all.
    if (rows.querySelectorAll(".jline").length > 2) {
      e.target.closest(".jline").remove();
    } else {
      var row = e.target.closest(".jline");
      Array.prototype.forEach.call(row.querySelectorAll("input"), function (i) { i.value = ""; });
      row.querySelector(".acct").selectedIndex = 0;
    }
    recalc();
  });

  form.addEventListener("input", recalc);
  recalc();
})();
