# Irish Heat Split

**How the island of Ireland heats itself, weekly – and how much of that heat
no one can see.**

Live site: https://causewaygt.github.io/irish-heatsplit/
Sibling of the [UK Heat Split](https://causewaygt.github.io/uk-heatsplit/).
Built and maintained by [Causeway Energies](https://causewaygt.com)
(Causeway Geothermal NI Ltd). Pipeline 5.6.0 / site 5.3.0.

## The premise

The island of Ireland is the most oil-heated corner of Western Europe.
Oil has no meter, no grid and no daily statistics – the majority of the
island's heat is invisible to the systems that watch everything else.
This tracker makes the visible parts visible daily, carries the invisible
majority as clearly-labelled annual anchors shaped by each week's weather,
and prices the alternative. The data gap is the story.

## What the site shows

- **Masthead** – the heat spark gap, live: oil-boiler heat versus
  geothermal on a useful-heat basis, priced in each jurisdiction's own
  currency, with the winning margin computed fresh from the day's feeds.
- **The back look** – a weekly history of the hero's combined figures
  and their what-if twins: complete calendar weeks priced at their own
  week's oil prices, ECB rate, tariff period and grid carbon intensity,
  frozen after the two most recent, capped at 60. A 1w/4w/12w/12m
  selector re-totals the headline four (auto-scaled to TWh/€bn/Mt, the
  indigenous share purchased-weighted) with sparklines – actual solid,
  what-if green, the gap between them shaded – and a delta versus the
  window start. Bills are sector-blended†: services gas and
  electricity, and all cooling, price at non-domestic rates; oil prices
  identically across sectors. The record reaches back to 6 August 2025. Weeks from 1 October 2025
  were observed as they happened; the eight before it are
  **reconstructed** from published regulated tariffs and the hourly
  carbon store, and are counted separately – weeks on record and weeks
  live are two numbers, and the 52-live-weeks milestone is the second
  one. NI oil before the daily survey began
  (2026-02-26) is bridged from the EU bulletin's ex-tax series plus an
  overlap-calibrated margin†, each bridged week tagged with its source.
  Twelve live months complete in October 2026.
- **Hero** – the week's heating *and cooling*: combined energy
  purchased (with the heat/cooling split), indigenous share, the bill
  and emissions in both currencies, toggled all-island / NI / ROI, each
  jurisdiction shaped by its own degree days with weekly cooling from
  the cold-economy census (comfort following the live overheating
  record); a what-if strip – 20% of heat & cooling moved to geothermal,
  the cooling side at a 70%† ground-coupled electricity saving; a
  for-scale line against last winter's peak; and energy-in versus
  useful-heat-&-cooling-out bars with losses hatched – delivered cooling
  applies per-load service factors† (vapour-compression plant delivers a
  multiple of its electricity), so served can legitimately exceed
  purchased, and the indigenous share is computed on the delivered
  basis with the ambient balance counted indigenous. In July the
  island's cooling bill outweighs its heat bill roughly 3:1 – the
  summer inversion the tracker displays rather than omits.
- **What heat costs to make** – five routes priced weekly per useful
  kWh, retail or ex-tax, sitting under the energy bars. It replaced the
  invisible-majority bar: the point that most of the island's heat is
  unmetered is now made where it belongs, in the method fold on the
  panel that depends on it.
- **The oil ticker** – NI kerosene daily (Consumer Council survey), ROI
  weekly (EU Oil Bulletin, backfilled from the Commission's price-history
  workbook), both per litre on FX-locked twin axes; dashed pre-tax lines
  either side making the tax wedge visible; policy events as chart
  markers; a same-tax GB comparison line that draws whenever its feed
  reports. Same fuel, two price regimes, one island.
- **The gas engine room** – daily ROI gas demand against degree days;
  the within-month temperature-sensitive slope is space heat,
  displayed with its residual standard error and an annual
  calibration disclosure against the SEAI anchor.
- **The heat gap** – cost of one useful kWh by route (oil boiler, gas
  boiler, air-source heat pump, geothermal), toggled by jurisdiction,
  with the break-even SPF against the incumbent oil boiler as the
  headline stat. The air-source SPF is modelled from each jurisdiction's
  own climate, not the brochure.
- **The cold economy** – a census of the island's cooling loads: data
  centres, the food-export cold chain, process cooling, comfort cooling
  and NI, 6.25 TWh† of electricity rejecting ≈19 TWh† of heat a year –
  refrigeration rejects more heat than the electricity it draws. The
  electricity figure fell from ≈12 TWh on 6 August 2026 when the
  data-centre line was repriced to its cooling share; the heat
  rejected did not move, because the physical output was never in
  question – only the share of the draw that counts as cooling. Flat
  loads against the degree-day demand shape, comfort shaped by the live
  overheating-degree record once a season exists; the stranded share is
  the seasonal-storage (ATES) wedge.
- **Geothermal – the empty bar** – installed capacity in thermal
  megawatts: today's island stock stacked beneath what serving 20% of
  delivered heat would require, beside the installed reality of Sweden,
  the Netherlands and France including their deeper-geothermal layer.
  The NI >60 kW register – every system named, dated and statused –
  ships in data.json; ROI anchors from the WGC2026 country update; flow
  context from the EGEC Geothermal Market Report 2025.
- **Why heat?** – the whole-economy zoom-out: four charts of annual
  energy services, spend, imported energy and emissions across power,
  transport and heat. Heat rivals transport as the largest service,
  carries the smallest bill per unit delivered – and is therefore still
  fossil.
- **Method & sources** – every feed, its status and its flags.

## Architecture

Static site, no backend. A GitHub Action runs `scripts/build.py` daily at
04:17 UTC, fetching every feed with retries, merging history across runs,
and writing a single `docs/data.json` that `docs/index.html` renders
client-side with Plotly. GitHub Pages serves `/docs`.

### Feeds

| Feed | Source | Cadence | Notes |
|---|---|---|---|
| `hdd` | ERA5 via Open-Meteo | daily | population-weighted heating degree days, island/ROI/NI; hourly overheating-degree-hours (base 26 °C) collected for the future comfort metric |
| `ecb_fx` | ECB reference rates | daily | EUR/GBP twin-currency lock |
| `ccni_oil` | Consumer Council NI price checker | daily (Mon–Fri) | 300/500/900 L; history merged across runs |
| `oil_bulletin` | EU Weekly Oil Bulletin + price-history workbook | weekly | Ireland heating gas oil, with & without taxes, backfilled from the 2005-onwards history |
| `gb_oil` | BoilerJuice / DESNZ | daily | SOFT feed – cache-busting + browser headers against a CDN observed serving archived 2021 pages to non-browser clients; a freshness gate rejects fossils |
| `gni_live` | Gas Networks Ireland gasconsumption API | daily | ~8-day windows, weekly anchors backfill |
| `gni_ckan` | GNI via data.gov.ie (CC BY 4.0) | quarterly | calibration series for the regression |
| `semopx` | SEMOpx day-ahead results | daily | dual-currency power price |
| `eirgrid` | Smart Grid Dashboard (/api/chart/) | daily | quarter-hour demand → daily GWh, island/NI/ROI; incomplete days excluded; carbon intensity live and stored hourly |
| `sem_mix` | third-party generation mix | daily | DIAGNOSTIC ONLY – reads ~33% indigenous against ~55% implied by grid carbon intensity; held at anchor and logging its two suspects (missing solar in the feed, an unverified cross-border sign convention) until they reconcile |
| `entsog_probe` | ENTSOG transparency platform | daily | SOFT – physical gas flows; the measurement behind the NI-exit finding below |
| `eirgrid_probe` | Smart Grid Dashboard (/api/chart/) | daily | SOFT, log-only discovery; retires once the wind/solar feeds are formalised |

Feed statuses: **ok** (fetched, current), **lagging** (fetched, source
publishes on a lag), **stale** (fetch failed, previous values retained).
`SOFT_FEEDS` fail quietly; `EXPECTED_DOWN` feeds are documented outages.
`FEED_FLAGS` carry value-level caveats distinct from fetch status and
render as ⚑ in the method table. `EVENTS` is a curated policy-event
register rendered as chart markers.

## Methodology

**The scaffold estimator.** Weekly figures are not measurements – no such
measurements exist for most of the island's heat. They are annual anchors
(SEAI, DfE/NISRA, Causeway estimates) shaped by each week's weather: hot
water is carried as a flat term (22.4% of annual input – SEAI's National
Heat Study residential split, applied to this site's sector mix†), and the space-heating
share follows the week's fraction of the trailing year's heating degree
days. Per-capita heat input sits at parity with the UK (6.2 vs 6.3
MWh/person, input basis). Each jurisdiction is shaped by its own HDD
series and the island is their reconciled sum, so the toggle views always
agree.

**Degree days.** ERA5 reanalysis via Open-Meteo for seven stations,
population-weighted, base 15.5 °C – the standard Met Éireann/SEAI base.

**The air-source SPF model.** The heat-gap panel refuses brochure SCOP
figures. The demand-weighted outdoor temperature falls out of the HDD
series itself (for heating days T = base − HDD, so the load-weighted
source temperature is base − Σh²/Σh over the trailing year); a
Carnot-fraction COP at 45 °C flow with a defrost derate and a hot-water
share, blended on an energy-weighted harmonic basis, gives a seasonal
performance factor per jurisdiction – calibrated to GB field-trial
medians, moving with the weather year. Geothermal's stable source
temperature is exactly why its SPF escapes this ceiling.

**The gas regression.** Space-heat sensitivity is estimated by
within-class (monthly) centring – daily demand deviations on daily HDD
deviations within each month – which removes seasonal confounds
(holidays, school terms, baseload drift) that bias the pooled slope.
Both slopes ship in the payload with the residual standard error; the
centred one is displayed, and a calibration disclosure publishes the
regression-implied annual space heat against the SEAI-derived anchor
with a 0.90–1.10 gate, whether or not it passes.

**The what-if.** 20% of delivered heat moves to heat pumps at seasonal
performance 4, and 20% of the cooling load moves to ground-coupled
systems at a 70%† electricity saving: heat-pump electricity is bought at
each jurisdiction's tariff and carries its grid-indigenous share, the
ambient remainder is free and indigenous by definition, avoided cooling
electricity is displaced by ambient rejection, and the displaced fuels
scale down pro-rata – purchased energy, bills, indigenous share and
emissions all recompute from one accounting.

**The cold economy.** Cooling loads are a census: data centres
(CSO-anchored) plus †-anchored cold-chain, process, comfort and NI
loads. Per-load rejection factors convert electricity to rejected heat
(vapour-compression loads reject compressor work plus the heat they
pump). Flat loads spread evenly; the comfort load follows the live
ODH₂₆ overheating record once a season of it exists. With annual totals
normalised, the stranded share is the part of supply produced while
heat demand runs below it – the seasonal-storage wedge, recomputed from
live records on every build.

**Geothermal capacity requirement.** 20% of annual delivered buildings
heat at 2,000 equivalent full-load hours, per jurisdiction and per
person – the arithmetic that converts the what-if strip into installed
thermal megawatts.

**Why heat?** Whole-economy anchors are annual and static: sourced where
a publication exists (SEAI Energy in Ireland 2025; the Causeway island
Sankey for the import split), with allocations kept deliberately round
and dagger-marked.

**Tariff basis.** Domestic rates include VAT (5% NI, 9% ROI);
non-domestic rates exclude it, because businesses recover input VAT.
That is Eurostat level 3 for households and level 2 for
non-households, and the UK sibling follows the same rule. NI gas and
electricity are effective all-in rates at the Utility Regulator's own
consumption basis, taken from published annual bills, with gas
weighted across SSE Airtricity (Greater Belfast and West, ~198,200
regulated customers) and Firmus Energy (Ten Towns, ~75,756) by
customer count. This replaced a single-supplier percentage chain with
the standing charge stripped out – Firmus alone was setting the NI gas
bill, and the two suppliers are not structurally comparable, since
SSE's domestic tariff is banded with no standing charge while Firmus
charges a unit rate plus one. ROI domestic is now the same KIND of quantity: the
Eurostat band price for semester 2 2025 – total revenue over volume,
so standing charges are included by construction – stepped by the
Electric Ireland announcements, which held from October 2022 to 1 July
2026. Both jurisdictions are therefore all-in effective rates at a
stated consumption, VAT and standing charges included, and the bills
are comparable at component level rather than only in total. The
residual difference is scope, not basis: NI is incumbent-weighted
regulated, ROI a market-wide average including discounts. Measured
against the same tables, NI's regulated electricity runs about 7%
above its own market band while its regulated gas runs about 18%
below, so the two do not bias in one direction. Non-domestic
rates for both jurisdictions come from the Utility Regulator's Retail
Energy Market Monitoring semester bands (S2 2024), which are derived
Eurostat-style as revenue over volume and therefore include standing
charges – so the services share IS like-for-like across the border.
They replace large-user prices: NI was carrying the GB manufacturing
average, which priced offices at industrial rates. Electricity is
consumption-weighted across the published bands, excluding only Large
and Very Large – seventeen NI connections and 683 GWh of heavy
industry and data centres. The ladder runs 28.5 p/kWh for very small
connections down to 16.9 for large and very large; the services-scoped
weighting lands at 23.5 p/kWh for NI and 23.8 for Ireland. Gas is band
I1 (under 278,000 kWh a year), where services buildings overwhelmingly
sit, rather than weighted – the REMM price bands do not map onto the
network bands the consumption split is published in, and NI I&C gas is
about two-thirds daily-metered heavy industry. **Non-domestic rates step by semester.** Three are published – S2
2024, S1 2025 and S2 2025 – and each week's services share is priced at
the semester it falls in, assigned by week ending, so a week straddling
30 June or 31 December lands wholly in the semester it ends in. The
semester is the resolution because there are no regulated non-domestic
announcements to give finer timing; domestic keeps dated steps because
the regulator and the incumbents publish them. Each Irish figure
converts at the ECB mean for its own semester, not the week's, because
that is the rate UREGNI used to sterling it. Weeks past the last
published semester hold at it – REMM lags about nine months. One consequence is visible on the site: because domestic rates
ARE stepped through to 2026 and NI gas fell about 15% over that span,
NI non-domestic gas now prints above NI domestic gas. That is a
vintage artefact rather than a claim about small business tariffs – at
a common vintage the ordering is right – and it is disclosed rather
than escalated away, because applying regulated domestic steps to
unregulated business contracts would compound one estimate with
another. It closes when REMM publishes newer semesters.

**Weeks that cannot be built say so.** A week the pipeline cannot
price is dropped, and a dropped week used to leave no trace – the
record simply came out shorter, which reads as a smaller number rather
than an error. Every decline now carries a reason, and the build logs
them grouped by cause with a count against the number attempted and the
span affected. A week outside the retention window is the only silent
decline, because that one is by design.

**The history block is written columnar.** Each key appears once
instead of once per week, with the ni/roi/fuels sub-blocks recursed
into – at 52 weeks the entries are wide and shallow, so the repeated
key strings outweigh the numbers they label, and the encoding takes the
block to about a third of its size. Wire format and content schema are
deliberately orthogonal: re-encoding is not a restatement and does not
trigger one. Both readers accept the columnar form and a plain list,
because `index.html` publishes the moment Pages deploys while
`data.json` only changes at the next 04:17 build, so for up to a day
each side is reading the other's previous shape.

**Irish anchors: credit-free, and converted at a fetched rate.** The
Irish domestic electricity series carries government credits as
negative taxes – €1,500 of them since 2022, the last €125 in
January/February 2025 – which is why Ireland reads 31.3 p/kWh in
semester 2 2024, 27.5 in semester 1 2025 and 35.2 in semester 2 2025.
That 28% jump is a credit ending, not a price moving. This site prices
the real cost of heat, so the credit-bearing semesters are unusable and
semester 2 2025, the first clean one, is the anchor – which is also the
semester the back-look starts in.

The Utility Regulator publishes Ireland in sterling, having converted
Eurostat's euro at the semester average, so recovering the euro figure
needs that same average. It scales every Irish anchor on the site, and
it is now computed from the ECB daily reference rates this pipeline
already retains rather than assumed – the full history back to 1999
comes down with the deep backfill, semesters with fewer than 110
observations are dropped rather than averaged thin, and the rate in use
is logged on every run. A documented fallback fires only if the mean
cannot be computed, and says so loudly.

**Provenance.** Sourced figures cite their publisher. Judgement figures
carry a dagger (†) and are current Causeway Energies estimates –
challenge and input welcome at contact@causewaygt.com. Data-quality
caveats distinct from fetch status render as ⚑ flags. Feeds are developed
diagnostics-first: on first contact with an unknown format the pipeline
logs the raw structure and continues, so parsers are written against
evidence from live run logs, never guessed.

The full estimation methodology is published as
[methodology.pdf](https://causewaygt.github.io/irish-heatsplit/methodology.pdf)
and linked from the site footer.

## The hourly store

`docs/hourly.json` holds a rolling 13 months of all-island demand,
wind, solar and carbon intensity at hourly resolution – EirGrid's
15-minute series aggregated to hourly means, an hour requiring at
least three of its four quarters – plus island air temperature,
population-weighted from ERA5 on the same station weights the daily
HDD feed uses. Both sources backfill by walking chunks and re-fetch
the most recent for revisions.

**Every series is keyed on Irish local clock, not UTC.** EirGrid
stamps its rows on local time and the weekly layer already treats
them that way, so the temperature request asks Open-Meteo for
`Europe/Dublin` rather than the UTC the daily HDD feed uses. Joined on
mixed clocks the store would put temperature an hour out of step with
demand from late March to late October – silently, and in the
direction that misaligns an evening peak with the cold that caused it.

**The series are written as flat arrays**, not one key per value:
`t0` is the base hour and position *i* is `t0 + i` hours, null where
absent. At one key per value the file reached 1,025 kB rewritten
daily and the repeated 13-character keys were most of it; the array
form is about 30% of that. Readers accept both shapes, so the run
that first writes the new encoding still inherits the old file rather
than refilling thirteen months from empty. The spring clock change
skips a local hour and shows up as one null a year – the same shape
as a feed gap, and indistinguishable from one by design.

The store is a **separate file with its own schema**: a failure there
cannot corrupt the weekly tracker. Two gates, deliberately separate.
`complete` covers the demand/wind/solar trio and governs the grid
panel; `heat_ready` additionally requires the temperature series at
95%, and governs the electrification computations. Carbon gates
itself as an overlay. Nothing already shipping can be withdrawn by a
series that is still filling.

Groundwork for the electrification-headroom and dispatch-down
absorption panels. Holding temperature rather than degree hours means
hourly HDD, ODH₂₆ and the Carnot source temperature all derive from
one retained series.

## What heat costs to make

The Irish equivalent of the UK sibling's cost-of-delivered-heat panel,
with **oil as the main series** because the island is the most
oil-heated corner of western Europe. Five routes – oil boiler, gas
boiler, air-source, ground-source, geothermal network – priced weekly
in native minor units per useful kWh. Pipeline side only so far; the
panel itself is not drawn.

**Daily, and every electric route is priced at that day's own COP.**
Ported from the UK sibling so the two dashboards compute the electric
routes the same way. The panel had one air-source SPF for the whole
record, which made every electric line a flat multiple of the
electricity price – they could never spread apart in the cold, which is
the effect the chart exists to show. Space flow follows the weather from
30 °C at +15 down to 50 °C at −5; hot water is held at 52 °C year-round,
because without that split a mild summer day gives absurd COPs on a load
that is entirely hot water. The oil price is the only weekly input, so it
is step-held across the week rather than interpolated.

**The mode regime is seasonal; the COP is instantaneous.** A boiler in
January does not drop to summer cycling efficiency because one day was
mild – it is still running its space-heating circuit, and the sub-40%
hot-water efficiency arises from a regime rather than a day. So the
hot-water/space blend runs on a trailing 28-day share while the
heat-pump COPs follow the day's own temperature. Blending the fuels on
each day's own share made the oil line sawtooth between adjacent days,
which is a shaping artefact rather than a price signal. Both shares are
published: the daily one for the caption, the smoothed one for the
money.

The method runs in the UK's order: assert the SPF anchor, then calibrate
the Carnot fraction so the heat-weighted trailing-year SPF reproduces it.
The four calibrated fractions must land within 15% of each other, or the
source temperature and the anchor are not describing the same machine.

**The two jurisdictions run different network models**, because
Permo-Triassic HSA is an NI play with no onshore ROI equivalent at scale.
Northern Ireland takes the UK sibling's blend – UTES and
intermediate-doublet together, source 19.6 °C, SPF 5.0. The Republic
takes a 5G ambient loop on seasonal storage alone, charged from comfort
cooling and process rejection, source 16 °C, SPF 4.0.

**Each day is priced at its own hot-water share, and every route is
priced in the mode that day actually demands.** Hot water is flat
across the year while space heat follows the week's share of the
trailing year's degree days, so a July week is almost all hot water –
and every route performs worse on hot water than on space heat. Oil
boilers cycling for a small summer load fall furthest: BRE put them
under 40% gross in water-only mode against ~85% annual. Heat pumps
degrade too, to the MCS defaults of 1.70 (air source, MCS 031 Issue
4.0) and 2.24 (ground source) against annual figures of 2.80 and 3.24.
The geothermal network figure is derived at the same lift ratio as
ground source, because both are ground-coupled with a constant source
and the hot-water penalty is flow temperature alone. Pricing the summer
at an annual efficiency would flatter the heat pumps and flatter the
boiler at exactly the point where the lines converge.

**The immersion leakage is zeroed.** Oil households do switch to the
cylinder immersion in summer rather than fire a boiler at sub-40% for a
small load, and at COP 1 that is dearer than the inefficient boiler – so
the mechanism is real and it pushed the oil line up, not down. But at
30% it was adding 5.8 c to the summer oil figure, nearly half of it
electricity rather than oil, on no metered evidence: the research found
consumer guidance and owner forums and nothing measured. It sat under
the most striking feature of the chart, and the UK sibling has no
equivalent, so carrying it broke parity between the two dashboards. The
constant stays in the code at zero; a metered Irish or NI study of
summer immersion use is what would turn it back on.

**What still differs between the two dashboards.** The heat-pump side is
aligned – both price hot water at a 52 °C cylinder flow year-round while
space heat follows the weather-compensated curve. The remaining divergence is
the boiler: this site prices a boiler at a separate hot-water efficiency
where the UK applies one figure year-round. Those figures are now taken
from **SAP 2012 Table 4b**, which publishes a winter and a summer
seasonal efficiency for every gas and oil archetype – 0.71 oil and 0.75
gas, the mean modern-stock summer/winter ratio applied to this site's
winter anchors.

They were 0.55 and 0.68, built on a BRE remark about two specific oil
boilers having "very low hot water efficiency (under 40% gross)" and
treated here as a fleet floor. Table 4b is the fleet answer: summer runs
82–89% of winter across every archetype, and the worst row in the whole
table – a single-burner range cooker boiler at 47/37 – is still 0.79.
The panel was using 0.67, below anything SAP publishes for any boiler,
and the summer oil penalty is roughly half what was shown: the oil line
now swings 15% between winter and summer rather than 49%.

Two things are deliberately not applied. Table 4b is SAP's fallback for
boilers absent from the Product Characteristics Database, so it is
conservative and skewed to older plant; a BER-weighted PCDB figure would
beat it, and BER records boiler make and model. And Table 4c deducts
5 points from both figures where a regular boiler has no interlock,
which is common in older Irish installations†.

**Every route pays what it would actually pay.** The panel priced all
five at domestic tariffs, which was wrong twice. About a quarter of the
island's building heat is services rather than residential, and the hero
bill has always blended that – so the cost panel disagreed with the bill
on the same page. And a heat network operator is not a household at all:
it buys electricity on a commercial contract and would never pay a
domestic tariff. So gas, air source and ground source blend domestic and
non-domestic at the services share of island heat input; the geothermal
network prices wholly at non-domestic, whoever the end customer is; and
oil stays a single price, because kerosene sells to both sectors on the
same terms and no non-domestic oil rate exists.

**Retail and ex-tax, with the wedge derived rather than left to the
browser.** Deliberately *ex-tax*, not *wholesale*: the EU bulletin's
without-taxes line is product, distribution and margin, not a wholesale
quote, and the same is true of a unit rate with its tax stripped. VAT
comes off first in both jurisdictions, because it is charged on the
carbon-tax-inclusive price; the carbon component comes off after.

The two sides of the border are not symmetrical. ROI kerosene carries a
carbon component (16.081 c/litre at €63.50 a tonne), the NORA levy at
2 c/litre and VAT at 13.5%; ROI gas carries the Natural Gas Carbon Tax
at 1.148 c/kWh and VAT at 9%. NI kerosene is fully duty-rebated with no
carbon price, and NI gas and electricity carry no carbon price and no
Climate Change Levy on domestic use – so NI ex-tax is retail over 1.05,
exactly rather than approximately. The result is that two oil lines
sitting about a third apart at retail converge to within a few percent
ex-tax: the border in heating cost is a policy wedge, not a market one.

Ireland's carbon increase on non-propellant fuels normally lands on
1 May; for 2026 it was postponed to **14 October**, so the rate is a
dated table rather than a constant and the discontinuity sits inside
the record.

**Carbon and VAT are dated tables, not constants.** Removing the floor
took the panel to 122 weeks and April 2024 on its first run, which is
before the carbon table began – 55 weeks were being charged €63.50 a
tonne when the rate was €56.00 or less, silently. The table now covers
the whole Finance Act 2020 trajectory and refuses anything earlier
rather than clamping, so a missing figure is visible where a wrong one
was not. VAT is dated too: ROI gas and electricity stepped from 13.5%
to 9% on 1 May 2022, and kerosene never got the cut.

**The series is not floored at the back-look's start.** That floor
exists because four tariff anchors are verified from 1 October 2025;
this panel is a different artefact, and its limit is how far the
weather record reaches, since every week needs a trailing year of
degree days behind it to know its own hot-water share.

Two things this does not claim. The heat-pump hot-water figures are MCS
design defaults, not field measurements: the Electrification of Heat
trial did not meter hot water separately, so no field hot-water SPF
exists. And the oil price is the EU bulletin's heating gas oil line
read as a kerosene level – a different product, 35-second against
28-second – which remains a stated Causeway judgement.

## Phase B.2 – the grid layer

Three computations run and logged **before any panel is drawn**, so the
headline is chosen after the numbers are seen rather than before.

**B.2.1, the tightest hour, is live and log-only.** Island useful heat
is shaped hourly from the store's own degree hours – hot water flat,
space heat degree-shaped – put through a Carnot-fraction COP at each
hour's actual air temperature, netted of the resistive heating already
inside observed demand, and added to observed all-island demand. The question it answers is the UK sibling's: **how far can heat be
electrified inside the fleet that already exists**, solved per route
rather than assumed. Fixing a share instead would force a choice
between this site's own 20% what-if and a 100% ceiling that appears
nowhere else, and the answer swings entirely on which is picked; the
netting is linear in the share, so solving is exact.

The ceiling **breathes with the weather** – the de-rated dispatchable
block plus the wind and solar actually generated in that hour – because
the hour that binds is cold and still and dark, and a flat block would
either credit wind that was not blowing or ignore wind that was. It is
also how the UK ceiling is defined, and the two figures are not
comparable otherwise.

Headroom is
reported for every route, not just one, because which routes fit under
the block IS the result – leaving it to be subtracted from three other
numbers was the first thing the live run exposed. The same line states
the island's useful heat in that hour against the electrical block,
which is the comparison the whole phase exists to make.

The
binding hour is reported against the de-rated dispatchable block
(~8,595 MW†, of which ~1,490 MW is run-hour-limited) with the observed
all-island peak of 7,502 MW on 8 January 2025 as the sanity rail. The
same hour is reported for three routes, on the **same tiers as the UK
sibling** so the two grid layers read against one ladder – air source
2.80 and ground source 3.24, both Energy Systems Catapult in-situ field
figures rather than brochure SCOPs, and a networked geothermal ambient
loop at 5.0. Ground and network are flat by construction, because a
borehole field does not care what the air is doing.

The air route is the exception: it is priced at each hour's own
Carnot-fraction COP, not the seasonal 2.80, because the point of that
column is that air-source performance collapses in the hour that binds.
Both figures are logged side by side, and the gap between them is the
argument.

Nothing draws from it. It is soft: a failure there cannot touch the
weekly tracker, and it declines rather than guessing if the store is
short or has no temperature.

**B.2.3 has its price series, filling forward.** `price_ai` – SEMOpx
day-ahead in EUR/MWh – is the store's sixth series, with its own gate so
it cannot withdraw the grid trio or the heat layer while it climbs. The
parser was reading the CSV's delivery-timestamp row and discarding it,
keeping only a daily mean; the stamps are now retained, because B.2.3
asks what price applied in one hour.

Prices are keyed on the **Irish local clock**, because every other
series in the store is and B.2.3 asks what price applied in one hour.
The offset is measured, not assumed: a trade day runs 00:00 to 23:00
local by definition and the resource name states which day it is, so
the shift is taken from the document's own first period. Two timezone
guesses – UTC, then CET – were each wrong and each cost a run to
disprove; anchoring needs no guess at all, and a document that cannot
be anchored contributes nothing rather than something misaligned.

History comes by **paging, not filtering**. The probe found that a
`Date` parameter returns nothing while a deep descending page reaches
months back and an unsorted listing returns the oldest documents in the
archive, so the days are there and simply have to be walked to. The
backfill is bounded per run – six listing pages, twelve trade days –
converging over runs in the same pattern the hourly chunks and the
temperature archive already use, rather than four hundred requests in
one build.

**The SEMO probe came back inconclusive, and now says so.** Its first
live run returned the same 50 documents from every trial – one report
ID, all from 2019 – because that endpoint lists documents ascending by
date rather than report types, and its text filter is ignored. The
probe announced it had found the catalogue anyway. It now tests for
more than one report ID and, failing that, says to read the catalogue
by hand rather than inviting a third round of guesses.

**B.2.2's per-farm layer has a probe.** Per-unit downward dispatch is
published on SEMO, but SEMO does not retain the full history – so the
series exists only from the day capture starts, and every day without
a feed is a day that cannot be recovered. `semo_dispatch_probe()` lists
the report catalogue on both API families and logs it, rather than
guessing a report ID; the feed is written against those logs, once it
is clear which report names resource codes and half-hourly periods.

The panel does not wait on it. The annual regional report and
EirGrid's 30-minute jurisdiction series are already published, so
B.2.2 can be built on those now and the per-farm map becomes a later
upgrade once the captured series has a winter in it. Two limitations
travel with any per-farm work: the volumes do not separate constraint
from curtailment, and the generator coordinates are not public, so a
unit-code-to-farm-to-location register has to be built separately.

**B.2.2 (dispatch-down absorption) is not built.** B.2.2 needs its dispatch-down basis settled first – the
2,139 GWh spilled in 2025 is an annual figure and there is no hourly
curtailment series – and it needs the regional split, because an
all-island absorption number is the one its own caveat disowns.

## Sibling comparability

This tracker is read beside the [UK Heat Split](https://causewaygt.github.io/uk-heatsplit/).
Any topline scoped differently between the two carries an explicit note –
cooling is the live example: this site's cold-economy census (data
centres, cold chain, process, comfort) is wider than the UK's
comfort-scoped line and the hero declares it. A standing test compares
extensive quantities per capita against the UK anchors; electricity
emissions use live all-island grid intensity once a week of the EirGrid
series exists.

## Versioning

**Temporarily frozen at x = 5.** The scheme is `x.y.z` – x a new source
or panel, y a source update, z wording or format – but while the site is
under construction only y and z move. The panels are changing weekly and
an x that tracked every new one would carry no information. The
masthead's "Under Construction" label and this freeze come off together.


`x.y.z` – x: new source or panel; y: source update; z: wording/format.
Pipeline and site are versioned independently; both are stamped in the
footer alongside the build time.

## Development

```
pip install requests openpyxl
python3 tests/test_synthetic.py   # 158 tests, no network
python3 scripts/build.py          # full build, writes docs/data.json
```

Tests validate parsers against verbatim formats captured from live run
logs, derivations against hand calculations, the regression against
synthetic data with injected confounds, and the Why heat? anchors against
their own internal logic (services reconcile to final consumption; heat's
bill is the smallest; imports never exceed the service).

## Attribution

Contains data from Gas Networks Ireland (CC BY 4.0 via data.gov.ie),
EirGrid Group (Smart Grid Dashboard), SEMOpx, the European Commission Weekly Oil Bulletin, the
Consumer Council for Northern Ireland, BoilerJuice, the European Central
Bank, ERA5/Copernicus via Open-Meteo, the WGC2026 Ireland country update
(Ireland, Blake, Pasquali, Dunphy & Hunter Williams), the EGEC Geothermal
Market Report 2025 (Key Findings), and NISRA/SEAI/DfE publications as
cited on the site. Sherwood Sandstone geothermal context: Todd et al.,
*Geoenergy* (2026), doi:10.1144/geoenergy2025-057.
