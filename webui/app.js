/* Sing Khmer web app.
 *
 * Three things to know if you edit this file:
 *
 * 1. NOTHING user-typed is ever put into innerHTML. Every value goes in through
 *    textContent or a DOM node. An earlier version interpolated user text into HTML,
 *    which was an XSS hole — keep it that way. Translations follow the same rule: i18n.js
 *    assigns only through textContent/setAttribute.
 * 2. The session id lives in a signed HttpOnly cookie set by the server. The browser
 *    neither sees nor sends it, so it can't be forged.
 * 3. Any button that fires a request goes through withPending(), which disables it for the
 *    duration. That's what stops double-submits — don't call fetch straight from a handler.
 */
'use strict';

const t = (key, vars) => window.SkI18n.t(key, vars);
const $ = (id) => document.getElementById(id);
const inEl = $('in'), outEl = $('out'), bdEl = $('bd'), bdWrap = $('bdWrap'),
      rdEl = $('readings'), rdWrap = $('readingsWrap'), convertingEl = $('converting');

const SETTLED_MS = 1500;   // "done typing" — when a conversion is worth recording
const SLOW_MS = 250;       // only show a converting indicator past this, or it just flickers

let chosen = {};        // word index -> candidate index the user picked
let override = null;    // whole-message reading the user switched to
let data = null;        // last /api/convert response
let timer = null, lastRecorded = '', convertSeq = 0;

// ---- small helpers -------------------------------------------------------------------
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;   // always textContent, never innerHTML
  return n;
}

function toast(msg) {
  const box = $('toast');
  box.textContent = msg;
  box.classList.add('show');
  setTimeout(() => box.classList.remove('show'), 1800);
}

/** POST JSON. Returns {ok, body} — a network failure looks the same as a rejected request,
 *  so callers have exactly one failure path to handle. */
async function api(path, body) {
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    let parsed = null;
    try { parsed = await res.json(); } catch (e) { /* empty or non-JSON body */ }
    return { ok: res.ok, status: res.status, body: parsed || {} };
  } catch (e) {
    return { ok: false, status: 0, body: {} };
  }
}

/** Run an async action with the button visibly busy, and always give it back.
 *  Restoring in `finally` matters: a failed request must not leave a dead button. */
async function withPending(btn, fn) {
  if (btn.disabled) return;               // already in flight
  // Prefer the translation key over the current text: if the language is switched while
  // the request is in flight, the button comes back in the language now on screen.
  const key = btn.getAttribute('data-i18n');
  const label = btn.textContent;
  btn.disabled = true;
  btn.setAttribute('aria-busy', 'true');
  btn.replaceChildren(el('span', 'spinner'), document.createTextNode(t('common.sending')));
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    btn.replaceChildren(document.createTextNode(key ? t(key) : label));
  }
}

// ---- feedback ------------------------------------------------------------------------
/** The one place a correction is sent. Both the inline prompt and the form use it, so the
 *  validation and the error messages can't drift apart. */
async function sendFeedback(spelling, khmer, source) {
  if (!spelling) { toast(t('common.needSpelling')); return false; }
  if (!khmer) { toast(t('common.needKhmerWord')); return false; }

  const res = await api('/api/feedback', {
    spelling: spelling, expected_khmer: khmer, source: source,
  });
  if (res.ok && res.body.ok) return true;

  // The server distinguishes "your word was junk" from "we couldn't store it", and the
  // difference decides whether retrying is worth it — so say which one happened.
  if (res.body.error === 'need_khmer') toast(t('common.needKhmer'));
  else if (res.body.error === 'not_stored') toast(t('common.notStored'));
  else toast(t('common.notSent'));
  return false;
}

