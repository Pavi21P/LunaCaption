# ruff: noqa: E501  (embedded HTML page template)
"""Build a private HTML page for the human caption review in docs/EVALUATION.md.

Usage (from the project root):
    python scripts/make_review_page.py .local/evaluation/v1/<run>/review-template.json \
        --image-root ..\\Flickr8k_Dataset\\Flicker8k_Dataset

The page is written next to the template and stays in the ignored .local folder,
because it shows dataset images. It never fills in ratings itself: a person rates
each caption, progress is kept in the browser, and "Export" downloads the
completed review JSON (same shape as the template) with a protocol summary.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LunaCaption caption review</title>
<style>
:root{--mist:#f2eef6;--card:#fbfaff;--line:#ddd6ee;--wash:#e4ddf5;--violet:#6a52c4;
--plum:#45338f;--night:#2f2560;--muted:#625a85}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 "Segoe UI",system-ui,sans-serif;
background:var(--mist);color:var(--night)}
main{max-width:1080px;margin:0 auto;padding:24px;display:grid;
grid-template-columns:minmax(0,1fr) 320px;gap:20px}
header{grid-column:1/-1;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
h1{font-size:22px;margin:0 auto 0 0}.card{background:var(--card);border:1px solid var(--line);
border-radius:12px;padding:18px}img{display:block;max-width:100%;max-height:52vh;margin:0 auto;
border-radius:8px}.caption{font-size:20px;margin:16px 0 4px}.muted{color:var(--muted)}
fieldset{border:0;padding:0;margin:14px 0}legend{font-weight:600;margin-bottom:6px}
label.opt{display:block;padding:6px 10px;border:1px solid var(--line);border-radius:8px;
margin:4px 0;cursor:pointer}label.opt:has(input:checked){background:var(--wash);
border-color:var(--violet)}textarea,input[type=text]{width:100%;font:inherit;padding:8px;
border:1px solid var(--line);border-radius:8px;background:#fff}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);
background:var(--wash);color:var(--night);cursor:pointer}
button.primary{background:var(--violet);border-color:var(--violet);color:#fff}
.nav{display:flex;gap:8px;align-items:center;margin-top:14px}.nav span{margin-left:auto}
table{border-collapse:collapse;width:100%}td{padding:3px 0}td+td{text-align:right}
:focus-visible{outline:3px solid var(--violet);outline-offset:2px}
</style></head><body><main>
<header><h1>Caption review</h1>
<label>Reviewer pseudonym <input type="text" id="reviewer" style="width:180px"></label>
<button class="primary" id="export">Export review JSON</button></header>
<section class="card" aria-live="polite">
<img id="photo" alt="">
<p class="caption" id="caption"></p>
<p class="muted" id="position"></p>
<form id="form">
<fieldset><legend>Faithfulness</legend>
<label class="opt"><input type="radio" name="faithfulness" value="0"> 0 - wrong main subject/action or major invented claim</label>
<label class="opt"><input type="radio" name="faithfulness" value="1"> 1 - minor unsupported detail</label>
<label class="opt"><input type="radio" name="faithfulness" value="2"> 2 - no observed unsupported claim</label></fieldset>
<fieldset><legend>Coverage</legend>
<label class="opt"><input type="radio" name="coverage" value="0"> 0 - misses salient content</label>
<label class="opt"><input type="radio" name="coverage" value="1"> 1 - captures some main content</label>
<label class="opt"><input type="radio" name="coverage" value="2"> 2 - captures main entities/action</label></fieldset>
<fieldset><legend>Fluency</legend>
<label class="opt"><input type="radio" name="fluency" value="0"> 0 - unintelligible</label>
<label class="opt"><input type="radio" name="fluency" value="1"> 1 - understandable but awkward</label>
<label class="opt"><input type="radio" name="fluency" value="2"> 2 - clear English</label></fieldset>
<fieldset><legend>Hallucination (anything in the caption that is not in the image)</legend>
<label class="opt"><input type="radio" name="hallucination" value="no"> No</label>
<label class="opt"><input type="radio" name="hallucination" value="yes"> Yes</label>
<label class="opt"><input type="radio" name="hallucination" value="uncertain"> Uncertain</label></fieldset>
<label>Short explanation (optional)<textarea name="note" rows="2"></textarea></label>
</form>
<div class="nav"><button id="prev">&larr; Previous</button><button id="next" class="primary">Next &rarr;</button>
<span class="muted" id="saved"></span></div>
</section>
<aside class="card"><h2 style="font-size:16px;margin-top:0">Summary</h2><table id="summary"></table>
<p class="muted" style="font-size:13px">Judge only what is visible. Don't guess identity or
sensitive attributes. Rate the caption as generated; never edit it first.</p></aside>
</main>
<script>
const TEMPLATE = __TEMPLATE__;
const IMAGE_ROOT = __IMAGE_ROOT__;
const KEY = "lunacaption-review:" + TEMPLATE.manifest_sha256;
const AXES = ["faithfulness", "coverage", "fluency", "hallucination"];
const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
const rows = TEMPLATE.rows.map(r => ({...r, ...(saved.rows || {})[r.id]}));
let index = saved.index || 0;
const $ = id => document.getElementById(id);
const form = $("form");
$("reviewer").value = saved.reviewer || "";

function complete(r) { return AXES.every(a => r[a] !== null && r[a] !== undefined); }
function persist() {
  const store = {index, reviewer: $("reviewer").value.trim(), rows: {}};
  for (const r of rows) if (complete(r) || r.note) store.rows[r.id] = pick(r);
  localStorage.setItem(KEY, JSON.stringify(store));
  $("saved").textContent = "Saved in this browser";
}
function pick(r) {
  return {faithfulness: r.faithfulness, coverage: r.coverage, fluency: r.fluency,
          hallucination: r.hallucination, note: r.note, reviewed_at: r.reviewed_at};
}
function show() {
  const r = rows[index];
  $("photo").src = IMAGE_ROOT + encodeURIComponent(r.id);
  $("photo").alt = "Evaluation image " + (index + 1);
  $("caption").textContent = "“" + r.generated_caption + "”";
  $("position").textContent = `Image ${index + 1} of ${rows.length}`;
  form.reset();
  for (const a of AXES) if (r[a] !== null && r[a] !== undefined)
    form.querySelector(`input[name=${a}][value="${r[a]}"]`).checked = true;
  form.note.value = r.note || "";
  $("prev").disabled = index === 0;
  $("next").textContent = index === rows.length - 1 ? "Finish" : "Next →";
  summarize();
}
function read() {
  const r = rows[index];
  for (const a of AXES) {
    const v = form.querySelector(`input[name=${a}]:checked`);
    r[a] = v ? (a === "hallucination" ? v.value : Number(v.value)) : null;
  }
  r.note = form.note.value.trim() || null;
  if (complete(r) && !r.reviewed_at) r.reviewed_at = new Date().toISOString();
  persist(); summarize();
}
function summary() {
  const done = rows.filter(complete);
  const dist = a => [0, 1, 2].map(v => done.filter(r => r[a] === v).length).join(" / ");
  const hall = v => done.filter(r => r.hallucination === v).length;
  const ok = done.filter(r => r.faithfulness === 2 && r.coverage >= 1 && r.fluency >= 1
                              && r.hallucination === "no").length;
  return {reviewed: done.length, successful: rows.length,
          faithfulness_0_1_2: dist("faithfulness"), coverage_0_1_2: dist("coverage"),
          fluency_0_1_2: dist("fluency"),
          hallucination: {yes: hall("yes"), no: hall("no"), uncertain: hall("uncertain")},
          acceptable: ok};
}
function summarize() {
  const s = summary();
  $("summary").innerHTML = [
    ["Reviewed", `${s.reviewed} / ${s.successful}`],
    ["Faithfulness 0/1/2", s.faithfulness_0_1_2], ["Coverage 0/1/2", s.coverage_0_1_2],
    ["Fluency 0/1/2", s.fluency_0_1_2],
    ["Hallucination yes/no/?", `${s.hallucination.yes} / ${s.hallucination.no} / ${s.hallucination.uncertain}`],
    ["Acceptable", `${s.acceptable} / ${s.reviewed}`],
  ].map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}
form.addEventListener("change", read);
form.note.addEventListener("input", read);
$("reviewer").addEventListener("input", persist);
$("prev").onclick = () => { index = Math.max(0, index - 1); persist(); show(); };
$("next").onclick = () => {
  if (index < rows.length - 1) { index++; persist(); show(); }
  else { const left = rows.findIndex(r => !complete(r)); if (left >= 0) { index = left; show(); } }
};
$("export").onclick = () => {
  const reviewer = $("reviewer").value.trim();
  if (!reviewer) { alert("Enter a reviewer pseudonym first."); $("reviewer").focus(); return; }
  const out = {...TEMPLATE, summary: summary(),
    rows: rows.map(r => ({...r, reviewer: complete(r) ? reviewer : null}))};
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], {type: "application/json"}));
  link.download = "review-completed.json"; link.click();
};
show();
</script></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("template", type=Path)
    parser.add_argument("--image-root", type=Path, required=True)
    args = parser.parse_args()
    template = json.loads(args.template.read_text(encoding="utf-8"))
    if not template.get("rows"):
        parser.error("The review template has no rows.")
    output = args.template.with_name("review.html")
    relative = os.path.relpath(args.image_root.resolve(), output.parent.resolve())
    image_root = Path(relative).as_posix().rstrip("/") + "/"
    page = PAGE.replace("__TEMPLATE__", json.dumps(template).replace("</", "<\\/"))
    page = page.replace("__IMAGE_ROOT__", json.dumps(image_root).replace("</", "<\/"))
    output.write_text(page, encoding="utf-8")
    print(f"Wrote {output} for {len(template['rows'])} captions. Open it in a browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
