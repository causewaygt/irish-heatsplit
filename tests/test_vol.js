// Executes the front end's renderers against fixtures rather than
// only parsing them. `node --check` proves a file parses; it does not
// prove a renderer survives its arguments - the UK sibling shipped a
// hard-coded '+' that stayed invisible until a value crossed zero,
// and a stacked path is exactly the shape where an undefined field
// becomes "NaN" in a d attribute and draws nothing at all.
//
//    node tests/test_vol.js
const fs = require("fs");
const path = require("path");

const HTML = path.join(__dirname, "..", "docs", "index.html");
const html = fs.readFileSync(HTML, "utf8");

const DOM = {};
function el(id){
  if(!DOM[id]) DOM[id] = { innerHTML: "", textContent: "" };
  return DOM[id];
}
function reset(){
  delete DOM.volChart; delete DOM.volLegend;
  el("volChart"); el("volLegend");
}
let checks = 0;
function ok(cond, msg){
  if(!cond) throw new Error("FAIL - " + msg);
  checks++;
  console.log("pass - " + msg);
}

// ---------------------------------------------------------------
// THE WHOLE SCRIPT BLOCK, EVALUATED ONCE.
//
// This used to lift each function out of index.html by its own
// regex and eval them in small groups. That worked while the
// renderers were self-contained, and stopped working as soon as they
// began sharing helpers: every new chart needed several lifts in the
// right order, MONTHS3 ended up lifted twice, and three consecutive
// runs failed on "X is not defined" before a single assertion ran.
// Worse, the per-function lifts hid a real fault - niceTicks returns
// GW while the plotting code works in MW, a boundary that only exists
// because the helper is shared, and the harness could not see it.
//
// Evaluating the block once means every function and constant is in
// scope exactly as it is on the page, in the same order, with no
// lift list to maintain.
// ---------------------------------------------------------------
const SCRIPTS = [...html.matchAll(
  /<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if(!SCRIPTS.length) throw new Error("no inline script found in index.html");

// Enough of a browser for the block to load. Anything the page does on
// load - attaching listeners, fetching data - must no-op rather than
// throw, or nothing after it gets defined.
const listeners = [];
const stubNode = () => ({
  addEventListener: (ev, fn) => listeners.push(fn),
  setAttribute(){}, removeAttribute(){}, classList: {add(){}, remove(){}},
  querySelectorAll: () => [], appendChild(){}, dataset: {},
  style: {}, innerHTML: "", textContent: "", open: false, hidden: false,
});
global.document = {
  querySelectorAll: () => [],
  querySelector: () => null,
  getElementById: id => el(id),
  addEventListener(){}, createElement: stubNode,
  body: stubNode(), documentElement: stubNode(),
};
global.window = { addEventListener(){}, matchMedia: () => ({matches:false}),
                  location: {hash: ""}, devicePixelRatio: 1 };
global.fetch = () => new Promise(() => {});   // never resolves: no boot
global.Plotly = { newPlot(){}, react(){}, purge(){}, relayout(){} };
global.requestAnimationFrame = fn => 0;
global.setTimeout = (fn, ms) => 0;

// A shim appended INSIDE the eval. Function declarations from a
// non-strict eval reach global scope, but `let` and `const` do not -
// they live in a lexical environment that is discarded when the eval
// finishes. So the renderers are callable from here, while the page's
// own state (GJUR, GVIEW, DDJUR) and its consts (fmt, MONTHS3) are
// not. Accessors defined inside the eval can still see them.
const SHIM = `
globalThis.__page = {
  get GJUR(){return GJUR}, set GJUR(v){GJUR = v},
  get GVIEW(){return GVIEW}, set GVIEW(v){GVIEW = v},
  get DDJUR(){return DDJUR}, set DDJUR(v){DDJUR = v},
  get GEOJUR(){return GEOJUR}, set GEOJUR(v){GEOJUR = v},
  get VFMJUR(){return VFMJUR}, set VFMJUR(v){VFMJUR = v},
  fmt: fmt, MONTHS3: MONTHS3, NICE: NICE, niceTicks: niceTicks,
  hourLabel: hourLabel, monthLabel: monthLabel,
};`;
SCRIPTS.forEach((src, i) => {
  try {
    // the SHIM reaches into the page block's lexical scope (fmt,
    // MONTHS3...). Since the generator injects the lever widget as a
    // second block, shim only blocks that actually define the helpers.
    (0, eval)(src + (/\bconst fmt\b/.test(src) ? SHIM : ""));
  } catch(e){
    throw new Error("script block " + i + " failed to evaluate: " + e.message);
  }
});
const page = globalThis.__page;

// The page's top-level `let` bindings live in the global lexical
// environment created by the eval, which a plain assignment from module
// scope does not reach. Assign in the same scope instead.
function setPageVar(name, value){ page[name] = value; }
function getPageVar(name){ return page[name]; }

// ---------------------------------------------------------------
// Geometric predicates, shared by every chart test.
//
// Both charts that shipped visibly broken were GEOMETRY faults, and
// both passed a suite that only asked whether elements existed. A
// chart can be entirely present and entirely wrong: seven gridlines
// stacked on the baseline, a label drawn straight through a bar.
// ---------------------------------------------------------------
function attrs(svg, tag, name){
  const re = new RegExp("<" + tag + " [^>]*" + name + '="([-\\d.]+)"', "g");
  return [...svg.matchAll(re)].map(m => +m[1]);
}
function texts(svg){
  return [...svg.matchAll(/<text ([^>]*)>([^<]*)<\/text>/g)].map(m => ({
    attr: m[1], body: m[2],
    x: +(m[1].match(/\bx="([-\d.]+)"/) || [0,NaN])[1],
    y: +(m[1].match(/\by="([-\d.]+)"/) || [0,NaN])[1],
  }));
}
function rects(svg){
  return [...svg.matchAll(/<rect ([^>]*)\/>/g)].map(m => {
    const g = n => +(m[1].match(new RegExp("\\b"+n+'="([-\\d.]+)"')) || [0,NaN])[1];
    return {x: g("x"), y: g("y"), w: g("width"), h: g("height")};
  });
}
// A panel can hold more than one chart, and a predicate handed the
// whole panel compares one chart's geometry against another's. Always
// scope to a single <svg>.
function svgAt(htmlStr, i){
  const all = htmlStr.match(/<svg [\s\S]*?<\/svg>/g) || [];
  if(!all[i || 0]) throw new Error("no svg at index " + (i||0));
  return all[i || 0];
}
// A chart whose gridlines collapse onto one another has no axis, even
// though every <line> and every <text> is present. Count only the
// gridlines - the dashed rules are drawn with a different stroke and
// are allowed to land wherever their value falls.
function gridlinesSpread(svg, least){
  const ys = [...svg.matchAll(
    /<line [^>]*y1="([-\d.]+)"[^>]*stroke="var\(--line\)"/g)]
    .map(m => Math.round(+m[1]));
  return ys.length >= (least || 3) && new Set(ys).size === ys.length;
}
// No text may cross a filled bar: that is how the ceiling label became
// unreadable where it ran through the tallest column.
//
// Testing the ANCHOR POINT alone is not enough, and this predicate
// first shipped that way - the original fault was a long label whose
// start sat in a gap and whose body crossed the next two bars. So
// estimate the span the glyphs occupy and test that instead.
function noTextInsideBars(svg){
  const rs = rects(svg).filter(r => r.w > 8 && r.h > 8);
  return !texts(svg).some(t => {
    if(!isFinite(t.x) || !isFinite(t.y)) return false;
    const size = +(t.attr.match(/font-size="(\d+)"/) || [0,12])[1];
    const w = t.body.length * size * 0.6;
    const anchor = (t.attr.match(/text-anchor="(\w+)"/) || [0,"start"])[1];
    const x0 = anchor === "middle" ? t.x - w/2
             : anchor === "end" ? t.x - w : t.x;
    const x1 = x0 + w;
    return rs.some(r => {
      // a value label centred over its own bar is fine; anything that
      // OVERLAPS a bar's filled area is not
      const inside = t.y > r.y + 2 && t.y < r.y + r.h - 2;
      const centred = anchor === "middle"
        && Math.abs(t.x - (r.x + r.w/2)) < 2;
      return inside && !centred && x1 > r.x + 2 && x0 < r.x + r.w - 2;
    });
  });
}
// A rotated axis label jammed against the frame is present and
// unreadable - it rendered at x=16 in a 1000-unit viewBox for weeks,
// about 16px from the edge in 12px grey, and every suite passed.
// Require it to clear the frame, to be no smaller than the tick
// numbers it labels, and to sit in the gutter rather than over the
// plot.
function axisLabelReadable(svg, gutter){
  const rot = texts(svg).filter(t => /rotate\(-?90/.test(t.attr));
  if(!rot.length) return false;
  return rot.every(t => {
    const size = +(t.attr.match(/font-size="(\d+)"/) || [0,0])[1];
    const x = t.x, right = /rotate\(90/.test(t.attr);
    const clear = right ? x > 900 : (x >= 22 && x <= (gutter || 82));
    return size >= 13 && clear;
  });
}
// An axis with no numbers on it, or numbers dimmer and smaller than
// the label beside them, reads as unlabelled however correct the
// geometry is. Two charts kept their 11px muted ticks through three
// rounds of "fixing the axis labels", because every assertion looked
// at the rotated label and none looked at the ticks.
function tickValuesReadable(svg, least, side){
  // side "right" reads the ticks drawn past the plot's right edge,
  // which carry no text-anchor. A predicate that only looked at
  // left-anchored ticks could not see the dispatch-down chart's
  // percentage axis, and that axis stayed 12px muted through every
  // round of fixing.
  // A horizontal bar chart's value axis runs along the BOTTOM, with
  // middle-anchored ticks - neither left nor right. The predicate knew
  // only vertical axes and would have skipped it silently.
  const t = side === "right"
    ? texts(svg).filter(x => !/text-anchor/.test(x.attr)
                             && !/rotate/.test(x.attr) && x.x > 880)
    : side === "bottom"
    ? texts(svg).filter(x => /text-anchor="middle"/.test(x.attr)
                             && !/rotate/.test(x.attr) && x.y > 200
                             && /^[\d.,]+$/.test(x.body.trim()))
    : texts(svg).filter(x => /text-anchor="end"/.test(x.attr));
  if(t.length < (least || 3)) return false;
  const bodies = t.map(x => x.body.trim()).filter(Boolean);
  if(new Set(bodies).size < bodies.length) return false;   // all distinct
  return t.every(x => {
    const size = +(x.attr.match(/font-size="(\d+)"/) || [0,0])[1];
    return size >= 13 && !/var\(--muted\)/.test(x.attr);
  });
}
// EVERY AXIS THAT CARRIES NUMBERS MUST CARRY A NAME. The
// dispatch-down chart drew right-hand tick values with nothing
// labelling them for four rounds of "fix the axis labels", because
// each predicate checked the labels that existed rather than counting
// them against the axes that did. Count both sides.
function everyAxisTitled(svg){
  const t = texts(svg);
  const leftTicks = t.some(x => /text-anchor="end"/.test(x.attr));
  const rightTicks = t.some(x => !/text-anchor/.test(x.attr)
                                 && !/rotate/.test(x.attr) && x.x > 880);
  const titles = t.filter(x => /rotate\(-?90/.test(x.attr));
  const leftTitle = titles.some(x => x.x < 200);
  const rightTitle = titles.some(x => x.x > 800);
  if(leftTicks && !leftTitle) return false;
  if(rightTicks && !rightTitle) return false;
  return leftTicks || rightTicks;
}
// Bars must use the height available: a chart drawn at a tenth of its
// axis is a scale fault, not a small number.
function usesItsAxis(svg, frac){
  const rs = rects(svg).filter(r => r.w > 8 && r.h > 0);
  if(!rs.length) return false;
  const lo = Math.min(...rs.map(r => r.y)), hi = Math.max(...rs.map(r => r.y + r.h));
  return (hi - lo) > (frac || 0.4) * hi;
}


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
ok(tickValuesReadable(svg, 3),
   "and the volume chart's tick values are legible");
// The VISIBLE label is rotated within the chart height, so a single
// long line is cut off - it shipped reading "GWh of delivered heat
// per da". The old assertion passed on the aria-label alone and would
// not have caught that, so pin the two tspans instead.
ok(/<tspan[^>]*>GWh of delivered<\/tspan>/.test(svg)
   && /<tspan[^>]*>heat per day<\/tspan>/.test(svg),
   "y-axis label is split over two lines so it cannot clip");
ok(/Hot water/.test(DOM.volLegend.innerHTML), "legend names both parts");
// x-axis dates in the UK sibling's form, so the two sites' charts can
// sit beside each other. "2026-01" reads as a database key.
ok(monthLabel("2026-01") === "Jan 26" && monthLabel("2025-11") === "Nov 25",
   "month labels read as Jan 26, not 2026-01");
ok(/>Jan 26</.test(svg) && !/>2026-01</.test(svg),
   "and the chart prints them that way");

// The stack must reach the total, not just the larger part. Each band
// emits TWO paths - a fill and an outline - both starting at the same
// point, so the bands are matches 0 and 2, and "above" means a
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

// ---- too few days to draw at all -----------------------------------
// Fully covered, but below the three-point threshold: a two-point
// stack is a line, not a chart.
reset();
drawVol(rows.slice(0, 2), "roi", GEOM);
ok(/next daily build/.test(DOM.volChart.textContent),
   "two priced days is not enough to draw");

// ---- a PARTIALLY covered window declines, naming where it starts ---
// The case the code's own guard exists for, and the one a 24-month
// window will actually hit: volume is emitted only once 200 days of
// degree days sit behind a day, so the early end of a long window can
// be bare. Plotting those at zero would read as "no heat that day".
reset();
const mixed = rows.map((r, i) => i < 12 ? {day: r.day} : r);
drawVol(mixed, "roi", GEOM);
ok(/does not cover the whole of this window/
   .test(DOM.volChart.textContent),
   "a part-covered window declines rather than plotting gaps as zero");
ok(DOM.volChart.textContent.indexOf(rows[12].day) > 0,
   "and the message names the day the volume starts");
ok(DOM.volLegend.innerHTML === "", "leaving no legend behind it");

// ---- the other jurisdiction is read from its own key ---------------
const ni = [];
for (let i = 0; i < 10; i++){
  const d = new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10);
  ni.push(row(d, 40 - i, 11.1, "ni"));
}
reset();
drawVol(ni, "ni", GEOM);
ok(/<svg/.test(DOM.volChart.innerHTML), "NI draws from vol_ni");
reset();
drawVol(ni, "roi", GEOM);
ok(/next daily build/.test(DOM.volChart.textContent),
   "and an NI-only payload does not draw under the ROI toggle");

// ---- the front end draws from a REAL columnar payload --------------
// The cost series is written columnar from pipeline 5.9.0. The
// asymmetry recorded for the history block applies here: a new
// payload needs the new front end. This proves the new front end
// reads one the pipeline actually produced, not a hand-built one.
const cols = JSON.parse(fs.readFileSync(
  path.join(__dirname, "fixtures", "cost_series_columnar.json"), "utf8"));
const expanded = expandHistory(cols);
ok(Array.isArray(expanded) && expanded.length === cols.n,
   "expandHistory returns one row per day of the columnar payload");
ok(expanded[0].day && expanded[0].vol_roi &&
   typeof expanded[0].vol_roi.space === "number",
   "nested route and volume blocks survive the expansion");
reset();
drawVol(expanded, "roi", GEOM);
ok(/<svg/.test(DOM.volChart.innerHTML) &&
   !/NaN|undefined/.test(DOM.volChart.innerHTML),
   "drawVol draws from an expanded columnar payload with no NaN");
ok(Array.isArray(expandHistory(expanded)),
   "and a plain list still passes through unchanged");

// ---- the window maps must be edited in step ------------------------
// SUMN and WLBL are two literals a hundred lines apart, and a window
// present in one and absent from the other prints "over the last
// undefined" on exactly that button and nowhere else. That shipped:
// 105 was missing from WLBL from the day the 24-month button existed.
// These four are declared INSIDE a function on the page, so the
// whole-block evaluation cannot reach them - it exposes top-level
// declarations only. Lifted by regex, which is what lift() is still
// here for.
function lift(re, what){
  const m = html.match(re);
  if(!m) throw new Error("could not find " + what + " in index.html");
  return m[0];
}
const maps = {};
for (const name of ["SUMN", "WLBL", "WNAME", "WSPAN"]){
  const src = lift(new RegExp("const " + name + "=\\{[\\s\\S]*?\\};"), name);
  maps[name] = eval("(" + src.replace(/^\s*const \w+=/, "")
                              .replace(/;$/, "") + ")");
}
for (const k of Object.keys(maps.SUMN)){
  if (maps.SUMN[k] > 0){
    ok(maps.WLBL[k] !== undefined, "WLBL has an entry for window " + k);
  }
  ok(maps.WNAME[k] !== undefined, "WNAME has an entry for window " + k);
  ok(maps.WSPAN[k] !== undefined, "WSPAN has an entry for window " + k);
}
for (const name of ["WLBL", "WNAME", "WSPAN"]){
  for (const k of Object.keys(maps[name])){
    ok(maps.SUMN[k] !== undefined,
       name + " has no orphan key " + k + " (window removed?)");
  }
}

// ---- the buttons agree with the maps -------------------------------
const winBtns = [...html.matchAll(/data-win="(\d+)"/g)].map(m => m[1]);
ok(winBtns.length === Object.keys(maps.SUMN).length,
   "one panel 1 button per window in SUMN");
winBtns.forEach(w => ok(maps.SUMN[w] !== undefined,
                        "panel 1 button " + w + " is a known window"));
const costBtns = [...html.matchAll(/data-cwin="(\d+)"/g)].map(m => +m[1]);
ok(!costBtns.includes(1825), "the 60-month cost button is gone");
ok(Math.max(...costBtns) === 730, "the widest cost window is 24 months");
ok(costBtns.includes(7), "and the 1-week window is offered");

// ---- the calibration board renders what the pipeline publishes -----
// The exhibit that answers "how do you know the COP model is right",
// so it has to survive a payload that predates it as well as one that
// carries it.
DOM.calBoard = null; el("calBoard");
calBoard({gate: 1.15, spread: 1.076, jurisdictions: {
  roi: {ashp:{eta:0.3175,spf_anchor:2.80,source_c:null},
        gshp:{eta:0.3342,spf_anchor:3.24,source_c:8.0},
        network:{eta:0.3106,spf_anchor:4.0,source_c:16.0}}}});
const cb = DOM.calBoard.innerHTML;
ok(/0\.3175/.test(cb) && /0\.3342/.test(cb) && /0\.3106/.test(cb),
   "calibration board prints every route's fraction");
// The page's fmt uses minimumFractionDigits:0, so 2.80 renders as
// "2.8". The old assertion passed only because the harness defined its
// own fmt stub - the renderer was never running against the real one.
ok(/2\.8/.test(cb) && /3\.24/.test(cb),
   "and the SPF anchor each one was solved to reproduce");
ok(/outdoor air/.test(cb), "air source's source is named, not left blank");
ok(/inside the 15% gate/.test(cb), "a passing spread says so");
DOM.calBoard = null; el("calBoard");
calBoard({gate: 1.15, spread: 1.21, jurisdictions: {
  ni: {ashp:{eta:0.30,spf_anchor:2.80,source_c:null},
       gshp:{eta:0.36,spf_anchor:3.24,source_c:8.0},
       network:{eta:0.363,spf_anchor:5.0,source_c:19.6}}}});
ok(/OUTSIDE the 15% gate/.test(DOM.calBoard.innerHTML),
   "and a failing spread is stated on the page, not just in the log");
DOM.calBoard = null; el("calBoard");
calBoard(null);
ok(/next daily build/.test(DOM.calBoard.textContent),
   "a payload without the calibration declines rather than drawing blank");

// ---- what heat emits: all-island, no jurisdiction toggle -----------
["emitBars","emitNote","emitMethod"].forEach(k=>{DOM[k]=null; el(k);});
emitPanel({grid_g_per_kwh: 212, grid_days: 14, network_spf_island: 4.252,
  routes: [
    {key:"gas_boiler",label:"Gas boiler",g_per_useful_kwh:241.2,spf:null},
    {key:"oil_boiler",label:"Oil boiler",g_per_useful_kwh:313.4,spf:null},
    {key:"resistive",label:"Resistive electric",g_per_useful_kwh:212,spf:1},
    {key:"ashp",label:"Air-source heat pump",g_per_useful_kwh:75.7,spf:2.8},
    {key:"gshp",label:"Ground source",g_per_useful_kwh:65.4,spf:3.24},
    {key:"network",label:"Geothermal heat network",
     g_per_useful_kwh:49.9,spf:4.252}]});
const eb = DOM.emitBars.innerHTML;
ok((eb.match(/emitrow/g)||[]).length === 6, "six routes, one bar each");
ok(/313/.test(eb) && /50/.test(eb), "values printed beside the bars");
ok(!/NaN|undefined/.test(eb), "no NaN in the bar widths");
// the three low-carbon routes are the highlighted ones
ok((eb.match(/emitbar on/g)||[]).length === 3,
   "the three heat-pump routes are highlighted, the three others are not");
// the longest bar is the oil boiler, the shortest the network
const w = [...eb.matchAll(/width:([\d.]+)%/g)].map(m=>parseFloat(m[1]));
ok(w.length===6 && w[1]===Math.max(...w) && w[5]===Math.min(...w),
   "oil is the longest bar and the geothermal network the shortest");
ok(/all-island market/.test(DOM.emitNote.textContent),
   "the note states why there is no jurisdiction toggle");
ok(/GEOTHERMAL, not the gas-fired network/.test(DOM.emitMethod.innerHTML),
   "the method fold does not inherit the gas-fired-network assumption");
ok(/harmonic/.test(DOM.emitMethod.innerHTML),
   "and says how the island SPF was combined");
["emitBars","emitNote","emitMethod"].forEach(k=>{DOM[k]=null; el(k);});
emitPanel(null);
ok(/next daily build/.test(DOM.emitBars.textContent),
   "an old payload declines rather than drawing an empty axis");

// ---- page order and the Panel 3 stub -------------------------------
const order = [...html.matchAll(/<section id="([a-z]+)"/g)].map(m=>m[1]);
// THE FRONTISPIECE LEADS. Six figures before the panels argue them;
// the numbered panels keep their order behind it, so this is pinned
// RELATIVE to the hero rather than by absolute index - adding a
// section above should not silently renumber the argument.
ok(order[0] === "front",
   "the frontispiece is the first section on the page");
ok(order.indexOf("grid") === order.indexOf("hero") + 2,
   "Panel 3 still sits two behind the hero");
ok(order.indexOf("oil") === order.length - 1,
   "the oil ticker has moved to the foot of the page");
ok(order.indexOf("why") < order.indexOf("oil"),
   "and sits beneath Why heat");
ok(html.split("<section ").length === html.split("</section>").length,
   "sections balance - the move did not eat an opening tag");
// the toggle switches whose heat, and says the ceiling is not toggled
const gj = [...html.matchAll(/data-gjur="([a-z]+)"/g)].map(m=>m[1]);
ok(gj.length === 3 && gj[0] === "all",
   "Panel 3 offers all-island, NI and ROI, defaulting to all-island");
ok(/single all-island market/.test(html)
   && /does\s+not\s+switch\s+the\s+ceiling/i.test(html),
   "and states that the toggle does not move the ceiling, with the reason");

// ---- Panel 3: the coldest hour, drawn from the published B.2.1 -----
const TH = {hour:"2026-01-05T17", observed_mw:7180, air_c:0.21,
  useful_heat_mw:11365, block_mw:8595, ceiling_mw:9713,
  wind_solar_mw:1118, heat_vs_block_ratio:1.32,
  added_mw:{air_source:3579, ground_source:2409, geothermal_network:1174},
  headroom_by_route_mw:{air_source:-1046, ground_source:124,
                        geothermal_network:1359},
  routes_that_fit:["ground_source","geothermal_network"],
  share_that_fits_pct:{air_source:70.6, ground_source:102.4,
                       geothermal_network:210.1},
  share_binding_hour:{air_source:"2026-01-05T17",
    ground_source:"2026-01-05T17", geothermal_network:"2026-01-05T17"}};
DOM.gridPanel = null; el("gridPanel");
gridPanel(TH);
const gp = DOM.gridPanel.innerHTML;
ok(!/NaN|undefined/.test(gp), "no NaN or undefined in the coldest hour");
ok(/\+3\.6 GW/.test(gp) && /\+1\.2 GW/.test(gp),
   "the increment each route adds is labelled on its bar");
// cards show the TOTAL requirement, as the UK sibling does, not just
// the increment - 7180 + 3579 = 10.8 GW for air source
ok(/10\.8/.test(gp) && /9\.6/.test(gp) && /8\.4/.test(gp),
   "cards show what the island's power stations would have to cover");
// fmt drops trailing zeroes (minimumFractionDigits:0), so 1.046 GW
// prints as "1 GW", not "1.0 GW". Both of these were written against
// the harness's own fmt stub and had never met the real one.
ok(/1 GW OVER the ceiling/.test(gp),
   "a route that does not fit says so, in GW over");
ok(/0\.1 GW of spare capacity left/.test(gp),
   "and one that does says how much spare is left");
ok(/capacity to deliver/.test(gp) && /stroke-dasharray/.test(gp),
   "the ceiling is a dashed rule across the chart, labelled");
// the ceiling label used to sit ON the line and ran through the bars,
// unreadable where it crossed them. It is now right-anchored above the
// line, and its composition sits in its own band at the top.
// the ceiling label was right-anchored above the line; on the share
// chart the equivalent 100% label still ran through the tallest bar.
// Both now sit in a band ABOVE the plot, so no label can cross a bar.
ok(/capacity to deliver/.test(gp) && !/text-anchor="end"[^>]*>capacity/.test(gp),
   "the ceiling label sits above the plot, not on the line");
ok(/de-rated dispatchable block/.test(gp)
   && /wind and solar that actually blew/.test(gp),
   "and the ceiling's composition is on its own line beneath it");
ok(!/capacity to deliver[^<]*GW \(/.test(gp),
   "the long parenthetical no longer rides on the dashed line");
// dates read as dates, not database keys
ok(/5 Jan 2026 \u00b7 17:00/.test(gp) && !/2026-01-05T17/.test(gp),
   "hours are labelled 5 Jan 2026 17:00, not 2026-01-05T17");
// axis ticks are round numbers, not an arbitrary maximum in thirds
ok(!/>151%</.test(gp) && !/>227%</.test(gp), "no ticks like 151% or 227%");
ok(/>100%</.test(gp) && />200%</.test(gp),
   "the share axis ticks on round hundreds");
ok((gp.match(/<rect /g)||[]).length === 9,
   "six rects for three two-part bars, plus three for the share chart");
ok(/102%/.test(gp) && /71%/.test(gp) && /210%/.test(gp),
   "the share sub-panel shows each route's share as a card and a bar");
ok(/100% = all of the island\u2019s building heat/.test(gp)
   && /stroke-dasharray/.test(gp),
   "with a dashed rule at 100%, labelled above the plot");
ok(/clears a full electrification of heat, with room over/.test(gp)
   && /the fleet binds before the heat is fully electrified/.test(gp),
   "and says plainly which routes clear it and which do not");
const ssvg = svgAt(gp, 1);
ok(gridlinesSpread(ssvg, 4), "the share chart's gridlines spread too");
ok(axisLabelReadable(ssvg), "and the share chart's label is legible too");
ok(tickValuesReadable(ssvg, 4), "and its tick values are legible");
ok(everyAxisTitled(ssvg), "every axis with numbers on it is named");
ok(noTextInsideBars(ssvg), "and no share label sits inside its bar");
ok(usesItsAxis(ssvg, 0.5), "and the share bars use their axis");
ok(/asked the other way round/.test(gp),
   "the note distinguishes the solved share from the fixed fifth above");
ok((gp.match(/<svg /g)||[]).length === 2,
   "two charts in the panel, one per sub-panel");
ok(/actual use/.test(gp) && /20% what-if/.test(gp),
   "the legend names the grey base and the coloured increment");
ok(/GW at the binding hour/.test(gp), "the y-axis is labelled");
// THE AXIS ITSELF. niceTicks returns GW while y() works in MW, and
// feeding one to the other put all seven gridlines on the baseline and
// printed seven zeroes. The suite passed throughout, because nothing
// checked that the ticks were distinct or that they spread.
const ticks = [...gp.matchAll(/text-anchor="end"[^>]*>(\d+)<\/text>/g)]
  .map(m => m[1]);
ok(ticks.length >= 4, "the y-axis has tick labels at all");
ok(new Set(ticks).size === ticks.length,
   "and they are distinct - not seven zeroes stacked on the baseline");
ok(ticks.indexOf("12") >= 0 && ticks.indexOf("0") >= 0,
   "running 0 to 12 GW, covering the tallest bar and the ceiling");
const gsvg = svgAt(gp, 0);
ok(gridlinesSpread(gsvg, 4), "the gridlines are at distinct heights");
ok(axisLabelReadable(gsvg), "its axis label clears the frame and is legible");
ok(tickValuesReadable(gsvg, 4), "and its tick values are legible too");
ok(everyAxisTitled(gsvg), "every axis with numbers on it is named");
ok(noTextInsideBars(gsvg), "no label is drawn inside a bar");
ok(usesItsAxis(gsvg, 0.5),
   "the bars use the height of the axis, not a corner of it");
// both dashed rules must be visible against a dark background
ok((gp.match(/stroke="#fff" stroke-width="2" stroke-dasharray="9 5"/g)||[])
   .length === 2,
   "the ceiling and the 100% rule are both white dashed rules");
ok(/hstats overbars/.test(gp),
   "the share cards are laid out to sit over their own bars");
ok(/tightest hour of the year/i.test(gp),
   "and the sub-panel carries the UK sibling's title");
ok(/1\.32x its power system/.test(gp),
   "the heat-system-against-power-system ratio is on the page");
ok(/peak-capacity test, not an energy test/.test(gp),
   "and the framing that must travel with it");
// the jurisdiction states must not show island figures under an NI label
setPageVar("GJUR", "ni"); DOM.gridPanel = null; el("gridPanel");
gridPanel(TH);
ok(/not built yet/.test(DOM.gridPanel.innerHTML)
   && !/GW/.test(DOM.gridPanel.innerHTML),
   "NI and ROI decline rather than relabelling the island figures");
setPageVar("GJUR", "all"); DOM.gridPanel = null; el("gridPanel");
gridPanel(null);
ok(/coming build/.test(DOM.gridPanel.innerHTML),
   "and a payload without the block declines cleanly");

// ---- Panel 3's three views -----------------------------------------
function gvRows(n, stamp){
  const out = [];
  for(let i = 0; i < n; i++){
    const cold = Math.cos(2 * Math.PI * i / n);
    out.push({t: stamp(i), heat_mw: 1200 + 900 * cold,
              temp_c: 10 - 6 * cold, demand_mw: 4200,
              air_source: 90 + 70 * cold, ground_source: 80 + 30 * cold,
              geothermal_network: 52 + 18 * cold});
  }
  return out;
}
const GV = {share: 0.2,
  hourly: gvRows(168, i => "2026-08-" + String(9 + Math.floor(i/24))
    .padStart(2,"0") + "T" + String(i%24).padStart(2,"0")),
  daily: gvRows(90, i => "2026-0" + (5 + Math.floor(i/31)) + "-"
    + String(1 + i%28).padStart(2,"0")),
  monthly: gvRows(14, i => "202" + (5 + Math.floor((6+i)/12)) + "-"
    + String(1 + (6+i)%12).padStart(2,"0"))};
["gridChart","gridLegend","gridViewNote"].forEach(k=>{DOM[k]=null; el(k);});
drawGridViews(GV);
const gc = DOM.gridChart.innerHTML;
ok(gc.indexOf("<svg") === 0, "the hourly view draws");
ok(!/NaN|undefined/.test(gc), "no NaN in the paths or the axes");
ok((gc.match(/<path /g)||[]).length === 4,
   "heat plus three routes, one path each");
ok(/stroke-dasharray/.test(gc),
   "heat delivered is dashed, so it reads as the demand not a route");
ok(/heat delivered, GW/.test(gc)
   && /electricity for the what-if, GW/.test(gc),
   "both axes are labelled - the two quantities differ by an order of "
   + "magnitude and one axis would flatten the electricity");
ok(gridlinesSpread(svgAt(gc, 0), 2),
   "the three-view chart's gridlines spread");
ok(axisLabelReadable(svgAt(gc, 0)),
   "and BOTH its axis labels clear their frames");
ok(tickValuesReadable(svgAt(gc, 0), 3),
   "and the three-view chart's ticks are legible");
ok(tickValuesReadable(svgAt(gc, 0), 3, "right"),
   "and its RIGHT electricity axis too - Panel 3 has two-axis charts");
ok(everyAxisTitled(svgAt(gc, 0)),
   "and both of its axes are named");
ok(/the fifth via geothermal network/.test(DOM.gridLegend.innerHTML),
   "the legend says these are the what-if's fifth, not all of it");
// the monthly view is the FALCON: a calendar year, each month the
// latest complete instance - Jan-Jul from this year, Aug-Dec from
// last. Twelve complete months is enough; it does not need two years.
GV.falcon = [];
for(let i = 1; i <= 12; i++){
  const src = i <= 7 ? "2026-" : "2025-";
  const cold = Math.cos(2 * Math.PI * (i - 1) / 12);
  GV.falcon.push({m: String(i).padStart(2,"0"),
    t: src + String(i).padStart(2,"0"),
    heat_mw: 1200 + 900*cold, temp_c: 10 - 6*cold, demand_mw: 4200,
    air_source: 90 + 70*cold, ground_source: 80 + 30*cold,
    geothermal_network: 52 + 18*cold});
}
GV.falcon_complete = 12;
setPageVar("GVIEW", "monthly");
["gridChart","gridViewNote"].forEach(k=>{DOM[k]=null; el(k);});
drawGridViews(GV);
ok(/falcon curve/.test(DOM.gridViewNote.textContent)
   && /12\/12 months/.test(DOM.gridViewNote.textContent),
   "the monthly view is the falcon and reports how many months it has");
const fc = DOM.gridChart.innerHTML;
ok(/>Jan 26</.test(fc) && /># *Dec 25</.test(fc) === false
   && /Dec 25/.test(fc),
   "and its axis runs the calendar year, Jan from this year and Dec "
   + "from last");
ok(!/NaN/.test(fc), "no NaN in the falcon");
setPageVar("GVIEW", "daily");
["gridChart","gridViewNote"].forEach(k=>{DOM[k]=null; el(k);});
drawGridViews(GV);
ok(/90 points/.test(DOM.gridViewNote.textContent),
   "and each view reports its own point count and span");
setPageVar("GVIEW", "hourly");
["gridChart","gridLegend"].forEach(k=>{DOM[k]=null; el(k);});
drawGridViews(null);
ok(/next daily build/.test(DOM.gridChart.textContent),
   "a payload without the series declines rather than drawing empty axes");

// ---- dispatch-down: stacked by reason, monthly since 2021 ----------
const ddFix = JSON.parse(require("fs").readFileSync(
  __dirname + "/../docs/dispatch_down_monthly.json", "utf8"));
const DD = {months: ddFix.months, unit: "GWh", technology: "Wind",
  spf: {ashp: 2.8, gshp: 3.24, network: 4.252},
  reasons: [{key:"trans",label:"Transmission constraint",group:"constraint"},
            {key:"test",label:"TSO testing",group:"constraint"},
            {key:"hifrq",label:"High frequency / minimum generation",
             group:"curtailment"},
            {key:"snsp",label:"SNSP limit",group:"curtailment"},
            {key:"rocof",label:"RoCoF / inertia",group:"curtailment"},
            {key:"other",label:"Other reductions",group:"other"}],
  jurisdictions: {}};
["IE","NI"].forEach(j=>{
  const b = ddFix.jurisdictions[j];
  DD.jurisdictions[j] = Object.assign({}, b, {
    rate_pct: b.dd.map((v,i)=> b.avail[i] ? 100*v/b.avail[i] : null),
    heat: {network: b.dd.map(v=>v*4.252)}});
});
["ddChart","ddNote"].forEach(k=>{DOM[k]=null; el(k);});
ddPanel(DD);
const dc = DOM.ddChart.innerHTML;
ok(!/NaN|undefined/.test(dc), "no NaN in the dispatch-down chart");
ok(ddFix.months.length >= 60, "the series reaches back to 2021");
ok(/2021/.test(dc) && /2026/.test(dc), "the x-axis is labelled by year");
ok(/Northern Ireland/.test(dc) && /local constraint/.test(dc),
   "the header names the jurisdiction and its constraint share");
// stacked by REASON, not by the constraint/curtailment fold - the fold
// hides that NI's spill is overwhelmingly the local kind
ok(/Transmission constraint \(constraint\)/.test(dc)
   && /SNSP limit \(curtailment\)/.test(dc),
   "the legend names each reason and which group it belongs to");
const dsvg = svgAt(dc, 0);
ok(gridlinesSpread(dsvg, 4), "the dispatch-down gridlines spread");
ok(axisLabelReadable(dsvg), "and its axis label is legible");
ok(tickValuesReadable(dsvg, 4), "and its tick values are legible");
ok(tickValuesReadable(dsvg, 3, "right"),
   "and its RIGHT percentage axis carries legible values too");
ok(everyAxisTitled(dsvg),
   "and BOTH its axes are named, not just the left one");
ok(noTextInsideBars(dsvg), "no dispatch-down label sits inside a bar");
ok(usesItsAxis(dsvg, 0.5), "and its bars use the axis height");
ok(/stroke-dasharray/.test(dc) && /share of available wind spilled/.test(dc),
   "the rate rides on a second axis as a dashed line");
ok(/energy-scale statement, not a dispatch claim/.test(DOM.ddNote.textContent),
   "the heat conversion carries its own caveat");
// the two jurisdictions must actually differ
const niHead = dc.match(/(\d+)% local constraint/)[1];
setPageVar("DDJUR", "IE"); ["ddChart","ddNote"].forEach(k=>{DOM[k]=null; el(k);});
ddPanel(DD);
const ieHead = DOM.ddChart.innerHTML.match(/(\d+)% local constraint/)[1];
ok(+niHead > +ieHead + 15,
   "Northern Ireland's spill is far more local than the Republic's");
setPageVar("DDJUR", "NI"); ["ddChart","ddNote"].forEach(k=>{DOM[k]=null; el(k);});
ddPanel(null);
ok(/coming build/.test(DOM.ddChart.textContent),
   "and a payload without the series declines cleanly");

// ---- what the spilled energy was worth ----------------------------
DD.price_month_mean = ddFix.price_month_mean;
["IE","NI"].forEach(j=>{
  const src = ddFix.jurisdictions[j], b = DD.jurisdictions[j];
  b.value_eur_m = {};
  ["dd","cons","curt"].forEach(k=>{
    const pk = src["price_" + k] || [];
    b.value_eur_m[k] = src[k].map((v,i)=>
      (pk[i] && v) ? +(v*pk[i]/1000).toFixed(2) : 0);
  });
  b.value_naive_eur_m = src.dd.map((v,i)=>
    ddFix.price_month_mean[i] ? +(v*ddFix.price_month_mean[i]/1000).toFixed(2) : 0);
});
["ddValue","ddValueNote"].forEach(k=>{DOM[k]=null; el(k);});
ddValue(DD);
const dv = DOM.ddValue.innerHTML;
ok(!/NaN|undefined/.test(dv), "no NaN in the value chart");
const vsvg = svgAt(dv, 0);
ok(gridlinesSpread(vsvg, 4), "the value chart's gridlines spread");
ok(axisLabelReadable(vsvg, 88), "and its axis label is legible");
ok(tickValuesReadable(vsvg, 4), "and its tick values are legible");
ok(everyAxisTitled(vsvg), "every axis with numbers on it is named");
ok(noTextInsideBars(vsvg), "no value label sits inside a bar");
// The axis on this chart is scaled to the NAIVE comparator line, which
// sits above the bars by construction - that gap is the finding. So
// the bars cannot fill it, and the threshold is lower here than on the
// charts where the bars set their own scale.
ok(usesItsAxis(vsvg, 0.3), "and its bars use the axis height");
// THE POINT OF THE CHART: the weighted total must come out materially
// BELOW the naive one. If a future join misaligns, the two converge -
// which is exactly how the first attempt failed, and it looked
// plausible rather than broken.
const b = DD.jurisdictions.NI;
const wtd = b.value_eur_m.dd.reduce((a,v)=>a+v,0);
const naive = b.value_naive_eur_m.reduce((a,v)=>a+v,0);
ok(wtd < naive * 0.8,
   "spilled wind is worth materially less than the monthly average implies");
ok(wtd > naive * 0.3, "but not implausibly less - the join is not broken");
// the value-and-capture argument moved into the method fold when
// Panel 3's notes were shortened; render it here to police it
el("gridMethod");
gridMethod(ddFix, null);
const gmEarly = DOM.gridMethod.innerHTML;
// constraint must be worth more per MWh than curtailment
const pc = ddFix.jurisdictions.NI.price_cons.filter(v=>v),
      pu = ddFix.jurisdictions.NI.price_curt.filter(v=>v);
const mean = a => a.reduce((x,y)=>x+y,0)/a.length;
ok(mean(pc) > mean(pu) * 1.15,
   "constraint hours clear well above curtailment hours");
ok(/already compensated/.test(gmEarly)
   && /generator/.test(gmEarly),
   "the note says who would capture it, and that it differs by reason");
ok(/upper bound/.test(gmEarly),
   "and that delivering the energy would itself soften the price");
ok(!/value lost/i.test(dv) && /was worth/.test(html),
   "the chart is titled what the energy was worth, not value lost");
["ddValue","ddValueNote"].forEach(k=>{DOM[k]=null; el(k);});
ddValue(null);
ok(/coming build/.test(DOM.ddValue.textContent),
   "and it declines cleanly without the series");

// ---- worked examples: sizing the sink, not claiming a saving ------
["oddEx","oddExNote"].forEach(k=>{DOM[k]=null; el(k);});
const oddFix = {basis_from:"2025-07", basis_to:"2026-06", basis_months:12,
  constrained_gwh:656.1, heat_gwh:2789.6,
  ni_delivered_heat_gwh:10888, share_of_ni_heat_pct:25.6,
  hospital:{eui_kwh_m2:211, heat_share:0.6, floor_m2:55000,
            heat_gwh:7.0, equivalent:401,
            source:"ERIC 2024/25 acute mean, heat share \u2020"},
  routes:{ashp:{spf:2.8, heat_gwh:1837.0, share_pct:16.9},
          gshp:{spf:3.24, heat_gwh:2125.6, share_pct:19.5},
          network:{spf:4.252, heat_gwh:2789.6, share_pct:25.6}},
  domestic:{subscribers:250000, constraint_cut_pct:67,
            curtailment_cut_pct:74, household_saving_gbp:220,
            farm_10mw_gbp:19400, operator_saving_pct:78,
            cite:"Agbonaye, Keatley, Huang, Odiase & Hewitt (2022), "
                 + "Renewable Energy 190:487\u2013500"}};
oddExamples(oddFix);
const ox = DOM.oddEx.innerHTML, oxn = DOM.oddExNote.innerHTML;
// THE METHOD FOLD. Panel 3's notes were shortened to their
// findings and the defence moved here; these pins moved with the
// text, so the claims are still policed - just in their new home.
el("gridMethod");
gridMethod(ddFix, oddFix);
const gmFold = DOM.gridMethod.innerHTML;
ok(!/NaN|undefined/.test(ox + oxn), "no NaN in the worked examples");
// the unit sits in a nested span, so figure and unit are not
// contiguous in the markup
ok(/2,790/.test(ox) && /GWh/.test(ox) && /26</.test(ox),
   "the heat volume and its share of NI building heat are stated");
// A ROLLING window, not a calendar year: it keeps the panel current
// without waiting for a year to close, and it lands on the same months
// as the hourly store so a spill-weighted COP will cover exactly these.
ok(/12 months to Jun 26/.test(ox) && /Jul 25 to Jun 26/.test(ox),
   "and the window is named at both ends, not left as a year");
ok(!/\b2025\b(?!-)/.test(ox), "the panel does not claim a calendar year");
ok(/401/.test(ox) && /ten acute sites/.test(ox),
   "the hospital count is set against the size of the actual estate");
ok(/250k/.test(ox) && /74% less curtailment/.test(ox),
   "and the published domestic optimum sits beside it");
// THE EPISTEMIC LABEL. This panel is a different kind of claim from
// everything above it and must say so, or it reads as measurement.
ok(/Worked examples/.test(oxn) && /not\s+measurements/.test(oxn),
   "the panel declares itself worked examples, not measurements");
ok(/size the LOAD it would take, not heat delivered/.test(oxn),
   "and that it sizes the load rather than claiming heat delivered");
ok(/outside the heating season/.test(gmFold) && /storage/.test(gmFold),
   "the coincidence objection is stated, not left for a reviewer");
// Agbonaye is quoted, attributed and not re-derived - the supervisor
// is a named peer reviewer, so the citation has to be exact
ok(/Agbonaye, Keatley, Huang, Odiase &amp; Hewitt \(2022\)/.test(gmFold)
   || /Agbonaye, Keatley, Huang, Odiase & Hewitt \(2022\)/.test(gmFold),
   "the domestic figures are attributed to the paper in full");
ok(/Renewable Energy 190:487/.test(gmFold), "with the journal reference");
ok(/quoted rather than re-derived/.test(gmFold),
   "and stated as quoted rather than recomputed");
// the hospital benchmark's weakest joint must be admitted
ok(/heat share is[\s\S]{0,20}ours/.test(gmFold)
   && /ERIC publishes total energy/.test(gmFold),
   "the hospital heat share is declared as ours, not ERIC's");
["oddEx","oddExNote"].forEach(k=>{DOM[k]=null; el(k);});
oddExamples(null);
ok(/coming build/.test(DOM.oddEx.textContent),
   "and the panel declines cleanly without the block");
// THE ROUTES MUST DIFFERENTIATE. Without this the panel implies one
// heat pump is as good as another for absorbing the spill, which is
// the opposite of the argument.
ok(/16\.9%/.test(ox) && /19\.5%/.test(ox) && /25\.6%/.test(ox),
   "each route's share of NI heat from the same spilled electricity");
ok(/Air source/.test(ox) && /Geothermal network/.test(ox),
   "named per route, not folded into one figure");
ok(/storage measured in months rather than hours/.test(gmFold),
   "and the storage-duration discriminator is stated as the larger one");
ok(/property of the route rather than[\s\S]{0,20}of the machine/.test(gmFold),
   "framed as a property of the route rather than of the heat pump");
// THE CONSTRAINT-GROUP ARGUMENT. Panel 3's ceiling is all-island and
// correct; the locational layer is what it used to omit. These pin the
// parts a grid engineer would test: that adequacy and deliverability
// are distinguished, that the shift-factor mechanism is GIVEN rather
// than asserted, that the two-sided cost is admitted, and that
// valuation is handed to Panel 6 rather than duplicated here.
ok(/ADEQUACY/.test(gmFold) && /[Dd]eliverability is separate/.test(gmFold),
   "the fold separates adequacy from deliverability");
ok(/SHIFT FACTOR/.test(gmFold)
   && /identical shift factor with[\s\S]{0,20}the opposite sign/.test(gmFold),
   "and gives the mechanism, not just the claim");
ok(/five Northern Irish wind constraint groups/.test(gmFold),
   "the five groups are named as five");
ok(/voltage-stability[\s\S]{0,80}Republic/.test(gmFold),
   "the voltage-stability exception is stated, not buried");
ok(/cuts against heat in the binding[\s\S]{0,20}hour/.test(gmFold),
   "the binding-hour cost of local load is admitted");
ok(/[Dd]istribution headroom, not the/.test(gmFold),
   "and distribution headroom is named as the real siting screen");

// ---- every CSS variable used must be defined ----------------------
// --ink2 was used in sixteen places and never declared. In CSS an
// invalid var() makes the property inherit, which looks fine; in an
// SVG fill attribute it falls back to BLACK, so axis ticks drawn in it
// were black on a near-black background. Present in the markup,
// invisible on the page, and passing every test that asked whether the
// text existed. Nothing about the geometry was wrong - it was a
// colour that did not exist.
{
  const declared = new Set(
    [...html.matchAll(/(--[a-z0-9-]+)\s*:/gi)].map(m => m[1]));
  const used = new Set(
    [...html.matchAll(/var\((--[a-z0-9-]+)/gi)].map(m => m[1]));
  const missing = [...used].filter(v => !declared.has(v));
  ok(missing.length === 0,
     "every CSS variable used is defined" +
     (missing.length ? " - missing: " + missing.join(", ") : ""));
  // and the SVG charts must not paint text in a bare fallback
  ok(!/fill="var\(--[a-z0-9-]+\)"[^>]*>\s*<\/text>/i.test(html),
     "no chart text is painted with an empty fill");
}

// ---- Panel 4: hard activity segments, four bars -------------------
["coolTiers","coolTiersNote","coolTierDefs","coolMethod","coolSub"]
  .forEach(k=>{DOM[k]=null; el(k);});
const CT = {base_year:2023, proj_year:2034, scope:"Republic of Ireland",
  unit:"TWh", service_twh:15.8, service_proj_twh:22.7,
  elec_proj_twh:6.65, elec_proj_geo_twh:5.87, geo_saving_twh:0.78,
  geo_saving_pct:11.8, geo_eer:15.0, whatif_share:0.2, industry_eer:3.0,
  dc_eer:6.0, whatif_excluded:["datacentres"],
  archetypes_with_cooling:[62,181], ni_all_twh:1.2,
  tier_totals_twh:{"0":13.95,"1":1.25,"m":0.69},
  tier_totals_segments_twh:{"0":6.06,"1":1.25,"m":0.69},
  source:"SEAI National Heat Study Figures 52-53; Technical Annex 2025",
  tier_defs:[{key:"tier0",label:"Tier 0 \u00b7 process",text:"Runs regardless."},
             {key:"tier1",label:"Tier 1 \u00b7 comfort, equipped",text:"Installed plant."},
             {key:"tier2",label:"Tier 2 \u00b7 comfort, unequipped",text:"No cooling to draw."}],
  segments:[
    {label:"Retail",service_twh:5.48,elec_twh:2.63,per_archetype_mwh:168,sector:"comm",tier:0},
    {label:"Restaurant/public house",service_twh:0.47,elec_twh:0.23,per_archetype_mwh:50,sector:"comm",tier:0},
    {label:"Warehouse and storage",service_twh:0.11,elec_twh:0.05,per_archetype_mwh:570,sector:"comm",tier:0},
    {label:"Hotel",service_twh:0.48,elec_twh:0.23,per_archetype_mwh:377,sector:"comm",tier:"m"},
    {label:"Healthcare",service_twh:0.21,elec_twh:0.08,per_archetype_mwh:121,sector:"pub",tier:"m"},
    {label:"Office (commercial)",service_twh:0.96,elec_twh:0.46,per_archetype_mwh:101,sector:"comm",tier:1},
    {label:"Office (public)",service_twh:0.26,elec_twh:0.10,per_archetype_mwh:205,sector:"pub",tier:1},
    {label:"Education",service_twh:0.03,elec_twh:0.01,per_archetype_mwh:305,sector:"pub",tier:1}],
  tiers:[{key:"datacentres",label:"Data centres",group:"process",
          service_twh:5.4,elec_twh:0.9,eer:6.0,eer_is_ours:true,
          service_proj_twh:12.32,elec_proj_twh:2.05,held:false},
         {key:"industry",label:"Industry",group:"process",
          service_twh:2.4,elec_twh:0.8,eer:3.0,eer_is_ours:true,
          service_proj_twh:2.4,elec_proj_twh:0.8,held:true},
         {key:"commercial",label:"Commercial",group:"mixed",
          service_twh:7.5,elec_twh:3.6,eer:2.08,eer_is_ours:false,
          service_proj_twh:7.5,elec_proj_twh:3.6,held:true},
         {key:"public",label:"Public",group:"mixed",
          service_twh:0.5,elec_twh:0.2,eer:2.5,eer_is_ours:false,
          service_proj_twh:0.5,elec_proj_twh:0.2,held:true}]};
coolTiers(CT);
const ck = DOM.coolTiers.innerHTML, csvg = svgAt(ck, 0);
ok(!/NaN|undefined/.test(ck), "no NaN in the cooling bars");
ok(axisLabelReadable(csvg), "its axis labels are legible");
ok(tickValuesReadable(csvg, 4, "bottom"),
   "and its bottom value axis carries legible ticks");
// HARD SEGMENTS, NOT A GRADIENT. The activity split is sourced and
// reconciles, so the boundary is drawn rather than implied.
ok(!/linearGradient/.test(csvg),
   "no gradient - the boundary is drawn, not shaded");
ok((csvg.match(/<rect /g)||[]).length === 40,
   "ten activity segments across four bars");
ok(/Retail 5\.48/.test(csvg) && /Office \(commercial\) 0\.96/.test(csvg),
   "segments are labelled with their activity and figure");
// Segments too narrow to label on the chart - warehousing is 0.11 TWh
// on a 24 TWh axis, about four pixels - are carried in the method
// table instead rather than crowded onto the bar.
ok(!/Warehouse and storage/.test(csvg)
   && /Warehouse and storage/.test(DOM.coolMethod.innerHTML),
   "segments too narrow to label appear in the method table instead");
// tier colouring must be by TIER, not by sector
// ONE COLOUR PER SECTOR, in three tier families. Ten segments sharing
// three colours made adjacent same-tier blocks merge into one shape,
// and the changed proportions between bars read as reordering.
{
  const fills = [...csvg.matchAll(/<rect [^>]*fill="(#[0-9A-Fa-f]{6})"/g)]
    .map(m => m[1]);
  const uniq = new Set(fills);
  ok(uniq.size === 10, "ten distinct sector colours, one per segment");
  // and the SAME colour in the same order on every bar - the order is
  // sorted on the 2023 value throughout, so nothing reverses
  const perBar = [fills.slice(0,10), fills.slice(10,20),
                  fills.slice(20,30), fills.slice(30,40)];
  // NOTE: structurally guaranteed today, because coolSegs sorts once
  // and all four bars share that array. It guards a future change that
  // sorts per bar, and cannot be proven by mutation against the
  // current code.
  ok(perBar.every(b => b.join() === perBar[0].join()),
     "the colour sequence is identical on all four bars");
}
ok(/Tier 0 \u00b7 process|Tier 0 · process/.test(ck)
   && /mixed under one roof/.test(ck) && /Tier 1/.test(ck),
   "the legend groups the sectors under their tiers");
ok(/coolleg-grp/.test(ck) && /Data centres<\/span>/.test(ck)
   && /Retail<\/span>/.test(ck),
   "and names every sector inside its group");
// the units change halfway
ok(/cooling delivered/.test(csvg) && /electricity bought/.test(csvg),
   "the two groups are named - service above, electricity below");
ok(/% less electricity/.test(csvg),
   "the geothermal dividend is marked between bars 3 and 4");
// Tier 2 now carries SEAI's own archetype finding
ok(/62 of 181/.test(ck),
   "Tier 2 cites SEAI's own count of archetypes with any cooling");
// THE HEADLINE SPLIT MUST COVER THE WHOLE BAR. tier_totals_twh once
// summed the activity segments only, reporting Tier 0 as 6.06 and
// silently omitting data centres and industry - both Tier 0, and
// between them more than half of it.
ok(/Tier 0 process is 13\.9|Tier 0 process is 14/.test(
     DOM.coolTiersNote.textContent),
   "the note gives the whole-bar Tier 0, not just the segments");
ok(/88%/.test(DOM.coolTiersNote.textContent)
   && /8%/.test(DOM.coolTiersNote.textContent),
   "and both tiers as a share of the total");
// LABELS MUST NOT COLLIDE. Lanes were cycled by index, so two narrow
// blocks either side of a wide one overprinted each other.
{
  const lab = texts(csvg).filter(t => /\d\.\d\d$/.test(t.body.trim()));
  const byLane = {};
  lab.forEach(t => { (byLane[Math.round(t.y)] ||= []).push(t); });
  let clash = false;
  Object.values(byLane).forEach(row => {
    row.sort((a,b)=>a.x-b.x);
    for(let i=1;i<row.length;i++){
      const halfA = row[i-1].body.length*2.8, halfB = row[i].body.length*2.8;
      if(row[i].x - halfB < row[i-1].x + halfA) clash = true;
    }
  });
  // NOTE: unproven by mutation. Reverting to index-cycled lanes does
  // not reproduce a clash on THIS fixture, though it did on the live
  // figures. The check is correct in principle and currently untested
  // against a real failure.
  ok(!clash, "no two segment labels overlap on the same lane");
}
// the method fold
const cm = DOM.coolMethod.innerHTML;
// ONE judgement, not two: the data centre factor is arithmetic
// (5.5 TWh removed for 0.9) and the commercial and public factors are
// SEAI's own ratios. Only industrial process is ours.
ok(/One EER is ours: industrial process/.test(cm),
   "the method fold names the single judgement");
ok(/enlarges the service bars but SHRINKS the geothermal what-if/.test(cm),
   "and says the judgement cuts against our own argument");
ok(/both read one set of constants/.test(cm)
   && /CUT the same quantity differently/.test(cm),
   "the reconciliation with the energy-balance panel is in the fold");
ok(/effective EER of 6/.test(cm) && /never models free cooling/.test(cm),
   "the data centre EER is stated with why SEAI's cannot be used");
ok(/data centres are excluded from the what-if/i.test(cm)
   && /fan moving 10/.test(cm), "the exclusion is stated with its reason");
// AND IT MUST BE ON THE CHART, not only in the fold. The two
// sub-panels use different populations and a reader comparing them
// needs to see which without opening anything.
ok(/DATA CENTRES OUT of the geothermal what-if/.test(csvg),
   "the cooling chart says data centres are OUT, on its face");
ok(/borefield in data centres is seasonal storage, not cheaper cooling/
     .test(cm),
   "and the case is put where it actually rests");
// the sub-heading total must come from the payload, not be typed: it
// said "eleven terawatt-hours" long after the figure reached 15.9
ok(DOM.coolSub.innerHTML.indexOf(CT.service_twh + " terawatt-hours")
     >= 0,
   "the sub-heading takes its total from the payload, not typed text");
ok(/activity split is hard, not judged/i.test(cm)
   && /exceeds that of all other archetypes combined/.test(cm),
   "retail's attribution is quoted to SEAI, not asserted by us");
ok(/MWh per archetype/.test(cm) && /26,000 buildings/.test(cm),
   "the concentration column from Figure 53 is carried and explained");
ok(/holds commercial and public cooling constant to 2050/.test(cm),
   "and the held-not-forecast treatment is attributed to SEAI");
// AND THE CHART MUST HONOUR THE EXCLUSION - not just the prose
{
  const rs = rects(csvg).filter(r => r.w > 0);
  const b3 = rs.slice(20, 30), b4 = rs.slice(30, 40);
  // segments are ordered tier-then-size, so retail leads and data
  // centres sit second - find by position rather than assume first
  ok(Math.abs(b3[1].w - b4[1].w) < 0.5,
     "the data centre block is identical on bars 3 and 4 - excluded");
  ok(b4[0].w < b3[0].w - 0.5,
     "while retail does shrink, so the what-if is still applied");
}
["coolTiers","coolTiersNote","coolTierDefs","coolMethod"]
  .forEach(k=>{DOM[k]=null; el(k);});
coolTiers(null);
ok(/coming build/.test(DOM.coolTiers.textContent),
   "and the panel declines cleanly without the block");

// ---- and the heat it rejects --------------------------------------
["heatReject","heatRejectNote"].forEach(k=>{DOM[k]=null; el(k);});
heatReject({share:0.2, banked_twh:2.21, recovered_twh:1.55,
  rejected_twh:4.28, roundtrip:0.70, roundtrip_range:[0.5,0.8],
  recovered_range_twh:[1.11,1.77], summer_fraction:0.5,
  share_of_roi_heat_pct:6.1,
  rows:[{key:"datacentres",label:"Data centres",rejected_twh:6.4,
         continuous:true,summer_twh:3.2},
        {key:"industry",label:"Industry",rejected_twh:3.2,
         continuous:true,summer_twh:1.6},
        {key:"commercial",label:"Commercial",rejected_twh:11.1,
         continuous:true,summer_twh:5.55},
        {key:"public",label:"Public",rejected_twh:0.7,
         continuous:false,summer_twh:0.7}]});
const hj = DOM.heatReject.innerHTML, hn = DOM.heatRejectNote.innerHTML;
ok(!/NaN|undefined/.test(hj + hn), "no NaN in the rejection panel");
ok(/2,210 GWh/.test(hj) && /1,550 GWh/.test(hj),
   "both bars carry their figure");
ok(/bankHatch/.test(hj),
   "the summer bar is hatched - available and currently thrown away");
// LAYOUT. The header was added at y=20 while the bars kept their old
// y of 20, so it printed straight through the first bar; and the row
// labels were 31 monospace characters at 13px against a 250-unit
// gutter, which clipped the leading S off the viewBox.
{
  const hsvg = svgAt(hj, 0);
  const hdr = texts(hsvg).filter(t => /DATA CENTRES IN/.test(t.body))[0];
  const bars = rects(hsvg).filter(r => r.h > 20);
  ok(hdr && bars.length && hdr.y + 4 < Math.min(...bars.map(r=>r.y)),
     "the header sits above the bars, not through them");
  const rows = texts(hsvg).filter(t => /REJECTED TO STORE|RECOVERED/.test(t.body));
  ok(rows.length === 2 && rows.every(t => {
       const size = +(t.attr.match(/font-size="(\d+)"/)||[0,12])[1];
       return t.x - t.body.length * size * 0.6 > 0;
     }), "the row labels fit inside the viewBox, not clipped at the left");
}
// the recovered bar must be SHORTER than the banked one, at 70%
{
  const rs = rects(hj).filter(r => r.w > 1 && r.h > 20);
  const filled = rs.filter(r => r.w < 590);
  ok(filled.length >= 2 && filled[1].w < filled[0].w,
     "the recovered bar is shorter than the banked one");
}
// DATA CENTRES ARE IN, unlike the cooling what-if above
ok(/whole facility draw, IT load included/.test(hn),
   "data centre rejection is the whole draw, not the cooling block");
// THE MULTIPLICATIVE POINT is what makes this Irish rather than a port
ok(/reject continuously/.test(hn) && /only the summer half strands/.test(hn),
   "the note distinguishes continuous sources from summer-only ones");
ok(/roughly half to nearly all/.test(hn),
   "and states the multiplicative effect a store has on a continuous source");
ok(/Tallaght/.test(hn), "citing the scheme that already does it");
// THE OTHER HALF OF THE PAIR: in here, out above, and the note must
// say why rather than leaving "that same fifth" to mislead.
ok(/DATA CENTRES IN/.test(hj),
   "the rejection chart says data centres are IN, on its face");
ok(/A different fifth from the bars above/.test(hn),
   "and the note declares it is a different fifth, not the same one");
ok(/for a data centre it means a heat offtake added/.test(hn),
   "explaining that the intervention differs by sector");
// the Tallaght sentence moved out of the opening paragraph in
// editing; it still appears later, where the continuous sources are
// described
ok(/Tallaght already does with a Dublin data centre/.test(hn),
   "Tallaght is cited where continuous rejection is explained");
ok(/air-source network structurally cannot do/.test(hn),
   "and what the alternative cannot do");
ok(/50\u201380%|50–80%/.test(hn),
   "the round-trip range is given, not just the central figure");
["heatReject","heatRejectNote"].forEach(k=>{DOM[k]=null; el(k);});
heatReject(null);
ok(/coming build/.test(DOM.heatReject.textContent),
   "and it declines cleanly without the block");

// ---- Panel 5: geothermal, now and next ----------------------------
["geoTargets","geoTargetsNote","geoHardware","geoHardwareNote",
 "geoCalib","geoCalibNote","geoMethod"].forEach(k=>{DOM[k]=null; el(k);});
const GEOT = {geothermal_targets:[], whatif_share:0.2,
  roi_delivered_twh:25.3, ni_delivered_twh:10.9, island_delivered_twh:36.2,
  roi_vs_dh:{fifth_twh:5.06, dh_target_twh:2.7, multiple:1.9},
  nearest:[{jur:"ROI",label:"District heating",value:2.7,unit:"TWh/yr",
            year:2030,status:"government commitment",
            covers:"all heat sources, no geothermal share",
            source:"Climate Action Plan 2025"},
           {jur:"ROI",label:"Heat pumps installed",value:680000,
            unit:"units",year:2030,status:"government commitment",
            covers:"air and ground source, no ground-source share",
            source:"Climate Action Plan 2025"},
           {jur:"NI",label:"Energy saved, buildings and industry",
            value:8000,unit:"GWh",year:2030,status:"strategy target",
            covers:"all savings measures, buildings AND industry",
            source:"NI Energy Strategy, DfE 2021",achieved_gwh:90}],
  ni_energy_saved:{target_gwh:8000,achieved_gwh:90,achieved_pct:1.1,
    whatif_delivered_twh:2.18,counterfactual_input_twh:2.60,
    saved_gwh:{gshp:1928,network:2164},saved_pct:{gshp:24,network:27}}};
const GEOH = {island_gshp_MWth:225, island_ni_MWth:6.6,
  island_total_MWth:231.6, whatif_MWth:3622, multiple:15.6, eflh:2000,
  delivered_heat_TWh:36.2, roi_units:20128, internal_gap:14,
  per_person_W:{roi:42,ni:3,sweden:773,france:34,netherlands:140},
  sales_2025:{Ireland:1409,Sweden:26785},
  comparators:[{name:"France",gshp_MWth:2293,deep_MWth:724},
               {name:"Netherlands",gshp_MWth:2486,deep_MWth:367},
               {name:"Sweden",gshp_MWth:8120,deep_MWth:47}],
  register_threshold_kw:45, ni_register_confirmed:8, ni_register_total:10,
  ni_register_totals:{documented:10, operational_clean:2,
    operational_any:4, failed:4, unconfirmed:2,
    delivered_heating_kw:460, delivered_cooling_kw:120,
    nameplate_heating_kw:532, heating_shortfall_kw:72},
  sources:{roi:"WGC2026 Country Update: Ireland \u2014 Ireland, Blake, "
              + "Pasquali, Dunphy & Hunter Williams, June 2026",
           ni_register:"Causeway Energies register of Northern Ireland "
              + "ground-source schemes above 45 kW, compiled site by "
              + "site and currently circulating for comment among "
              + "Northern Ireland practitioners",
           ni_domestic:"MCS certification records, ~386\u2013450 units, "
              + "plus a pre-certification estimate \u2014 Causeway "
              + "triangulation",
           comparators:"EGC 2025 country updates (Sanner et al., Tables "
              + "3\u20134, end-2024) \u2014 shared with the UK sibling"},
  flh_ireland:1301, flh_europe_avg:2420,
  output_source:"EGC 2025 Country Update Summary, Sanner et al., Table 4",
  jur:{roi:{installed_MWth:224.4,whatif_MWth:3894,multiple:17.0,
            delivered_TWh:25.3,national_heat_TWh:30.8,share_pct:0.95,
            output_gwh:291.9,output_reported:true,
            per_person_W:42,units:20128,population_m:5.3},
       ni:{installed_MWth:4.5,whatif_MWth:1674,multiple:372.0,
           delivered_TWh:10.9,national_heat_TWh:13.0,share_pct:0.05,
           output_gwh:5.9,output_reported:false,
           per_person_W:2,units:null,population_m:1.92}},
  share_of_national_heat:{whatif_pct:20.0,countries:[
    {name:"Ireland",national_heat_TWh:44,share_pct:0.67,
     output_gwh:291.9,flh:1301},
    {name:"France",national_heat_TWh:350,share_pct:1.36,
     output_gwh:4750,flh:2072},
    {name:"Netherlands",national_heat_TWh:115,share_pct:2.37,
     output_gwh:2722,flh:1095},
    {name:"Sweden",national_heat_TWh:80,share_pct:35.50,
     output_gwh:28400,flh:3498}]}};
geoPanel({geo:{targets:GEOT, hardware:GEOH}});
const gt = DOM.geoTargets.innerHTML, gtn = DOM.geoTargetsNote.textContent;
const gh = DOM.geoHardware.innerHTML, ghn = DOM.geoHardwareNote.textContent;
const gcv = DOM.geoCalib.innerHTML, gcn = DOM.geoCalibNote.textContent;
const gm = DOM.geoMethod.innerHTML;
ok(!/NaN|undefined/.test(gt+gh+gcv+gm), "no NaN in the geothermal panel");
// THE FINDING: no target exists, and the panel leads with it
ok(/geothermal deployment targets set in/.test(gt),
   "the zero-targets finding is a headline figure, not a footnote");
ok(/No jurisdiction on this island has set a geothermal deployment target/
     .test(gtn), "and the note states it in full");
// TARGETS ARE JURISDICTIONAL, so there is no all-island view: each
// side is measured against what its own government committed to, and
// the two are never averaged.
ok(!/data-geojur="all"/.test(html),
   "no all-island option on this panel");
ok(/1\.9/.test(gt) && /district heating target/.test(gt),
   "the Republic's fifth is set against its district heating target");
ok(/no ground-source share is reserved/.test(gt),
   "and what that target does not reserve");
// THE SECOND FINDING: the Irish bar is not empty, the gap is internal
// THE TOGGLE CARRIES THE CONTRAST, so the copy must not assert it.
// Spelling it out reads as an argument made at the reader; switching
// between the two makes the same point and lets them find it.
ok(!/empty bar Britain|fold gap inside one island/.test(ghn),
   "the copy no longer spells the ROI/NI contrast out - the toggle "
   + "carries it");
const hsvg = svgAt(gh, 0);
ok(gridlinesSpread(hsvg, 3), "the hardware chart's gridlines spread");
ok(axisLabelReadable(hsvg), "its axis label is legible");
ok(/wiHatch/.test(hsvg), "the what-if is hatched, not solid");
ok((hsvg.match(/<rect [^>]*fill="#5A6B64"/g)||[]).length === 3,
   "three comparator fleets drawn");
// calibration
const csv2 = svgAt(gcv, 0);
ok(gridlinesSpread(csv2, 3), "the calibration chart's gridlines spread");
// REPORTED OUTPUT, no load-hour convention. The 2,000-hour figure
// this replaced was wrong for every country and wrong in opposite
// directions - overstating Ireland by 54% and understating Sweden by
// 43%, drawing the gap between them 2.7 times narrower than it is.
ok(/35\.50%|35\.5%/.test(csv2) && /0\.95%/.test(csv2),
   "each fleet's share of its own national heat is labelled");
ok(/reported output, not/.test(csv2),
   "and the chart says reported output, not an assumed load factor");
ok(/Sweden already serves well over it/.test(csv2),
   "Sweden is above the what-if line, not level with it");
ok(/stroke-dasharray/.test(csv2) && /the 20% what-if/.test(csv2),
   "with the what-if drawn as a rule across it");
ok(/unremarkable somewhere that started/.test(gcn),
   "and the scale argument stated");
// THE RUNNING HOURS EXPLAIN PART OF THE GAP, and belong at the chart
// where the gap is visible rather than in the method fold - a reader
// looking at a short bar asks why, not how it was computed.
ok(/1,301 full-load hours a year/.test(gcn)
   && /European average of 2,420/.test(gcn),
   "the calibration note explains the gap with the running hours");
ok(/short heating season/.test(gcn),
   "and why Irish systems run so few of them");
ok(/no load-factor assumption anywhere in it/.test(gcn),
   "while stating the calibration itself assumes none");
ok(/Load hours are reported, not assumed/.test(gm)
   && /Netherlands at 1,095 to Sweden at 3,498/.test(gm),
   "the fold gives the spread that makes one convention untenable");
ok(/Country Update Summary/.test(gm), "with the table it comes from");
ok(/currently circulating for comment/.test(gm),
   "the register is described as circulating, not published");
// AND NO ENTRY IS REPRODUCED. The register is Causeway's own and out
// for review among NI practitioners; the site reports totals derived
// from it and cites it as a source, but must not publish the sites
// until that review closes.
{
  const sites = ["Riddel Hall", "Lisnafin", "Randalstown", "McClay",
                 "Girdwood", "Lyric Theatre", "Jordanstown",
                 "Greenmount", "Giant\u2019s Causeway",
                 "Giant's Causeway"];
  const leaked = sites.filter(s => html.indexOf(s) >= 0);
  ok(leaked.length === 0,
     "no register entry is named on the page"
     + (leaked.length ? " - leaked: " + leaked.join(", ") : ""));
}
// method
ok(/Comparator capacities are the UK sibling/.test(gm),
   "the method credits the shared comparator constants");
ok(/weakest figure here/.test(gm) && /never commissioned/.test(gm),
   "and admits the NI register's weakness, failures included");
// EVERY SOURCE CREDITED BY NAME. The fold previously said "a
// site-by-site register" as though it had appeared from nowhere, and
// never credited the Republic's country update at all.
ok(/WGC2026 Country Update/.test(gm),
   "the Republic's country update is credited");
ok(/Causeway Energies register/.test(gm) && /above 45 kW/.test(gm),
   "the NI register is credited to Causeway with its threshold");
ok(/44 and 18 kW/.test(gm),
   "and the exclusions that fix that threshold are given");
ok(/MCS certification records/.test(gm),
   "MCS is credited for the domestic estimate");
// THE TOGGLE MUST MOVE THE FIGURES, not just the wording. Asserting
// that the note mentions a toggle proves nothing about whether
// switching does anything - the same failure as testing that a label
// exists rather than where it sits.
function geoAt(j){
  setPageVar("GEOJUR", j);
  ["geoHardware","geoHardwareNote","geoCalib","geoCalibNote"]
    .forEach(k=>{DOM[k]=null; el(k);});
  geoPanel({geo:{targets:GEOT, hardware:GEOH}});
  return {hw:DOM.geoHardware.innerHTML, note:DOM.geoHardwareNote.textContent,
          cal:DOM.geoCalib.innerHTML};
}
{
  const R = geoAt("roi"), N = geoAt("ni");
  ok(R.hw !== N.hw,
     "each jurisdiction renders a different hardware panel");
  ok(/17x what is installed/.test(R.hw)
     && /372x what is installed/.test(N.hw),
     "the what-if multiple changes with the toggle - 17x against 372x");
  ok(/0\.95%/.test(R.cal) && /0\.05%/.test(N.cal),
     "and each jurisdiction's share of its own heat is drawn");
  ok(/Republic of Ireland/.test(R.cal) && /Northern Ireland/.test(N.cal),
     "with the home bar relabelled");
  ok(/Sweden/.test(R.cal) && /Sweden/.test(N.cal),
     "while the comparators stay put");
  // THE DELIVERY RECORD IS THE FINDING, not just the small number:
  // two of ten schemes run cleanly, four failed outright, and a
  // seventh of installed heating never reached a building.
  ok(/10 documented schemes above 45 kW/.test(N.note)
     && /only 2 run cleanly/.test(N.note),
     "the NI view gives the register's delivery record");
  ok(/532 kW of heating built, 460 kW is delivered/.test(N.note),
     "including the gap between built and delivered");
  ok(/never reached a building/.test(N.note),
     "and says what that gap means");
  setPageVar("GEOJUR", "roi");
}
["geoTargets","geoHardware","geoCalib"].forEach(k=>{DOM[k]=null; el(k);});
geoPanel({});
ok(/coming build/.test(DOM.geoTargets.textContent)
   && /coming build/.test(DOM.geoHardware.textContent),
   "and every sub-panel declines cleanly without its block");

// ---- no renderer may reach for an element that does not exist ------
// Removing a panel leaves its renderer behind, and in the browser el()
// returns NULL for a missing id - so the first .textContent on one
// throws and kills EVERY renderer after it in the boot sequence. That
// is what emptied Panel 5: heatGap and coolSide were still being
// called for markup deleted two versions earlier, and geoPanel never
// ran. Nothing in either suite could see it, because the harness's
// el() manufactures a stub instead of returning null.
{
  const markup = html.replace(/<script[\s\S]*?<\/script>/g, "");
  const have = new Set([...markup.matchAll(/id="([A-Za-z0-9_-]+)"/g)]
    .map(m => m[1]));
  const want = [...SCRIPTS.join("\n")
    .matchAll(/\bel\(\s*['"]([A-Za-z0-9_-]+)['"]\s*\)/g)]
    .map(m => m[1]);
  // an id is allowed to be absent only where the call site guards it
  // Two guard idioms are in use and BOTH count. The first is
  //   const h1 = el('h1Win'); if (h1) h1.textContent = ...
  // the second, used by every panel renderer, is
  //   const box = el("vfmStages"), note = el("vfmStagesNote");
  //   if (!box) return;
  // which protects every id destructured on that line, not just the
  // first. Panel 6 is covered on the public page, so its containers
  // are absent by design and the renderers return early - a false
  // positive here would have looked like the bug it is designed to
  // catch.
  const src = SCRIPTS.join("\n");
  const guarded = new Set([...src
    .matchAll(/(?:const|let)\s+(\w+)\s*=\s*el\(\s*['"]([A-Za-z0-9_-]+)['"]\s*\)\s*;\s*if\s*\(\s*\1\s*\)/g)]
    .map(m => m[2]));
  [...src.matchAll(
    /(?:const|let)\s+(\w+)\s*=\s*((?:el\(\s*['"][A-Za-z0-9_-]+['"]\s*\)\s*,?\s*\w*\s*=?\s*)+);[\s\S]{0,120}?if\s*\(\s*!\1\s*\)\s*(?:return|\{)/g)]
    .forEach(m => {
      [...m[2].matchAll(/el\(\s*['"]([A-Za-z0-9_-]+)['"]\s*\)/g)]
        .forEach(x => guarded.add(x[1]));
    });
  const missing = [...new Set(want)]
    .filter(id => !have.has(id) && !guarded.has(id));
  ok(missing.length === 0,
     "every el() the script calls resolves to markup that exists"
     + (missing.length ? " - missing: " + missing.join(", ") : ""));
}

// ---- Panel 6: value for money -------------------------------------
["vfmStages","vfmStagesNote","vfmStreams","vfmStreamsNote","vfmTes",
 "vfmTesNote","vfmMethod"].forEach(k=>{DOM[k]=null; el(k);});
const VFMFIX = {derived:{vfm:{
  scenario:{load_hours:4000,
    scenario:{roi_twh:5.0, roi_year:2036, roi_milestone_twh:2.7,
              roi_milestone_year:2030},
    jur:{
    roi:{network_twh:5.0, network_pct_of_heat:19.7, plant_mw:1250,
         basis:"ten-year build", committed:true,
         milestone_twh:2.7, milestone_year:2030},
    ni:{network_twh:2.15, network_pct_of_heat:19.7, plant_mw:538,
        basis:"lent", committed:false,
        milestone_twh:1.16, milestone_year:2030}}},
  stages:{jur:{
    roi:{spf:4.0, spf_counterfactual:2.8, spf_gain:1.43, source_c:16.0,
         deep_weight:0.0, devex_social_pct:0.040,
         shortfall_default:0.10, shortfall_range:[0.0,0.30]},
    ni:{spf:5.0, spf_counterfactual:2.8, spf_gain:1.79, source_c:19.6,
        deep_weight:0.40, devex_social_pct:0.074,
        shortfall_default:0.15, shortfall_range:[0.0,0.45]}}},
  increment:{air_source_eur_kw:881, jur:{
    roi:{central:{increment_eur_kw:119}},
    ni:{central:{increment_eur_kw:330}}}},
  carbon:{jur:{roi:{elec_saved_twh:0.289}, ni:{elec_saved_twh:0.182}}},
  running:{jur:{
    roi:{resource_eur_m_yr:{low:31.1,central:42.4,high:48.4}},
    ni:{resource_eur_m_yr:{low:19.6,central:26.7,high:30.5}}}},
  constants:{capacity_applies_to:["ashp"]},
  phased:{build_years:10, horizon_years:60,
    optimism:{default_pct:50.0, applies_to:"capital only",
              benefits_adjustment:null},
    integrated:["running cost at LRVC","avoided generation capacity",
                "carbon at the shadow price",
                "cooling, operating and avoided chiller capital",
                "subsurface increment","development capital",
                "optimism bias on capital",
                "subsurface shortfall on the benefit side"],
    not_integrated:{stage2_benefits:[
        "avoided network reinforcement","air quality",
        "interseasonal storage","dispatch-down absorption",
        "security of supply","residual value at 60 years"],
      stage2_costs:["operating and maintenance"],
      stage1:["NOTHING IS BUILT"]},
    known_shortcuts:["avoided capacity is hard-coded",
      "the shortfall is applied flat, not through a duration curve",
      "the avoided chiller capital is NOT scaled by the shortfall",
      "the LRVC is borrowed from the UK sibling",
      "the ten-year build has no Irish basis",
      "optimism applies to capital only"],
    jur:{roi:{plant_mw:1250, increment_eur_kw:997,
              avoided_peak_mw:227, capacity_eur_m_yr:25.7,
              running_eur_m_yr:78.6, annual_benefit_eur_m:104.3,
              carbon_pv_eur_m:94,
              streams_pv_eur_m:{running:1471, capacity:481, carbon:94,
                                cooling:34},
              cooling_avoided_eur_m:7.1, cooling_running_eur_m_yr:1.8,
              capex_pv_eur_m:1608, benefit_pv_eur_m:2046, bcr:1.27},
         ni:{plant_mw:538, increment_eur_kw:857,
             avoided_peak_mw:125, capacity_eur_m_yr:14.1,
             running_eur_m_yr:49.6, annual_benefit_eur_m:63.7,
             carbon_pv_eur_m:53,
             streams_pv_eur_m:{running:1061, capacity:302, carbon:53,
                               cooling:9},
             cooling_avoided_eur_m:1.8, cooling_running_eur_m_yr:0.5,
             capex_pv_eur_m:628, benefit_pv_eur_m:1416, bcr:2.25}}},
  tes_cop:{air_source:2.6, ground_source:2.94,
    table:"TES 2023 databook, IE Demand, Table 6.4",
    seasonal_treatment:null, peak_treatment:null},
  tes_carbon:{}, lrvc:{}}}};
vfmPanel(VFMFIX);
const vs = DOM.vfmStages.innerHTML, vsn = DOM.vfmStagesNote.textContent;
const vr = DOM.vfmStreams.innerHTML, vrn = DOM.vfmStreamsNote.textContent;
const vt = DOM.vfmTes.innerHTML, vtn = DOM.vfmTesNote.textContent;
const vm = DOM.vfmMethod.innerHTML;
ok(!/NaN|undefined/.test(vs+vr+vt+vm), "no NaN in the appraisal panel");
// THE STAGES ARE NEVER SUMMED, and the capacity sign follows the stage
ok(/a COST/.test(vs) && /a BENEFIT/.test(vs),
   "capacity is a cost in stage one and a benefit in stage two");
ok(/geothermal upgrade to the national/.test(vsn),
   "and the note frames stage 2 as the geothermal upgrade");
ok(/single-home ground source heat pumps/.test(vsn),
   "spanning single homes to city networks");
// THE SCENARIO IS OURS; ONLY THE MILESTONE IS GOVERNMENT'S. When the
// panel moved from the 2030 milestone to the ten-year build, two
// labels went stale and left it saying "5 TWh by 2030 - a government
// commitment". Neither the year nor the attribution was true. The
// Republic has committed to 2.7 TWh by 2030; 5.0 TWh by 2036 is our
// extrapolation from it.
ok(/our ten-year build/.test(vs),
   "the scenario is declared as ours, not a commitment");
ok(/extrapolated from a 2\.7 TWh commitment by 2030/.test(vs),
   "with the actual commitment named and dated");
ok(!/2\.7 TWh[^<]{0,40}by 2030[^<]{0,40}\u2014 a government commitment/
     .test(vs), "and no bare commitment claim on the scenario figure");
ok(/networks by 2036/.test(vs),
   "the ten-year build carries its own date, not the milestone's");
// (the price-exposure sentence was removed from the note by edit,
// 23 Aug 2026 - the geothermal-upgrade pins above police its successor)
// carbon must NOT be shown as a durable stream
ok(/extinguishes by about 2035/.test(vr),
   "carbon is shown extinguishing, not as a durable benefit");
// THE BENEFITS BAR. Proportions of present value, with cost drawn
// beside it at the same scale so the BCR is visible rather than only
// readable.
ok(/class="mixbar"/.test(vr) && (vr.match(/class="seg"/g)||[]).length >= 5,
   "a benefits bar is drawn with four streams and a cost bar");
ok(/improves BOTH sides at once/.test(vr),
   "and cooling is declared as improving both sides");
ok(/BENEFIT \u2014 present value|BENEFIT — present value/.test(vr),
   "the benefit bar is labelled");
ok(/COST \u2014 subsurface increment|COST — subsurface/.test(vr),
   "and the cost bar beside it");
{
  // running must dominate, carbon must be the smallest - if that ever
  // inverts, something has gone wrong upstream
  const w = [...vr.matchAll(/class="seg" style="width:([\d.]+)%;background:(#[0-9A-Fa-f]{6})/g)]
    .map(m => ({pct:parseFloat(m[1]), col:m[2]}));
  const run = w.find(x=>x.col==="#3AAA35"), carb = w.find(x=>x.col==="#C98F4F");
  ok(run && carb && run.pct > 50 && carb.pct < 15,
     "running cost dominates the benefit and carbon is the smallest");
}
ok(/does not decay/.test(vr), "while capacity is marked as durable");
// It IS a BCR now - capital phased over a ten-year build, benefits
// ramping with the fleet, discounted on each jurisdiction's own rule.
// The earlier assertion guarded against calling an undiscounted
// payback a BCR; that guard is replaced rather than removed, because
// the substance changed.
ok(/benefit-cost ratio over/.test(vr),
   "a properly discounted BCR is shown");
ok(/optimism bias/.test(vr), "with the optimism bias declared on it");
ok(/five value streams of about twenty-five/i.test(vr),
   "and how little of the appraisal is actually in it");
// the TES finding
ok(/none<\/b>/.test(vt) && /flat COP/.test(vt),
   "the operators' flat COP is shown with no seasonal treatment");
ok(/HIGHER than theirs/.test(vtn),
   "and our own air-source figure is declared higher than theirs");
ok(/underestimates the problem and the solution/.test(vtn),
   "with the omission cutting both ways");
// the method fold must admit what is missing
// THE AUDIT MUST BE ON THE PAGE, not just in the payload. Eight terms
// of about twenty-five are in the arithmetic. The shortfall lever is
// now APPLIED, so this assertion is INVERTED from the version that
// policed its absence - the page can never quietly drop it again.
ok(/What is in the arithmetic, and what is not/.test(vm),
   "the fold audits what is in and what is out");
ok(/subsurface shortfall on the benefit side/.test(vm),
   "the shortfall is named as applied, not as an omission");
ok(!/SUBSURFACE SHORTFALL - defined, never applied/.test(vm),
   "and the old unapplied wording is gone from the page");
ok(/NOTHING IS BUILT/.test(vm),
   "and that the electrification stage does not exist");
ok(/Known shortcuts/.test(vm) && /hard-coded/.test(vm),
   "with the shortcuts listed, including the hard-coded capacity");
ok(/borrowed from the UK sibling/i.test(vm),
   "including that the LRVC is borrowed");
ok(/against interest/.test(vm), "and the interest declaration");
// the toggle must move the figures
{
  setPageVar("VFMJUR","ni");
  ["vfmStages","vfmStreams","vfmTes"].forEach(k=>{DOM[k]=null; el(k);});
  vfmPanel(VFMFIX);
  const ni = DOM.vfmStages.innerHTML;
  ok(/LENT/.test(ni), "the North's scenario is declared lent");
  ok(ni !== vs, "and the toggle changes the figures");
  setPageVar("VFMJUR","roi");
}
["vfmStages","vfmStreams","vfmTes"].forEach(k=>{DOM[k]=null; el(k);});
vfmPanel({});
ok(/coming build/.test(DOM.vfmStages.textContent),
   "and it declines cleanly without the block");
// THE PANEL IS LIVE ON THE PUBLIC PAGE, UNDER A LABEL - uncovered
// 23 Aug 2026 by decision. These assertions are the INVERSE of the
// cover checks that stood while the appraisal was half finished: the
// label must say the work is unfinished, the containers must exist
// for the renderer, and the daily payload must be exposed for the
// lever widget. If the label ever comes off, that must be a decision
// that edits this test, not an accident.
{
  const sec = html.slice(html.indexOf('<section id="vfm"'),
                         html.indexOf('<section id="why"'));
  ok(/wipcover/.test(sec), "Panel 6 carries the under-construction label");
  ok(/working appraisal/i.test(sec), "and calls itself a working appraisal");
  ok(/id="vfmStages"/.test(sec) && /id="vfmStreams"/.test(sec)
     && /id="vfmTes"/.test(sec) && /id="vfmMethod"/.test(sec),
     "its containers are present, so the renderer runs");
  ok(/data-vfmjur="roi"/.test(sec) && /data-vfmjur="ni"/.test(sec),
     "with both jurisdiction toggles");
  ok(/window\.VFM_PAYLOAD = D;/.test(html),
     "and the daily payload is exposed for the lever widget");
  ok(html.indexOf("<!-- panel6-widget -->") !== -1,
     "which is injected by the generator, not by hand");
}

// THE WIDGET MOUNTS. The lever widget crashed on its own init for two
// days while every arithmetic test passed: the corner tests exercised
// the evaluator, and this harness skips non-page script blocks, so the
// widget's boot path ran NOWHERE until a real-DOM check caught two
// slider ids writing into state keys that did not exist. This mini-DOM
// executes the SHIPPED tools files against the real standalone payload
// and asserts the widget builds, renders a readout, and toggles to
// sterling for the North. If the widget cannot boot, this fails.
{
  const path = require("path");
  const p6 = fs.readFileSync(
    path.join(__dirname, "..", "docs", "panel6.html"), "utf8");
  const pm = p6.match(/<script>window\.VFM_PAYLOAD = (\{[\s\S]*?\});<\/script>/);
  ok(!!pm, "widget-mount: standalone payload found");
  const payload = JSON.parse(pm[1]);

  function elem(tag){
    return {tag, children:[], style:{}, dataset:{}, listeners:{},
      type:null, id:null, _text:"", _html:"",
      appendChild(c){this.children.push(c); return c;},
      addEventListener(t,f){(this.listeners[t]=this.listeners[t]||[]).push(f);},
      setAttribute(){},
      set innerHTML(v){this._html=v; this._text=v.replace(/<[^>]+>/g," ");
                       this.children=[];},
      get innerHTML(){return this._html;},
      set textContent(v){this._text=v; this.children=[];},
      get textContent(){
        let t=this._text||"";
        this.children.forEach(c=>{t+=c.textContent;});
        return t;},
      all(){const o=[this];
        this.children.forEach(c=>{if(c.all)o.push(...c.all());});
        return o;},
    };
  }
  const host = elem("section"); host.id="vfm";
  // the widget prefers the slot beside the streams bars; the harness
  // offers both so the test proves WHICH one it chooses
  const levers = elem("div"); levers.id="vfmLevers";
  // THE PANEL OWNS THE ONLY JURISDICTION TOGGLE. The widget used to
  // carry a second one; it now follows these, so the harness must
  // supply them and the test asserts the widget tracks a click.
  const jurBtns = ["roi","ni"].map(j=>{
    const b = elem("button"); b.dataset = {vfmjur:j};
    b._pressed = j==="roi";
    b.getAttribute = a => a==="aria-pressed" ? String(b._pressed) : null;
    return b;
  });
  const savedW = global.window, savedD = global.document;
  global.document = {
    getElementById: id => id==="vfmLevers" ? levers
                       : (id==="vfm" ? host : null),
    querySelectorAll: sel => /data-vfmjur/.test(sel) ? jurBtns : [],
    createElement: t => elem(t),
    createTextNode: t => ({textContent:t, children:[]}),
    body: elem("body"),
  };
  global.window = {VFM_PAYLOAD: payload};
  try {
    const src =
      fs.readFileSync(path.join(__dirname,"..","tools","vfm_levers.js"),"utf8")
      + "\n"
      + fs.readFileSync(path.join(__dirname,"..","tools","panel6_widget.js"),"utf8");
    (0, eval)(src);
    const box = levers.children.find(c=>c.id==="vfm-lever-widget");
    ok(!!box, "widget-mount: the widget boots and mounts beside the bars");
    ok(!host.children.some(c=>c.id==="vfm-lever-widget"),
       "widget-mount: not at the section end, where it was before");
    const nodes = box ? box.all() : [];
    const ranges = nodes.filter(n=>n.tag==="input" && n.type==="range");
    ok(ranges.length===7,
       "widget-mount: four headline sliders plus three in the fold");
    ok(/benefit\u2013cost ratio/.test(box.textContent),
       "widget-mount: a live headline ratio renders");
    ok(/net present social value/.test(box.textContent),
       "widget-mount: with its net present value and cost");
    // THE BAR MOVES WITH THE NUMBER. The point of the layout: a
    // reader pushes a lever and sees the streams it is made of change,
    // not just the ratio. Segment widths are exact under the levers
    // because every benefit stream scales with (1 - shortfall).
    const barOf = b => (b.all().filter(n=>n.tag==="div"
                        && /width:/.test(n.style.cssText||"")));
    ok(barOf(box).length >= 4,
       "widget-mount: the stream bar renders its segments");
    ok(/Benefits/.test(box.textContent) && /Costs/.test(box.textContent),
       "widget-mount: both bars are labelled");
    // THE COST BAR IS DECOMPOSED FROM THE SAME COEFFICIENTS the
    // evaluator uses, so its segments sum to the headline cost. If a
    // future lever changes the capital algebra without changing the
    // decomposition, the two drift and this catches it.
    ok(/Subsurface increment/.test(box.textContent)
       && /Development risk/.test(box.textContent)
       && /Optimism bias/.test(box.textContent),
       "widget-mount: capital is split into its three parts");
    ok(/stops passing at a programme shortfall/.test(box.textContent),
       "widget-mount: the break-even sentence renders");
    ok(!nodes.some(n=>n.tag==="button"
                    && /^(NI|ROI)$/.test((n.textContent||"").trim())),
       "widget-mount: the widget carries no toggle of its own");
    const niBtn = jurBtns[1];
    (niBtn.listeners.click||[]).forEach(f=>f());
    ok(/NI benefit\u2013cost ratio/.test(box.textContent)
       && /\u00a3/.test(box.textContent),
       "widget-mount: NI renders, in sterling");
    ok(/Constrained wind/.test(box.textContent),
       "widget-mount: and NI's bar carries the constrained-wind stream");
  } finally {
    global.window = savedW; global.document = savedD;
  }
}

console.log(checks + " front-end fixture checks passed");