/** A small "we don't know this word — what should it be?" box, asked where it happened. */
function unknownPrompt(spelling) {
  const box = el('div', 'ask');
  box.appendChild(el('div', 'hint', t('words.ask')));
  const row = el('div', 'row');
  const input = el('input', 'khmer');
  input.type = 'text';
  input.placeholder = t('words.askPlaceholder');
  input.setAttribute('aria-label', t('words.askAria', { spelling: spelling }));
  const btn = el('button', 'primary', t('common.send'));
  const send = () => withPending(btn, async () => {
    const khmer = input.value.trim();
    if (!khmer) { input.focus(); return; }
    if (await sendFeedback(spelling, khmer, 'inline')) {
      box.replaceChildren(el('div', 'hint ok', t('common.thanks')));
    }
  });
  btn.onclick = send;
  input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') send(); });
  row.append(input, btn);
  box.appendChild(row);
  return box;
}

// ---- rendering -----------------------------------------------------------------------
/** The Khmer currently on screen, honouring taps and reading switches. */
function currentOutput() {
  if (override !== null) return override;
  if (!data) return '';
  let out = '', prevKhmer = false, attach = false;
  data.words.forEach((w, i) => {
    if (w.space) { if (out && !out.endsWith(' ')) out += ' '; prevKhmer = false; attach = true; return; }
    const isKhmer = w.candidates.length > 0;
    let piece;
    if (isKhmer) {
      const ci = Math.min(chosen[i] || 0, w.candidates.length - 1);
      const shown = (w.display != null && !(i in chosen)) ? w.display : w.candidates[ci].khmer;
      piece = w.lead + shown + w.trail;
    } else if (w.core) { piece = w.token; } else { return; }
    const isPunct = !isKhmer && !/[\p{L}\p{N}]/u.test(w.core);
    if (out === '' || attach) out += piece;
    else if (isPunct || (prevKhmer && isKhmer)) out += piece;
    else out += ' ' + piece;
    prevKhmer = isKhmer; attach = false;
  });
  return out.trim();
}

function wordTile(w, i) {
  const tile = el('div', 'tile');
  tile.appendChild(el('span', 'latin', w.core));

  if (!w.candidates.length) {
    tile.appendChild(el('span', 'unknown', t('words.noMatch')));
    tile.appendChild(unknownPrompt(w.core.toLowerCase()));
    return tile;
  }

  const altRow = el('div', 'alt-row');
  const ci = Math.min(chosen[i] || 0, w.candidates.length - 1);
  w.candidates.forEach((c, ai) => {
    const isEnglish = c.source === 'english';
    const on = (i in chosen) ? ai === ci : (w.display == null && ai === ci);
    const b = el('span', 'alt khmer' + (isEnglish ? ' en' : '') + (on ? ' chosen' : ''),
                 isEnglish ? t('words.english', { word: c.khmer }) : c.khmer);
    b.dataset.source = c.source;
    if (isEnglish) b.title = t('words.englishHint');
    b.setAttribute('role', 'button');
    b.setAttribute('tabindex', '0');
    b.onclick = () => { override = null; chosen[i] = ai; render(); };
    b.onkeydown = (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); b.click(); }
    };
    altRow.appendChild(b);
  });
  tile.appendChild(altRow);
  if (w.display != null) tile.appendChild(el('span', 'hint', ' → ' + w.display + ' (ៗ)'));
  return tile;
}

function render() {
  const text = currentOutput();
  outEl.replaceChildren(
    text ? document.createTextNode(text) : el('span', 'ph', t('output.placeholder'))
  );

  const tiles = [];
  (data ? data.words : []).forEach((w, i) => {
    if (w.space) return;
    if (w.candidates.length || (w.core && /[\p{L}\p{N}]/u.test(w.core))) {
      tiles.push(wordTile(w, i));
    }
  });
  bdEl.replaceChildren(...tiles);
  bdWrap.style.display = tiles.length ? '' : 'none';

  const rs = (data && data.readings) || [];
  if (rs.length > 1) {
    rdWrap.style.display = '';
    rdEl.replaceChildren(...rs.map((r) => {
      const b = el('span', 'alt khmer' + (text === r ? ' chosen' : ''), r);
      b.onclick = () => { override = r; render(); };
      return b;
    }));
  } else {
    rdWrap.style.display = 'none';
  }
}

