#!/usr/bin/env python3
"""Live local tester for the Sing Khmer engine — run once, test in your browser.

Why this exists: terminals can't render Khmer, and regenerating a static HTML file
every time is tedious. This starts a tiny local web server that uses the REAL Python
engine (so every engine improvement shows up automatically) and reloads
`data/vocabulary.csv` whenever you edit it — so you can add words in VS Code, hit
refresh in the browser, and immediately see the effect. No rebuild step, no npm.

Usage (from the project root):
    PYTHONPATH=src python scripts/serve.py           # then open http://localhost:8000
    PYTHONPATH=src python scripts/serve.py 8080      # custom port

Stop it with Ctrl-C.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402

VOCAB = ROOT / "data" / "vocabulary.csv"

_engine: Engine | None = None
_loaded_mtime: float | None = None


def get_engine() -> Engine:
    """Return a cached engine, rebuilding it if vocabulary.csv changed on disk."""
    global _engine, _loaded_mtime
    mtime = VOCAB.stat().st_mtime
    if _engine is None or mtime != _loaded_mtime:
        _engine = Engine()
        _loaded_mtime = mtime
        print(f"  (loaded {len(_engine.index)} spellings from vocabulary.csv)")
    return _engine


PAGE = r"""<!doctype html>
<html lang="km"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sing Khmer — live tester</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 780px; margin: 2rem auto; padding: 0 1rem; }
  .khmer { font-family: 'Noto Sans Khmer','Khmer OS','Battambang','Hanuman', system-ui, sans-serif; }
  textarea { width:100%; font-size:1.2rem; padding:.7rem; box-sizing:border-box; border-radius:8px;
             border:1px solid #999; }
  #out { font-size:2.2rem; line-height:3.2rem; margin:1.1rem 0; min-height:3rem; padding:.6rem .8rem;
         border-radius:10px; background:rgba(127,127,127,.1); }
  .unknown { color:#d33; }
  .wtile { border:1px solid rgba(127,127,127,.4); border-radius:8px; padding:.45rem .7rem; margin:.35rem 0; }
  .latin { color:#888; font-size:.95rem; margin-right:.4rem; }
  .alt { display:inline-block; margin:.15rem .3rem .15rem 0; padding:.1rem .55rem;
         border:1px solid rgba(127,127,127,.5); border-radius:6px; cursor:pointer; font-size:1.4rem; }
  .alt.chosen { background:#2563eb; color:#fff; border-color:#2563eb; }
  .alt.en-btn { font-size:.85rem; color:#888; }
  .alt.en-opt { display:none; font-size:1.05rem; color:#666; }
  .hint { color:#888; font-size:.9rem; }
</style></head><body>
<h1>Sing Khmer — live tester</h1>
<p class="hint">Uses the real engine. Edit <code>data/vocabulary.csv</code> in VS Code, then just
refresh this page — no rebuild needed. Try <code>nhslbong</code>, <code>bongrean</code>,
<code>muy muy</code> (→ ៗ). Single space = join; <b>double space = a real space</b>.</p>
<textarea id="in" rows="2" placeholder="Input your text" autofocus></textarea>
<div id="out" class="khmer"></div>
<div id="readings"></div>
<div id="bd"></div>
<script>
const inEl = document.getElementById('in'), outEl = document.getElementById('out'),
      rdEl = document.getElementById('readings'), bdEl = document.getElementById('bd');
let chosen = {}, timer = null, override = null;
async function run(){
  const q = inEl.value;
  const res = await fetch('/convert?q=' + encodeURIComponent(q));
  const data = await res.json();
  let out = '', bd = '', prevKhmer = false, attachNext = false;
  data.words.forEach((w, i) => {
    if (w.space){ if (out && !out.endsWith(' ')) out += ' '; prevKhmer = false; attachNext = true; return; }
    const isKhmer = w.candidates.length > 0;
    let piece;
    if (isKhmer){
      const ci = Math.min(chosen[i] || 0, w.candidates.length - 1);
      // default rendering may be an override (ៗ repetition); a manual pick wins over it.
      const shown = (w.display != null && !(i in chosen)) ? w.display : w.candidates[ci].khmer;
      piece = w.lead + shown + w.trail;
      const note = { generated:' (auto)', fuzzy:' (~typo)' };
      const tile = (c, ai, extra) =>
        `<span class="alt khmer ${extra} ${(i in chosen ? ai===ci : w.display==null && ai===ci)?'chosen':''}"
         data-w="${i}" data-a="${ai}" title="score ${c.score}${note[c.source]||''}">${c.khmer}</span>`;
      // English original (if any) is the last option, hidden behind an "En" toggle.
      const alts = w.candidates.map((c, ai) => c.source==='english' ? '' : tile(c, ai, '')).join('');
      const engHtml = w.candidates.map((c, ai) => c.source==='english'
        ? tile(c, ai, `en-opt e${i}`) : '').join('');
      const enBtn = engHtml ? `<span class="alt en-btn" data-e="${i}" title="type it in English instead">En</span>` : '';
      const rep = w.display != null ? ` <span class="hint">→ ${w.display} (repeat)</span>` : '';
      bd += `<div class="wtile"><span class="latin">${w.core}</span>→ ${alts}${enBtn}${engHtml}${rep}</div>`;
    } else if (w.core){
      piece = `<span class="unknown">${w.token}</span>`;
      bd += `<div class="wtile"><span class="latin">${w.core}</span>→ <span class="unknown">no match</span></div>`;
    } else { return; }
    // Khmer words run together; space only around non-Khmer, none before punctuation.
    const isPunct = !isKhmer && !/[\p{L}\p{N}]/u.test(w.core);
    if (out === '' || attachNext) out += piece;
    else if (isPunct || (prevKhmer && isKhmer)) out += piece;
    else out += ' ' + piece;
    prevKhmer = isKhmer; attachNext = false;
  });
  const readings = data.readings || [];
  outEl.innerHTML = (override !== null ? override : out.trim()) || '<span class="hint">…</span>';
  // whole-message alternative readings (compound vs. split) — click to switch
  if (readings.length > 1){
    rdEl.innerHTML = '<span class="hint">readings: </span>' + readings.map(r =>
      `<span class="alt khmer ${(override!==null?override:out.trim())===r?'chosen':''}"
        data-r="${encodeURIComponent(r)}">${r}</span>`).join('');
    rdEl.querySelectorAll('.alt').forEach(el => el.onclick = () => {
      override = decodeURIComponent(el.dataset.r); run(); });
  } else { rdEl.innerHTML = ''; }
  bdEl.innerHTML = bd;
  // "En" toggle reveals the hidden English option for that word.
  bdEl.querySelectorAll('.en-btn').forEach(el => el.onclick = () => {
    el.classList.toggle('chosen');
    bdEl.querySelectorAll('.e' + el.dataset.e).forEach(o => o.style.display =
      o.style.display === 'inline-block' ? 'none' : 'inline-block');
  });
  bdEl.querySelectorAll('.alt[data-w]').forEach(el => el.onclick = () => {
    override = null; chosen[+el.dataset.w] = +el.dataset.a; run(); });
}
inEl.addEventListener('input', () => { chosen = {}; override = null; clearTimeout(timer); timer = setTimeout(run, 120); });
run();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter console
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if parsed.path == "/convert":
            q = parse_qs(parsed.query).get("q", [""])[0]
            words = []
            for w in get_engine().decode(q):
                words.append({
                    "token": f"{w.lead}{w.surface}{w.trail}", "core": w.surface,
                    "lead": w.lead, "trail": w.trail,
                    "space": w.space, "display": w.display,
                    "candidates": [
                        {"khmer": c.khmer, "score": c.score, "source": c.source}
                        for c in w.candidates
                    ],
                })
            readings = get_engine().readings(q)
            self._send(200, json.dumps({"words": words, "readings": readings}),
                       "application/json; charset=utf-8")
            return
        self._send(404, "not found", "text/plain")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    get_engine()  # warm up + print count
    print(f"\n  Sing Khmer tester running →  http://localhost:{port}")
    print("  Edit data/vocabulary.csv, then refresh the page. Ctrl-C to stop.\n")
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")


if __name__ == "__main__":
    main()
