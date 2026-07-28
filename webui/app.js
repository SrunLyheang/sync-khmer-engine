/* Sing Khmer web app.
 *
 * Two things to know if you edit this file:
 *
 * 1. NOTHING user-typed is ever put into innerHTML. Every value goes in through
 *    textContent or a DOM node. An earlier version interpolated user text into HTML,
 *    which was an XSS hole — keep it that way.
 * 2. The session id lives in a signed HttpOnly cookie set by the server. The browser
 *    neither sees nor sends it, so it can't be forged.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const inEl = $('in'), outEl = $('out'), bdEl = $('bd'), bdWrap = $('bdWrap'),
      rdEl = $('readings'), rdWrap = $('readingsWrap');

let chosen = {};        // word index -> candidate index the user picked
let override = null;    // whole-message reading the user switched to
let data = null;        // last /api/convert response
let timer = null, lastRecorded = '';

const optout = $('optout');
optout.checked = localStorage.getItem('sk_optout') === '1';
optout.onchange = () => localStorage.setItem('sk_optout', optout.checked ? '1' : '0');
const saving = () => !optout.checked;

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1800);
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;   // always textContent, never innerHTML
  return n;
}

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

/** A small "we don't know this word — what should it be?" box, asked where it happened. */
function unknownPrompt(spelling) {
  const box = el('div', 'ask');
  box.appendChild(el('div', 'hint', "We don't know this word — what should it be?"));
  const row = el('div', 'row');
  const input = el('input', 'khmer');
  input.type = 'text';
  input.placeholder = 'ជាភាសាខ្មែរ…';
  input.setAttribute('aria-label', 'Khmer for ' + spelling);
  const btn = el('button', 'primary', 'Send');
  const send = async () => {
    const khmer = input.value.trim();
    if (!khmer) { input.focus(); return; }
    try {
      const res = await fetch('/api/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spelling, expected_khmer: khmer, source: 'inline' }),
      });
      const j = await res.json();
      if (j.ok) { box.replaceChildren(el('div', 'hint ok', 'Thank you! អរគុណ ✓')); }
      else { toast(j.error === 'need_khmer' ? 'Please type it in Khmer' : 'Could not send'); }
    } catch (e) { toast('Could not send'); }
  };
  btn.onclick = send;
  input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') send(); });
  row.append(input, btn);
  box.appendChild(row);
  return box;
}

function render() {
  const text = currentOutput();
  outEl.replaceChildren(
    text ? document.createTextNode(text) : el('span', 'ph', 'ខ្មែរ will appear here…')
  );

  const tiles = [];
  (data ? data.words : []).forEach((w, i) => {
    if (w.space) return;
    if (w.candidates.length) {
      const tile = el('div', 'tile');
      tile.appendChild(el('span', 'latin', w.core));
      const ci = Math.min(chosen[i] || 0, w.candidates.length - 1);
      w.candidates.forEach((c, ai) => {
        const isEnglish = c.source === 'english';
        const on = (i in chosen) ? ai === ci : (w.display == null && ai === ci);
        const b = el('span', 'alt khmer' + (isEnglish ? ' en' : '') + (on ? ' chosen' : ''),
                     isEnglish ? 'English: ' + c.khmer : c.khmer);
        if (isEnglish) b.title = 'Keep this word in English instead of Khmer';
        b.onclick = () => { override = null; chosen[i] = ai; render(); };
        tile.appendChild(b);
      });
      if (w.display != null) tile.appendChild(el('span', 'hint', ' → ' + w.display + ' (ៗ)'));
      tiles.push(tile);
    } else if (w.core && /[\p{L}\p{N}]/u.test(w.core)) {
      const tile = el('div', 'tile');
      tile.appendChild(el('span', 'latin', w.core));
      tile.appendChild(el('span', 'unknown', 'no match'));
      tile.appendChild(unknownPrompt(w.core.toLowerCase()));
      tiles.push(tile);
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
  } else { rdWrap.style.display = 'none'; }
}

async function convert() {
  const q = inEl.value;
  if (!q.trim()) { data = null; render(); return; }
  try {
    const res = await fetch('/api/convert', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: q }),
    });
    if (!res.ok) return;
    data = await res.json();
  } catch (e) { return; }
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
  try {
    await fetch('/api/record', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, copied: !!copied, overrides }),
    });
  } catch (e) { /* never let logging break the app */ }
}

inEl.addEventListener('input', () => {
  chosen = {}; override = null;
  clearTimeout(timer);
  convert();
  timer = setTimeout(() => recordNow(false), 1500);   // "settled" = 1.5s after typing stops
});

$('copy').onclick = async () => {
  const text = currentOutput();
  if (!text) { toast('Nothing to copy'); return; }
  try { await navigator.clipboard.writeText(text); toast('Copied ✓'); }
  catch (e) { toast('Press and hold the Khmer text to copy'); }
  recordNow(true);        // a copy is the strongest signal that the output was right
};

$('clear').onclick = () => {
  inEl.value = ''; data = null; chosen = {}; override = null; lastRecorded = '';
  render(); inEl.focus();
};

$('send').onclick = async () => {
  const spelling = $('fbSpell').value.trim(), khmer = $('fbKhmer').value.trim();
  if (!spelling) { toast('Type what you typed'); return; }
  if (!khmer) { toast('Type the Khmer word'); return; }
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spelling, expected_khmer: khmer, source: 'form' }),
    });
    const j = await res.json();
    if (j.ok) { $('fbSpell').value = ''; $('fbKhmer').value = ''; toast('Thank you! អរគុណ'); }
    else { toast(j.error === 'need_khmer' ? 'Please type it in Khmer' : 'Could not send'); }
  } catch (e) { toast('Could not send'); }
};

window.addEventListener('pagehide', () => recordNow(false));
render();
