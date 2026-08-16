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
  fmt: fmt, MONTHS3: MONTHS3, NICE: NICE, niceTicks: niceTicks,
  hourLabel: hourLabel, monthLabel: monthLabel,
};`;
SCRIPTS.forEach((src, i) => {
  try {
    (0, eval)(src + SHIM);
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
ok(order.indexOf("grid") === 2,
   "Panel 3 sits third, where the oil ticker used to be");
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

console.log(checks + " front-end fixture checks passed");
