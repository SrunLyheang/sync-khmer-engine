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
<p class="hint">Type romanized Khmer with spaces between words. Try: <code>nh sl bong</code>,
&nbsp;<code>bong sabay te</code>. Click a highlighted word below to pick a different option.</p>
<textarea id="in" rows="2" placeholder="nh sl bong" autofocus></textarea>
<div id="output" class="khmer"></div>
<div id="breakdown"></div>
<script>
const INDEX = __INDEX_JSON__;
const inEl = document.getElementById('in');
const outEl = document.getElementById('output');
const bdEl = document.getElementById('breakdown');
let chosen = {};

const KEYS = Object.keys(INDEX);

function tokenize(t){ return t.split(/\s+/).filter(x => x.length); }
function splitPunct(tok){ const m = tok.match(/^([^\p{L}\p{N}]*)(.*?)([^\p{L}\p{N}]*)$/u);
  return { lead: m[1], core: m[2], trail: m[3] }; }

function lev(a, b){                       // edit distance
  if (a === b) return 0;
  let prev = Array.from({length: b.length + 1}, (_, i) => i);
  for (let i = 1; i <= a.length; i++){
    let cur = [i];
    for (let j = 1; j <= b.length; j++){
      const cost = a[i-1] === b[j-1] ? 0 : 1;
      cur.push(Math.min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost));
    }
    prev = cur;
  }
  return prev[b.length];
}

// Exact match, else closest known spellings by edit distance (mirrors the Python engine).
function lookup(key){
  if (INDEX[key]) return INDEX[key];
  const k = key.length <= 3 ? 1 : 2;
  const best = {};                        // khmer -> [distance, score]
  for (const ik of KEYS){
    if (Math.abs(ik.length - key.length) > k) continue;
    const d = lev(key, ik);
    if (d > k) continue;
    for (const c of INDEX[ik]){
      const cur = best[c[0]];
      if (!cur || d < cur[0] || (d === cur[0] && c[1] > cur[1])) best[c[0]] = [d, c[1]];
    }
  }
  return Object.entries(best)
    .sort((x, y) => x[1][0] - y[1][0] || y[1][1] - x[1][1])
    .map(([kh, [d, s]]) => [kh, +(s / (1 + d)).toFixed(3), 'fuzzy']);
}

function render(){
  const toks = tokenize(inEl.value);
  let out = '', bd = '';
  toks.forEach((tok, i) => {
    const { lead, core, trail } = splitPunct(tok);
    const cands = core ? lookup(core.toLowerCase()) : [];
    if (cands.length){
      const ci = Math.min(chosen[i] || 0, cands.length - 1);
      out += lead + cands[ci][0] + trail + ' ';
      const note = { generated: ' (auto)', fuzzy: ' (~typo)' };
      const alts = cands.map((c, ai) =>
        `<span class="alt khmer ${ai===ci?'chosen':''}" data-w="${i}" data-a="${ai}" `
        + `title="score ${c[1]}${note[c[2]]||''}">${c[0]}</span>`).join('');
      bd += `<div class="wtile"><span class="latin">${core}</span>→ ${alts}</div>`;
    } else {
      out += `<span class="unknown">${tok}</span> `;
      if (core) bd += `<div class="wtile"><span class="latin">${core}</span>`
        + `→ <span class="unknown">no match yet</span></div>`;
    }
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
    out_dir = ROOT / "web"
    out_dir.mkdir(exist_ok=True)
    html = HTML.replace("__INDEX_JSON__", json.dumps(index, ensure_ascii=False))
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote web/index.html ({len(index)} spellings). Open it in a browser.")


if __name__ == "__main__":
    main()