// ---- conversion ----------------------------------------------------------------------
async function convert() {
  const q = inEl.value;
  if (!q.trim()) { data = null; render(); return; }

  // Keystrokes outrun the network, so tag each request and ignore any reply that a newer
  // one has already superseded.
  const seq = ++convertSeq;
  const slow = setTimeout(() => {
    if (seq === convertSeq) convertingEl.classList.add('show');
  }, SLOW_MS);

  const res = await api('/api/convert', { text: q });
  clearTimeout(slow);
  if (seq !== convertSeq) return;
  convertingEl.classList.remove('show');
  if (!res.ok) return;
  data = res.body;
  render();
}

/** Send the finished text (not keystrokes). The server derives every signal itself. */
async function recordNow(copied) {
  if (!saving()) return;
  const text = inEl.value.trim();
  if (!text) return;
  if (!copied && text === lastRecorded) return;
  lastRecorded = text;
  const overrides = {};
  Object.keys(chosen).forEach((i) => {
    const w = data && data.words[i];
    if (w && w.candidates[chosen[i]]) overrides[i] = w.candidates[chosen[i]].khmer;
  });
  await api('/api/record', { text: text, copied: !!copied, overrides: overrides });
}

// ---- preferences ---------------------------------------------------------------------
const optout = $('optout');
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};
optout.checked = store.get('sk_optout') === '1';
optout.onchange = () => store.set('sk_optout', optout.checked ? '1' : '0');
const saving = () => !optout.checked;

// ---- events --------------------------------------------------------------------------
inEl.addEventListener('input', () => {
  chosen = {}; override = null;
  clearTimeout(timer);
  convert();
  timer = setTimeout(() => recordNow(false), SETTLED_MS);
});

// Deliberately not withPending: copying is instant, and the toast is the confirmation.
// Showing "Sending…" on it would describe the background record call, not the copy.
$('copy').onclick = async () => {
  const text = currentOutput();
  if (!text) { toast(t('common.nothingToCopy')); return; }
  try { await navigator.clipboard.writeText(text); toast(t('common.copied')); }
  catch (e) { toast(t('common.copyManual')); }
  recordNow(true);   // a copy is the strongest signal that the output was right
};

$('clear').onclick = () => {
  inEl.value = ''; data = null; chosen = {}; override = null; lastRecorded = '';
  render(); inEl.focus();
};

$('send').onclick = () => withPending($('send'), async () => {
  const ok = await sendFeedback($('fbSpell').value.trim(), $('fbKhmer').value.trim(), 'form');
  if (ok) {
    $('fbSpell').value = '';
    $('fbKhmer').value = '';
    toast(t('common.thanks'));
  }
});

$('lang').onclick = () => window.SkI18n.toggle();

$('noticeToggle').addEventListener('click', () => {
  const notice = $('notice');
  const open = notice.classList.toggle('open');
  $('noticeToggle').setAttribute('aria-expanded', open ? 'true' : 'false');
  store.set('sk_notice_open', open ? '1' : '0');
});
if (store.get('sk_notice_open') === '1') {
  $('notice').classList.add('open');
  $('noticeToggle').setAttribute('aria-expanded', 'true');
}

window.addEventListener('pagehide', () => recordNow(false));

// Vercel analytics helper
window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };

// ---- boot ----------------------------------------------------------------------------
// The switcher button shows the language you'd get by tapping it, not the current one —
// with two languages that's the only label that tells you what the button does.
window.SkI18n.onChange((lang) => {
  const next = window.SkI18n.langs.filter((l) => l.id !== lang)[0];
  $('lang').textContent = next ? next.label : lang;
  render();               // word tiles and the placeholder carry translated text too
});
window.SkI18n.apply();
