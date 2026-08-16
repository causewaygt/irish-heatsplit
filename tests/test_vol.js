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

// Lift the pieces under test out of the page.
function lift(re, what){
  const m = html.match(re);
  if(!m) throw new Error("could not find " + what + " in index.html");
  return m[0];
}
const partsSrc = lift(/const VOL_PARTS = \[[\s\S]*?\];/, "VOL_PARTS");
const monthsSrc = lift(/const MONTHS3 = \[[\s\S]*?\];/, "MONTHS3");
const mlabSrc = lift(/function monthLabel\(ym\)\{[\s\S]*?\n\}/, "monthLabel");
const drawSrc = lift(/function drawVol\(rows, state, geom\)\{[\s\S]*?\n\}/,
                     "drawVol");
const expandSrc = lift(/function expandHistory\(h\)\{[\s\S]*?\n  \}/,
                       "expandHistory");
eval(partsSrc + "\n" + monthsSrc + "\n" + mlabSrc + "\n"
     + drawSrc + "\n" + expandSrc);

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
const maps = {};
for (const name of ["SUMN", "WLBL", "WNAME", "WSPAN"]){
  const src = lift(new RegExp("const " + name + "=\\{[\\s\\S]*?\\};"), name);
  maps[name] = eval("(" + src.replace(/^const \w+=/, "")
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
const calSrc = lift(/const CAL_ROUTES = \[[\s\S]*?\];/, "CAL_ROUTES");
const calFn = lift(/function calBoard\(cal\)\{[\s\S]*?\n\}/, "calBoard");
function fmt(v, dp){ return Number(v).toFixed(dp); }
eval(calSrc + "\n" + calFn);
DOM.calBoard = null; el("calBoard");
calBoard({gate: 1.15, spread: 1.076, jurisdictions: {
  roi: {ashp:{eta:0.3175,spf_anchor:2.80,source_c:null},
        gshp:{eta:0.3342,spf_anchor:3.24,source_c:8.0},
        network:{eta:0.3106,spf_anchor:4.0,source_c:16.0}}}});
const cb = DOM.calBoard.innerHTML;
ok(/0\.3175/.test(cb) && /0\.3342/.test(cb) && /0\.3106/.test(cb),
   "calibration board prints every route's fraction");
ok(/2\.80/.test(cb) && /3\.24/.test(cb),
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
const emitSrc = lift(/const EMIT_GREEN = [\s\S]*?\);/, "EMIT_GREEN");
const emitFn = lift(/function emitPanel\(he\)\{[\s\S]*?\n\}/, "emitPanel");
eval(emitSrc + "\n" + emitFn);
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
const grSrc = lift(/const GROUTES = \[[\s\S]*?\];/, "GROUTES");
const hourSrc = lift(/function hourLabel\(t\)\{[\s\S]*?\n\}/, "hourLabel");
const niceArr = lift(/const NICE = \[[\s\S]*?\];/, "NICE");
const niceSrc = lift(/function niceTicks\(max, want\)\{[\s\S]*?\n\}/,
                     "niceTicks");
const grFn = lift(/function gridPanel\(th\)\{[\s\S]*?\n\}/, "gridPanel");
function esc(s){ return String(s); }
let GJUR = "all";
eval(monthsSrc + "\n" + niceArr + "\n" + hourSrc + "\n" + niceSrc + "\n" + grSrc
     + "\n" + grFn);
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
ok(/1\.0 GW OVER the ceiling/.test(gp),
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
ok(/asked the other way round/.test(gp),
   "the note distinguishes the solved share from the fixed fifth above");
ok((gp.match(/<svg /g)||[]).length === 2,
   "two charts in the panel, one per sub-panel");
ok(/actual use/.test(gp) && /20% what-if/.test(gp),
   "the legend names the grey base and the coloured increment");
ok(/GW at the binding hour/.test(gp), "the y-axis is labelled");
ok(/tightest hour of the year/i.test(gp),
   "and the sub-panel carries the UK sibling's title");
ok(/1\.32x its power system/.test(gp),
   "the heat-system-against-power-system ratio is on the page");
ok(/peak-capacity test, not an energy test/.test(gp),
   "and the framing that must travel with it");
// the jurisdiction states must not show island figures under an NI label
GJUR = "ni"; DOM.gridPanel = null; el("gridPanel");
gridPanel(TH);
ok(/not built yet/.test(DOM.gridPanel.innerHTML)
   && !/GW/.test(DOM.gridPanel.innerHTML),
   "NI and ROI decline rather than relabelling the island figures");
GJUR = "all"; DOM.gridPanel = null; el("gridPanel");
gridPanel(null);
ok(/coming build/.test(DOM.gridPanel.innerHTML),
   "and a payload without the block declines cleanly");

// ---- Panel 3's three views -----------------------------------------
const gvSer = lift(/const GV_SERIES = \[[\s\S]*?\];/, "GV_SERIES");
const gvLab = lift(/function gvLabel\(t\)\{[\s\S]*?\n\}/, "gvLabel");
const gvFn = lift(/function drawGridViews\(gv\)\{[\s\S]*?\n\}/,
                  "drawGridViews");
let GVIEW = "hourly";
eval(gvSer + "\n" + gvLab + "\n" + gvFn);
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
GVIEW = "monthly";
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
GVIEW = "daily";
["gridChart","gridViewNote"].forEach(k=>{DOM[k]=null; el(k);});
drawGridViews(GV);
ok(/90 points/.test(DOM.gridViewNote.textContent),
   "and each view reports its own point count and span");
GVIEW = "hourly";
["gridChart","gridLegend"].forEach(k=>{DOM[k]=null; el(k);});
drawGridViews(null);
ok(/next daily build/.test(DOM.gridChart.textContent),
   "a payload without the series declines rather than drawing empty axes");

console.log(checks + " front-end fixture checks passed");
