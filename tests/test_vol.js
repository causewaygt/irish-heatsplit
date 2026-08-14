// Executes drawVol against a fixture. node --check proves the file
// parses; it does not prove a renderer survives its arguments - the
// UK sibling shipped a hard-coded '+' that was invisible until a
// value crossed zero, and a stacked path is exactly the shape where
// an undefined field becomes "NaN" in a d attribute and draws
// nothing at all.
//
//    node tests/test_vol.js
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(
  path.join(__dirname, "..", "docs", "index.html"), "utf8");

// Lift the two pieces under test out of the page.
const parts = html.match(/const VOL_PARTS = \[[\s\S]*?\];/);
const fn = html.match(/function drawVol\(rows, state, geom\)\{[\s\S]*?\n\}/);
if (!parts || !fn) throw new Error("could not find VOL_PARTS / drawVol");

const DOM = {};
function el(id){
  if(!DOM[id]) DOM[id] = { innerHTML: "", textContent: "" };
  return DOM[id];
}
eval(parts[0] + "\n" + fn[0]);

function reset(){ DOM.volChart = null; DOM.volLegend = null; el("volChart");
  el("volLegend"); }
function ok(cond, msg){ if(!cond) throw new Error("FAIL - " + msg);
  console.log("pass - " + msg); }

const GEOM = {W: 1000, l: 62, r: 14};
function row(day, space, dhw, jur){
  const r = {day: day};
  if (space !== null) r["vol_" + (jur || "roi")] = {space: space, dhw: dhw};
  return r;
}

// ---- a full window draws, and every number in it is a number -------
reset();
const rows = [];
for (let i = 0; i < 40; i++){
  const d = new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10);
  // winter tailing off, hot water flat - the shape the pipeline emits
  rows.push(row(d, 120 - i * 2.5, 26.4));
}
drawVol(rows, "roi", GEOM);
const svg = DOM.volChart.innerHTML;
ok(svg.indexOf("<svg") === 0, "draws an svg for a full window");
ok(!/NaN|undefined/.test(svg), "no NaN or undefined anywhere in the svg");
ok((svg.match(/<path /g) || []).length === 4,
   "two stacked bands, each a fill and an outline");
ok(/GWh of delivered heat per day/.test(svg), "carries its own y-axis label");
ok(/Hot water/.test(DOM.volLegend.innerHTML), "legend names both parts");

// The stack must reach the total, not just the larger part: the top
// band's outline has to sit above the bottom band's everywhere. Each
// band emits TWO paths - a fill and an outline - both starting at the
// same point, so the bands are matches 0 and 2, and "above" means a
// SMALLER y because the svg origin is top left.
const ys = (svg.match(/M62 ([\d.]+)/g) || []).map(s => parseFloat(s.slice(4)));
ok(ys.length === 4 && ys[2] < ys[0],
   "hot water stacks ON TOP of space heat rather than over it");

// ---- an old payload declines rather than drawing an empty frame ----
reset();
drawVol(rows.map(r => ({day: r.day})), "roi", GEOM);
ok(/next daily build/.test(DOM.volChart.textContent),
   "payload without vol_ fields declines and names the cause");
ok(DOM.volLegend.innerHTML === "", "and leaves no legend behind it");

// ---- a partly-filled payload declines on the same threshold --------
reset();
const two = rows.slice(0, 5).map((r, i) =>
  i < 2 ? r : {day: r.day});
drawVol(two, "roi", GEOM);
ok(/next daily build/.test(DOM.volChart.textContent),
   "two priced days is not enough to draw");

// ---- the other jurisdiction is read from its own key ---------------
reset();
const ni = [];
for (let i = 0; i < 10; i++){
  const d = new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10);
  ni.push(row(d, 40 - i, 11.1, "ni"));
}
drawVol(ni, "ni", GEOM);
ok(/<svg/.test(DOM.volChart.innerHTML), "NI draws from vol_ni");
reset();
drawVol(ni, "roi", GEOM);
ok(/next daily build/.test(DOM.volChart.textContent),
   "and an NI-only payload does not draw under the ROI toggle");

console.log("all drawVol fixture checks passed");
