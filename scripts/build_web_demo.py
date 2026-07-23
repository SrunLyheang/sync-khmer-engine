#!/usr/bin/env python3
"""Generate a self-contained web demo (correct Khmer rendering + sentence input).

Terminals often can't shape Khmer script; browsers can. This exports the reverse
index to a single offline HTML file you can open in any browser to test the
converter on whole sentences, with clickable alternatives per word.

Usage:
    PYTHONPATH=src python scripts/build_web_demo.py
    # then open web/index.html in a browser
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

HTML = r"""<!doctype html>
<html lang="km">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sing Khmer → Khmer</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, sans-serif; max-width: 780px;
         margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
  h1 { font-size: 1.4rem; }
  .khmer { font-family: 'Noto Sans Khmer','Khmer OS','Khmer OS System','Battambang',
           'Hanuman', system-ui, sans-serif; }
  textarea { width: 100%; font-size: 1.2rem; padding: .7rem; box-sizing: border-box;
             border-radius: 8px; border: 1px solid #999; }
  #output { font-size: 2.2rem; line-height: 3.2rem; margin: 1.1rem 0; min-height: 3rem;
            padding: .6rem .8rem; border-radius: 10px; background: rgba(127,127,127,.1); }
  .unknown { color: #d33; }
  .wtile { border: 1px solid rgba(127,127,127,.4); border-radius: 8px;
           padding: .45rem .7rem; margin: .35rem 0; }
  .latin { color: #888; font-size: .95rem; margin-right: .4rem; }
  .alt { display: inline-block; margin: .15rem .3rem .15rem 0; padding: .1rem .55rem;
         border: 1px solid rgba(127,127,127,.5); border-radius: 6px; cursor: pointer;
         font-size: 1.4rem; }
  .alt.chosen { background: #2563eb; color: #fff; border-color: #2563eb; }
  .hint { color: #888; font-size: .9rem; }
</style>
</head>
<body>
<h1>Sing Khmer → Khmer converter</h1>
<p class="hint">Type romanized Khmer — spaces optional. Try: <code>nh sl bong</code>,
&nbsp;<code>nhslbong</code>, &nbsp;<code>msel minh</code>, &nbsp;<code>muy muy</code> (→ ៗ).
Single space = join; <b>double space = a real space</b>. Click a highlighted word to pick a
different option.</p>
<textarea id="in" rows="2" placeholder="Input your text" autofocus></textarea>
<div id="output" class="khmer"></div>
<div id="breakdown"></div>
<script>
const INDEX = __INDEX_JSON__;
const KHMER_WORDS = new Set(__WORDS_JSON__);   // known standalone words (reduplication base)
const REPEAT = "ៗ";                             // Khmer repetition sign
const inEl = document.getElementById('in');
const outEl = document.getElementById('output');
const bdEl = document.getElementById('breakdown');
let chosen = {};

// Segmentation decoder — mirrors the Python engine (works with/without spaces,
// matches multi-word spellings). See src/sing_khmer_engine/lookup.py.
const KEYS = Object.keys(INDEX);
const MAXLEN = KEYS.reduce((m, k) => Math.max(m, k.length), 1);
const LEN_WEIGHT = 3.0, UNKNOWN_PENALTY = 2.0, WORD_COST = 6.0;

function lev(a, b){
  if (a === b) return 0;
  let prev = Array.from({length: b.length + 1}, (_, i) => i);
  for (let i = 1; i <= a.length; i++){
    let cur = [i];
    for (let j = 1; j <= b.length; j++)
      cur.push(Math.min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (a[i-1]===b[j-1]?0:1)));
    prev = cur;
  }
  return prev[b.length];
}
function fuzzy(key){
  if (INDEX[key]) return INDEX[key];
  const k = key.length <= 3 ? 1 : 2, best = {};
  for (const ik of KEYS){
    if (Math.abs(ik.length - key.length) > k) continue;
    const d = lev(key, ik); if (d > k) continue;
    for (const c of INDEX[ik]){ const cur = best[c[0]];
      if (!cur || d < cur[0] || (d===cur[0] && c[1] > cur[1])) best[c[0]] = [d, c[1]]; }
  }
  return Object.entries(best).sort((x,y)=>x[1][0]-y[1][0]||y[1][1]-x[1][1])
    .map(([kh,[d,s]])=>[kh, +(s/(1+d)).toFixed(3), 'fuzzy']);
}
function spans(lower){
  const n = lower.length, dp = Array(n+1).fill(-Infinity), back = Array(n+1).fill(null);
  dp[0] = 0; back[0] = [0, null];
  for (let i = 1; i <= n; i++){
    const step = lower[i-1] === ' ' ? 0 : -UNKNOWN_PENALTY;
    if (dp[i-1] + step > dp[i]){ dp[i] = dp[i-1] + step; back[i] = [i-1, null]; }
    for (let j = Math.max(0, i-MAXLEN); j < i; j++){
      if (dp[j] <= -Infinity) continue;
      const sub = lower.slice(j, i), cands = INDEX[sub];
      if (!cands) continue;
      if (sub.length === 1 && !((j===0||lower[j-1]===' ') && (i===n||lower[i]===' '))) continue;
      const sc = dp[j] + cands[0][1] + LEN_WEIGHT*sub.length - WORD_COST;
      if (sc > dp[i]){ dp[i] = sc; back[i] = [j, sub]; }
    }
  }
  const out = []; let i = n;
  while (i > 0){ const [j, key] = back[i]; out.push([j, i, key]); i = j; }
  return out.reverse();
}
function decodePart(text){
  const lower = text.toLowerCase(), segs = []; let rawStart = null;
  const flush = (end) => {
    if (rawStart === null) return;
    const chunk = text.slice(rawStart, end); rawStart = null;
    for (const m of chunk.matchAll(/\S+/g)){
      const mm = m[0].match(/^([^\p{L}\p{N}]*)(.*?)([^\p{L}\p{N}]*)$/u), core = mm[2];
      if (!core){ segs.push({surface: m[0], candidates: [], lead: '', trail: ''}); continue; }
      segs.push({surface: core, candidates: fuzzy(core.toLowerCase()), lead: mm[1], trail: mm[3]});
    }
  };
  for (const [j, i, key] of spans(lower)){
    if (key === null){ if (rawStart === null) rawStart = j; }
    else { flush(j); segs.push({surface: text.slice(j, i), candidates: INDEX[key], lead: '', trail: ''}); }
  }
  flush(text.length);
  return segs;
}
// A word repeated twice folds to the ៗ sign; the doubled form stays as an option.
function reduplicationBase(kh){
  if (kh.length % 2 === 0){
    const half = kh.slice(0, kh.length/2);
    if (kh.slice(kh.length/2) === half && KHMER_WORDS.has(half)) return half;
  }
  return null;
}
function applyRepetition(segs){
  let prev = null;
  for (const s of segs){
    const word = s.candidates.length ? s.candidates[0][0] : null;
    const canFold = word !== null && s.display == null && !s.lead && !s.trail && !s.space;
    const base = canFold ? reduplicationBase(word) : null;
    if (canFold && base !== null){ s.display = base + REPEAT; prev = base; }
    else if (canFold && word === prev){ s.display = REPEAT; prev = word; }
    else { prev = word; }
  }
  return segs;
}
// Single space = word boundary; a run of 2+ spaces commits one real space.
function decode(text){
  const segs = [];
  text.split(/ {2,}/).forEach((part, idx) => {
    if (idx > 0) segs.push({surface: ' ', candidates: [], lead: '', trail: '', space: true});
    if (part) for (const s of decodePart(part)) segs.push(s);
  });
  return applyRepetition(segs);
}

function render(){
  const segs = decode(inEl.value);
  let out = '', bd = '', prevKhmer = false, attachNext = false;
  segs.forEach((s, i) => {
    if (s.space){ if (out && !out.endsWith(' ')) out += ' '; prevKhmer = false; attachNext = true; return; }
    const isKhmer = s.candidates.length > 0;
    let piece;
    if (isKhmer){
      const ci = Math.min(chosen[i] || 0, s.candidates.length - 1);
      // default rendering may be a ៗ override; a manual pick overrides it.
      const shown = (s.display != null && !(i in chosen)) ? s.display : s.candidates[ci][0];
      piece = s.lead + shown + s.trail;
      const note = { generated: ' (auto)', fuzzy: ' (~typo)' };
      const alts = s.candidates.map((c, ai) =>
        `<span class="alt khmer ${(i in chosen ? ai===ci : s.display==null && ai===ci)?'chosen':''}" data-w="${i}" data-a="${ai}" `
        + `title="score ${c[1]}${note[c[2]]||''}">${c[0]}</span>`).join('');
      const rep = s.display != null ? ` <span class="hint">→ ${s.display} (repeat)</span>` : '';
      bd += `<div class="wtile"><span class="latin">${s.surface}</span>→ ${alts}${rep}</div>`;
    } else {
      piece = `<span class="unknown">${s.lead}${s.surface}${s.trail}</span>`;
      if (s.surface.trim()) bd += `<div class="wtile"><span class="latin">${s.surface}</span>`
        + `→ <span class="unknown">no match yet</span></div>`;
    }
    // Khmer words run together; space only around non-Khmer, none before punctuation.
    const isPunct = !isKhmer && !/[\p{L}\p{N}]/u.test(s.surface);
    if (out === '' || attachNext) out += piece;
    else if (isPunct || (prevKhmer && isKhmer)) out += piece;
    else out += ' ' + piece;
    prevKhmer = isKhmer; attachNext = false;
  });
  outEl.innerHTML = out.trim() || '<span class="hint">…</span>';
  bdEl.innerHTML = bd;
  bdEl.querySelectorAll('.alt').forEach(el => el.onclick = () => {
    chosen[+el.dataset.w] = +el.dataset.a; render();
  });
}
inEl.addEventListener('input', () => { chosen = {}; render(); });
render();
</script>
</body>
</html>
"""


def main() -> None:
    engine = Engine()
    index = {key: [[c.khmer, c.score, c.source] for c in cands]
             for key, cands in engine.index.items()}
    words = sorted({entry.khmer for entry in engine.vocab})
    out_dir = ROOT / "web"
    out_dir.mkdir(exist_ok=True)
    html = (HTML
            .replace("__INDEX_JSON__", json.dumps(index, ensure_ascii=False))
            .replace("__WORDS_JSON__", json.dumps(words, ensure_ascii=False)))
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote web/index.html ({len(index)} spellings). Open it in a browser.")


if __name__ == "__main__":
    main()
