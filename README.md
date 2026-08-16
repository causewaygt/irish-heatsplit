# Irish Heat Split

**How the island of Ireland heats itself, weekly – and how much of that heat
no one can see.**

Live site: https://causewaygt.github.io/irish-heatsplit/
Sibling of the [UK Heat Split](https://causewaygt.github.io/uk-heatsplit/).
Built and maintained by [Causeway Energies](https://causewaygt.com)
(Causeway Geothermal NI Ltd). Pipeline 5.23.1 / site 5.22.3.

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
boiler, air-source, ground-source, geothermal network – priced daily in
currency per MWh of delivered heat, on the same axis as the UK sibling.
Three toggles: service, basis, window.

*(This paragraph read "priced weekly in native minor units per useful
kWh. Pipeline side only so far; the panel itself is not drawn" until
5.9.0, by which point the panel had been drawn for some time and the
paragraph directly under it already said daily. Corrected rather than
left.)*

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

**Three services, toggled together: space heating, as delivered, hot
water.** They answer different questions and the answers diverge. On
space heat a heat pump rides a weather-compensated flow down to 30 °C;
on hot water the cylinder pins it at 52 °C whatever the weather, so
none of that benefit is available. Every electric route pays a similar
penalty in absolute terms, so the cheapest takes the largest
proportional hit and the geothermal advantage *narrows* on hot water –
it is not air source collapsing, which is what an earlier version of
this note claimed. "As delivered" blends the two at the season's own
share and is the default, because it is what a household pays.

**Axes are currency per MWh of delivered heat**, matching the UK
sibling – the two charts were showing the same kind of number in
different clothes, 7 c/kWh against £44/MWh.

**Two gates on the degree-day series.** The trailing-year total is
checked against a plausibility band on every run, because the failure it
catches is invisible otherwise: the UK sibling once raised a regression
window from 365 to 730 days, every quantity that treated the window as a
year silently doubled, and all four of its test suites passed throughout.
The band is provisional until the first live figure. And the degree-day
base is scanned at 14.5, 15.5 and 16.5 against gas demand and the fit
reported – log-only, because moving the base moves every shaped figure
on the site, which is a decision rather than a tuning.

**Hot-water shares are published by fuel** – SEAI's residential end-use
model gives oil at 22.8% and gas at 26.8% – and those price the energy
and bill panels. They are deliberately *not* used in the cost panel,
where every route answers the same counterfactual, so the share belongs
to the building's demand rather than to the fuel; using them there would
compare two different demand profiles.

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

**The volume under the price (5.9.0).** A second chart shares the price
chart's x-axis and shows what the per-MWh figure is charged on: GWh of
delivered heat that day, space heating stacked under hot water, in the
same window and the same jurisdiction. It is **invariant to service and
basis** – it is the island's heat, not a route and not a tax basis – and
the caption says so rather than leaving the reader to test the buttons.

Its shaping is not a second model. Hot water is flat across the year,
space heat follows the day's share of the trailing year's degree days –
the identical rule behind `dhw_share`, so `dhw / (space + dhw)`
reproduces that share exactly, and a test pins it. What the volume adds
is the scale: the sector anchors are fuel **input**, so they go through
each jurisdiction's own fuel mix and efficiencies first, the same
conversion `hourly_heat_mw()` uses. Delivered against input, that is
about 25.3 TWh a year in ROI and 10.9 TWh in NI, against 30.8 and 13.0
of purchased fuel. Shape is island-wide, scale is jurisdictional: one
degree-day series shapes both, the same simplification the share has
always carried.

A volume is emitted only once 200 days of degree days sit behind the
day, so the early end of a long window can be bare while the recent end
is full. The chart **declines a partly covered window** and names the
day the volume starts, rather than plotting the bare days at zero –
which would read as "no heat that day".

**Three guards shipped ahead of the back-look extension, not after it.**
`nondom_for` now REFUSES a week before the first published REMM
semester instead of clamping it to that semester; callers decline the
day or the week by name. Clamping was safe only while nothing reached
back that far, and extending the window is exactly what removes that
safety – the same fault already fixed for carbon and for tariffs.
`retention_span_gate` asserts the retained record covers the widest
window plus its trailing year; the margin is 55 days, thin enough that
a change to any of the three constants should break the build rather
than quietly shape space heat on a season. And `heat_cost_series` is
now written columnar, same wire format and same encoder as the history
block – measured at 32% of flat – with both readers accepting either
shape, because index.html publishes on the Pages deploy while
data.json only changes at 04:17.

**The 60-month window has been withdrawn** from both panels. `HISTORY_MAX`
is 120 weeks, about 27 months, so that button could never fill whatever
happened to the tariff table; stated reach and actual reach are now the
same number. Removing it surfaced a live defect: `WLBL` carried no entry
for the 24-month window, so every card label on that button read "over
the last undefined" from the day it shipped. `tests/test_vol.js` now
pins the window maps and the buttons against each other in both
directions.

**NI oil comes from two CCNI pages (5.10.0).** The daily checker
(Mon–Fri) is the recent detail; the **weekly archive** carries the whole
published record, 277 points back to April 2021. The archive page embeds
a chart array of exactly the same shape as the daily page, so it parses
through the same functions — no scraper, no new parser. That is what
lets the NI oil series reach a 24-month window; the daily page alone
cannot. The archive fetch is soft: if it fails the run keeps the daily
series and loses reach, nothing else.

The two merge into one series so every consumer reads it unchanged, with
the daily reading winning any overlap and their disagreement logged each
run rather than averaged. Which page priced a week is recorded in
`daily_page_days` and surfaced as `ni_oil_source`, because a week
carried by the archive alone is a mean of one reading rather than five.

`ccni_ratio_gate` names rows whose litre ratios cannot be right — a
day's three figures come from one survey, so their ratios barely move
even as the level swings. Three such rows exist in CCNI's record
(17 Jun 2021, 9 Sep 2021, 17 Nov 2021) and only the last is visible in
the 900 L series the site prices on, where it sits about 10% above both
neighbours. The gate does not reject them: the series is published and
we do not get to overrule it.

**NI oil is step-held across its week (5.11.0), capped.** The archive is
weekly, so pricing only the survey days left the NI line as one point in
seven behind the daily checker's start — 144 of 375 days on the first
live run against ROI's 375. That reads as missing data rather than as a
weekly survey. The most recent reading at or before a day is held
forward, exactly as the ROI bulletin week always has been, capped at
`NI_OIL_HOLD_DAYS` so a single reading is not smeared across one of the
archive's real gaps (there is a 26-day one after its first row and a
21-day one in 2023).

**The back-look reaches April 2024 (5.12.0).** Both sides of the tariff
table had to move together. The sterling side was already a dated table;
the euro side was derived at call time from a single S2 2025 anchor, so
extending one alone would have priced every earlier Irish day at the
2025 level, silently — the same fault the table's own refusal was
written to prevent. Three sterling rows come from UREGNI's tariff-review
releases, which publish the annual bill at this site's own consumption
basis; the row added at 1 April 2025 reproduces the old floor row
exactly, which is the check that bill-over-consumption is the right
derivation. The Irish side becomes `IE_DOMESTIC_SEMESTER`, the published
band series by semester — band DC electricity, band D2 gas, the bands
the existing anchors were shown to sit on.

**Irish electricity is credit-free; Irish gas is untouched.** Between
2022 and 2025 domestic electricity accounts received €1,500 in lump sums
per meter, and SEAI books those into the effective unit price. The
distortion is visible in the band gradient alone: the same electricity
shows +93% in the smallest consumption band and −4% in the largest,
because a fixed sum is worth more per kWh the less you use. A lump sum
never changed the cost of the next kWh, so on a cost-of-delivered-heat
axis it is added back. Households did pay less than the series shows in
those semesters — it is the unit rate, not the bill, and the panel says
so. Gas accounts were never eligible.

**The divisor for that add-back is a judgement†.** Three controls
bracket it: band DE flatness implies about 1,500 kWh a semester, the
S2 2024 reconciliation about 1,810, and the S1 2024 double-credit check
about 2,000. The site's own 3,200 kWh/yr basis was the first candidate
and is **not** used — at that divisor the corrected S1 2025 lands exactly
on S2 2025, implying no market movement across an autumn in which four
suppliers raised prices. The midpoint is carried and every run logs what
the series would be at either end of the bracket.

**Irish prices step by semester, as published**, rather than riding a
12-month mean. That keeps the figure traceable to SEAI's table with no
transformation of ours in between, at the cost of an artefact worth
knowing: household gas reads about 6% higher in the July–December half
every year, because fixed network costs spread over far fewer summer
units.

**The weekly record reaches back too (5.13.0), as far as carbon allows.**
`HISTORY_START` moves from August 2025 to February 2025 — not all the
way to the tariff table's April 2024 floor, because the binding
constraint on the weekly record is no longer tariffs but each week's own
grid carbon. The daily EirGrid feed retains 50 days and the hourly store
13 months, so an older week has no carbon unless it is fetched; the
probe's demonstrated reach is 18 months. A one-off deep backfill walks
monthly chunks until the retained series covers the floor, then never
runs again. **A reconstructed week without its own carbon is refused by
name, not priced at the anchor** — otherwise its emissions would be
today's grid intensity wearing last year's date. The record therefore
extends itself as the backfill reaches further and can never contain a
week it cannot date.

**Panel 2 has its own jurisdiction toggle**, under the title, Republic or
Northern Ireland. It previously followed panel 1, which meant selecting
"all island" above silently showed the Republic below. There is no
all-island option: the panel prices in one currency per jurisdiction, so
there is no such figure to show.

**The calibration was day-weighted, not heat-weighted (5.14.0).** The
Carnot fraction η is solved so the annual heat-weighted SPF reproduces
each route's published anchor — that is what makes η a statement about
machine quality, with the source carried by the Carnot term. But the
caller passed the day's space and hot-water *shares*, two numbers
summing to 1.0 on every day, so a mild August day weighed exactly as
much as a January one. That flatters air source, whose advantage is
concentrated in mild weather, and it was most of the spread the 15%
consistency gate has been reporting.

Comparing with the UK sibling is what surfaced it. On identical
constants and identical anchors the UK's three fractions agree to 1.35%,
so the difference had to be in the weighting rather than in the physics
or the climate. With real delivered-heat volumes as the weights, the
air-source and ground-source Carnot ceilings separate as they do in
Britain, and the spread falls back inside the gate.

**The masthead ticker reads the panel's own rows (5.15.0).** It used to
come from `derive_heat_gap`, the original calculation, which never
received the panel's changes: one geothermal SPF of 4.0 for both
jurisdictions where the panel uses 5.0 in the North, a single
oil-boiler efficiency of 0.82 where the panel prices hot water at 0.71,
and no hot-water blending at all. The two disagreed by 13–20% on
identical routes on the same day, with the headline sitting above the
chart that contradicted it. `derive_heat_gap` is kept as
`heat_gap_diagnostic` for its break-even SPF figures.

The ticker also now shows the gap's **median over the window** beside
today's figure. A spot gap reads as a standing fact, and on this record
oil climbs steeply from November 2025 — so the headline was stating a
war-driven condition as though it were structural.

**The weekly record was capped by a literal (5.16.0).** `build_history`
offered `range(59, -1, -1)` while `HISTORY_MAX` was 120, and the cap was
applied afterwards to a list that could never exceed sixty. So the
record sat at sixty weeks, the run log's "60 weeks built, none skipped"
was reporting the loop bound rather than any data limit, and panel 1's
sparklines were short because they slice whatever the record holds. The
loop is now driven by `HISTORY_MAX` and a test fails if a literal
returns. What binds depth now, in order: the carbon backfill's reach,
then the tariff table floor — and a week that cannot be priced is
refused by name rather than filled in.

The carbon-reach diagnostic also moved out of the backfill branch. It
only logged when the backfill fired, so on every other run it said
nothing — and nothing is indistinguishable from "the block never ran",
which is precisely the case the line exists for. It now reports where
the carbon record reaches, and whether that covers `HISTORY_START`,
every run.

**Panel 1 has a method fold (site 5.10.0).** "How this is estimated, and
why it is not metered" sits at the foot of the panel and now carries the
anchors-and-degree-days prose, the gas engine room chart and its note,
the feed status table, and a new calibration board. The standalone
"Method & sources" and "The gas engine room" sections are gone — each
has one home rather than two, and the strap's Methodology link opens the
fold rather than jumping to a section that no longer exists.

**The calibration board publishes what the log has always said.** For
each jurisdiction and route it shows the solved Carnot fraction beside
the SPF anchor it was solved to reproduce and the source temperature it
saw, then states how closely the three agree and whether that is inside
the 15% gate. A fraction without its anchor means nothing, so they
travel together. This is the exhibit that answers "how do you know the
COP model is right", and after the weighting fix the fractions agree to
1.6% in the North and 7.6% in the Republic, against the UK sibling's
1.35%.

**Panel 2's title follows its own jurisdiction toggle**, as panel 1's
does — "What Northern Ireland's heat costs and emits" over a sterling
view rather than "the island of Ireland's".

**What heat emits (5.18.0).** gCO₂e per *useful* kWh by route, under
panel 2 with its own method fold — the Irish answer to the UK sibling's
sub-panel. Combustion factors are applied to the fuel burned and then
divided by the boiler efficiency, so every bar is per unit of heat
delivered rather than per unit purchased; electric routes take the live
all-island grid intensity over each route's seasonal performance factor.

**It is all-island and has no jurisdiction toggle, deliberately.** The
combustion factors do not change at the border, the efficiencies are
shared, and the grid is a single all-island market — so a split would
draw the same bars three times. That is the finding rather than a gap,
and the panel says so: the price answer differs sharply across the
border and the carbon answer does not at all.

The heat network here is **geothermal, not the gas-fired network assumed
in most comparisons**. Its figure is the ambient loop at an island SPF
that is the heat-weighted **harmonic** mean of 5.0 in the North and 4.0
in the Republic — harmonic because efficiencies average that way, and an
arithmetic mean would flatter it.

**Panel 3 is stubbed in, and the oil ticker has moved (site 5.12.0).**
"Electricity grid impacts — the 20% what-if, hour by hour" now sits
third, where the oil ticker was; the ticker has moved to the foot of the
page beneath "Why heat?". The panel carries its jurisdiction toggle and
its scope note; the charts follow.

**The toggle switches whose heat is electrified, not the ceiling.** The
SEM is a single all-island market with one dispatch, and Northern Irish
demand is met from all-island generation across the tie-lines — so a
separate northern capacity ceiling would invent a constraint that does
not exist. Each jurisdiction's what-if is measured against one shared
de-rated block, and the panel says so rather than leaving it implied.
The regional constraint story — network constraints are about
two-thirds of dispatch-down and concentrated west and northwest, while
SNSP is around 1% — is geography rather than jurisdiction, and belongs
in the map panel rather than here.

**Panel 3 draws the coldest hour (site 5.13.0).** B.2.1 has been computed
and logged since the grid layer landed and has ridden in the payload as
`tightest_hour` all along; this is the first time it appears on the page.
Per route it shows the added load in GW, that load as a share of what the
island was using in that hour, and whether it fits the ceiling or exceeds
it and by how much — then the ceiling itself as the de-rated block plus
the wind and solar actually generated, so it breathes with the weather.
Beneath, the share of island heat that fits inside today's fleet, with
its binding hour.

The framing that must travel with it is on the page, not just in the
README: this is a **peak-capacity test, not an energy test** — nothing
here phases the conversion or counts storage, diversity or demand
response.

**The NI and ROI states decline rather than relabelling.** The hourly
heat what-if is computed all-island, so a jurisdiction split needs hourly
heat per jurisdiction, which is not built. Selecting either says so
instead of showing island figures under a jurisdiction heading.

**The three views Panel 3 plots are published (5.19.0).** 168 hourly
rows, 90 daily and up to 24 monthly — about 280 against a store of nine
thousand hours, so the payload carries what is drawn rather than what was
computed, at roughly 34 kB. Each row is the island's delivered heat and
the electricity the site's own 20% what-if would draw by route, netted of
the resistive heating already inside observed demand, on the same hourly
air-source COP the binding-hour panel uses.

**Two what-ifs, deliberately kept apart.** The binding-hour panel *solves*
for the share of heat that fits inside today's fleet; these views plot
the *fixed* 20% the rest of the site uses. They answer different
questions, and a test asserts the solve is not pinned to the constant,
because reading them as one number is the easy mistake.

**The route ordering is not universal, and that is a finding.** In the
cold, air source draws the most electricity of the three. In mild weather
the weather-compensated air COP passes ground source's flat 3.24 and the
two invert — the same effect that closed the Carnot ceilings in the
calibration work. The test pins both ends rather than asserting an
ordering that only holds in winter.

**Panel 3's three views are drawn (site 5.14.0).** Hourly over the live
week, daily over 90 days, and monthly — heat delivered on the left axis
and the 20% what-if's electricity by route on the right, because the two
quantities differ by roughly an order of magnitude and one axis would
flatten the electricity into the floor. Heat is dashed so it reads as the
demand being met rather than a fourth route.

**The monthly view says what it is not.** The hourly store holds about
thirteen months, so the falcon is not yet a year-on-year comparison and
the view states that rather than drawing a single loop that looks like
one. It fills in on its own as the store deepens.

**Two hours, two questions, and the labels distinguish them.** The
binding-hour cards solve for the share of heat that fits; the views plot
the fixed 20%. The added-load hour and the share-that-fits hour differ by
one hour in the live data, which is correct and would otherwise look like
an error.

**The falcon curve (5.20.0), and a correction.** I said it needed two
winters of history and deferred it. It does not. It is a **calendar
year** with each month filled by the **latest complete instance** of that
month — January to July from this year, August to December from last —
so twelve complete months is enough, and a thirteen-month store already
carries a full one. `derive_grid_views` publishes `falcon`: twelve rows
ordered by calendar month, each tagged with the month it came from, plus
`falcon_complete` so a shorter store draws a partial curve rather than a
misleading one. The monthly view plots it and the note says how it is
built.

**The grid layer never reached the payload (5.20.1).** `data.json` is
serialised before the hourly block runs, so `tightest_hour` and
`grid_views` were being assigned to a dict already written to disk. Panel
3 drew its decline messages for two bundles while the run log showed
B.2.1 and the falcon computing perfectly — the renderers were right and
the payload was empty. The tell was visible and missed: `data.json`
stayed at 1,436 kB when the grid views should have added about 34 kB.
`main()` now writes again once the grid keys exist, and says in the log
when they are absent; the first write stays where it is so a payload
still lands if the hourly step throws.

**The tightest hour of the year, in the UK sibling's layout (site
5.16.0).** Four cards — the binding hour with its temperature and the
wind and solar that blew, then each route's **total** requirement in GW
rather than just its increment, with the spare capacity left or the
amount it goes over. Beneath, stacked bars: a grey base of what the
island was already using in that hour, identical on every bar, plus the
coloured increment the what-if adds, against the ceiling as a dashed
rule. Only the increment differs between bars, which is the comparison
the panel exists to make.

Route colours are the same here, on the price chart and on the three-view
chart, so a route reads as one colour across the whole page.

The ceiling label states its construction inline — de-rated dispatchable
block plus the wind and solar actually generated — because that figure
is the panel's most contestable input and should not need a footnote to
find. **Note that `GRID_BLOCK_MW` remains under review**: the AIRAA
Appendix 3 it cites is a plant register, and whether the 8,595 MW is
installed or de-rated is unresolved.

**Panel subtitles and chart tidying (site 5.17.0).** The six `.foldh`
subtitles move from green mono at 0.72rem — which read as a code comment
rather than a heading — to white Lato 11pt, all caps, with real space
above them. The descriptive clause after each keeps its muted
sentence-case form via a `.sub` span.

On the tightest-hour chart, the ceiling label used to sit *on* the dashed
line and ran straight through the bars, unreadable where it crossed
them. It is now right-anchored above the line carrying only the figure,
with the composition — de-rated block plus the wind and solar that
actually blew — in its own band above the plot. The plot is taller, its
top padding leaves room for the increment labels instead of pushing them
onto the top gridline, and the bars are narrower so the three read as a
comparison rather than a wall.

**"How much of the island's heat fits inside today's fleet" is now a
sub-panel (site 5.18.0)**, in the same shape as the tightest hour above
it: subtitle, cards, chart, short note. It was a three-row table. Each
route gets its share as a card and a bar, against a dashed rule at 100%
— all of the island's building heat — with routes that fall short drawn
at reduced opacity so the two outcomes are distinguishable before you
read a number. Each card names that route's own binding hour, which
differs by route because the hour that constrains a route depends on how
much electricity it draws when it is cold.

**The two sub-panels ask the same question from opposite ends**, and the
note says so: the first fixes the share at a fifth and reports what it
costs, the second solves for the largest share the fleet could carry.
Reading them as one number would be the easy mistake, which is also why
a pipeline test asserts the solve is not pinned to `GRID_WHATIF_SHARE`.

**Panel 3 chart tidying (site 5.19.0).** Three fixes across both
sub-panels. Hours read as **5 Jan 2026 · 17:00** rather than
`2026-01-05T17`, on the cards and the binding-hour labels. Axis ticks are
**round numbers** — the old code divided an arbitrary maximum into
thirds and produced 76 / 151 / 227%; the new chooser tries each candidate
step, keeps those giving three to six intervals, and takes the one
wasting least plot height, which turns 11.9 GW into a 0–12 axis rather
than 0–15. And **no label crosses a bar**: the ceiling line on the first
chart and the 100% rule on the second both moved into a band above the
plot, after the 100% label was found running straight through the
geothermal bar.

Chart text also moved up in size and contrast — tick labels and bar
values from muted grey at 11px to white and `--ink2` at 13–16px, since
the previous setting was close to unreadable against the dark theme at
presentation scale.

**Wind that was thrown away (5.21.0).** Monthly wind dispatch-down by
jurisdiction and reason, 2021 to date, from EirGrid's own half-hourly
files. Bars are GWh a month stacked by reason; a dashed line on a second
axis carries the share of available wind spilled.

**Stacked by reason, not by the constraint/curtailment fold**, because
the fold hides the finding. Northern Ireland spills 22–30% of its
available wind and roughly 85% of that is transmission constraint — the
local kind that only local load can absorb. The Republic runs 10–13% at
about half that constraint share. Those are different problems, and only
one of them has a heat answer.

The series ships as a **static** `docs/dispatch_down_monthly.json`.
The half-hourly downloads sit behind a JavaScript accordion on EirGrid's
site and carry version suffixes that change without notice (`V7`, `v10`),
so a fetcher built on a guessed URL would rot silently rather than fail
loudly. `tools/dd_convert.py` regenerates the file from downloaded
workbooks and asserts the schema rather than trusting it; closed years
never change.

**Column relationship, corrected.** `DD = CURTAILMENTS + CONSTRAINTS`
exactly, and `OTHER` sits *outside* dispatch-down — DSO/DNO constraints,
developer outages and developer testing, which are not TSO actions. An
earlier reading of 1,314 non-reconciling rows was a wrong formula, not a
data quirk.

The heat conversion uses seasonal SPFs and is labelled on the panel as
**an energy-scale statement, not a dispatch claim**: it takes no account
of whether the spill coincided with heat demand, and a large flexible
load would itself change the dispatch. The hourly-COP refinement is
available only for the last 13 months and would make the series
inconsistent with itself.

**Panel 3 axis fix (site 5.20.1).** `niceTicks` returns values in GW
while the plotting function works in MW, and 5.19.0 fed one to the other.
Every gridline landed on the baseline and the axis printed seven zeroes
stacked on top of each other — which read on the page as no axis and no
ceiling line at all. The tick values are now converted at the point of
use, and the fixture suite asserts the labels are distinct, that the
gridlines sit at distinct heights, and that the axis runs 0 to 12 GW.
It passed throughout the fault because nothing checked any of that.

Both dashed rules — the capacity ceiling and the 100% line — are now
white at 2px, and the share cards are laid out on the plot's own margins
so each figure sits over its bar rather than 5% to the left of it.

**Charting harness rebuilt (site 5.20.2).** Three changes, after two
charts shipped visibly broken while their tests stayed green.

*The harness evaluates the whole script block once* rather than lifting
each function by its own regex. The per-function lifts worked while
renderers were self-contained and broke as soon as they shared helpers —
three consecutive runs failed on "X is not defined" before a single
assertion ran, and `MONTHS3` ended up lifted twice. One consequence is
worth knowing: `let` and `const` declarations inside an eval do not
persist, only function declarations do, so the page's state is exposed
through accessors defined inside the eval itself.

*That immediately caught two false passes.* The harness had been
defining its own `fmt` stub, so several assertions had never met the
page's real formatter — which uses `minimumFractionDigits: 0` and prints
2.80 as "2.8" and 1.046 GW as "1 GW".

*Shared geometric predicates* now back every chart: `gridlinesSpread`,
`noTextInsideBars` and `usesItsAxis`, each scoped to a single `<svg>`.
Both shipped faults were geometry, and both passed a suite that only
asked whether elements existed. All three are proven by mutation — the
collapsed axis, a squashed scale and a label crossing the bars each make
the suite fail. The label predicate needed a second pass: testing the
anchor point alone missed the original fault, whose start sat in a gap
and whose body crossed the next two bars, so it now estimates the glyph
span.

**What the spilled energy was worth (5.22.0).** `dd_convert.py` now takes
`--prices`, an hourly SEM day-ahead series, and emits the
**volume-weighted price in the half-hours each reason was actually
spilling** alongside the month's plain average. The join derives UTC per
row from the dispatch-down file's own `GMT_OFFSET` column rather than
assuming a fixed offset.

**Spilled wind clears at roughly half the average price**, because it is
spilled when the wind blows and power is cheap. Island total since 2021:
**€721m at the prices of its own hours against €1,218m at monthly
averages** — the naive figure overstates by 40%. The chart plots the
weighted value as bars and the naive figure as a dashed line, so the gap
between them is the correction rather than a claim made in prose.

**Constraint hours clear about 40% above curtailment hours** — 61% of
average against 43% — because curtailment fires on the system-wide
conditions that also crush the price, while local network constraint
does not. So the volume a local heat load can absorb is also the more
valuable volume.

**It is not a payment, and the panel says so.** Constrained wind with
firm access is already compensated, so absorbing it saves the system
operator and consumers; curtailed wind generally is not, so absorbing it
is revenue the generator keeps. Delivering the energy would also soften
the price in those hours, so even the weighted figure is an upper bound
on market value — though not on the heat, which is unaffected.

**A source caution.** Two published price series were compared and found
to disagree by a full day; the weekday profile settled which was right
(Sunday cheapest, not Monday). The error was hard to see because a date
shift pulls the weighted figure *toward* the mean, which looks like a
plausible answer rather than a broken one. A fixture test now fails if
the weighted and naive totals converge.

**What it would take to use it (5.23.0).** Two worked examples of
absorbing Northern Ireland's constrained wind — **worked examples, not
measurements**, and labelled as such on the panel. They size the *load*
it would take rather than claiming a saving, because sizing survives the
coincidence objection and a benefit claim does not: half the spill falls
outside the heating season and only 44% between midnight and six.

**The arithmetic gives the opposite answer to the one the framing
suggests.** NI constrained 563 GWh of wind in 2025 — 2,392 GWh of heat
through a network, or **22% of all the building heat Northern Ireland
uses in a year**. That would need **344 hospitals** of 7.0 GWh against an
acute estate of about ten. Institutional anchor loads cannot absorb this
volume, which is precisely why the published answer is an aggregation of
250,000 households. The hospital is the demonstrator; the aggregation is
the scale.

The domestic figures are the published results of **Agbonaye, Keatley,
Huang, Odiase & Hewitt (2022)**, *Renewable Energy* 190:487–500 — same
jurisdiction, four SONI constraint groups, hourly and spatial — quoted
rather than re-derived. The hospital is sized from the ERIC 2024/25
acute mean of 211 kWh/m² across 1,104 English sites; **the 60% heat
share is ours and daggered, since ERIC publishes total energy**, and
neither NHS Scotland nor Northern Ireland publishes an equivalent
series.

**Axis labels made legible (site 5.22.1).** Every rotated y-axis label
was rendering at x=14–18 in a 1000-unit viewBox — roughly 16px from the
frame — in 12px muted grey, which is *smaller and dimmer than the tick
numbers it was labelling*. Present, and effectively invisible. All six
across five charts move to x=26 in 13px white at weight 600, with the
left gutter widened from 56–60 to 82–88 to hold them; the three-view
chart's right-hand label moves in from the opposite edge.

A new predicate, `axisLabelReadable`, now requires every rotated label
to clear the frame, sit inside the gutter rather than over the plot, and
be no smaller than its ticks. It is proven by mutation — restoring one
label to its old position and size fails the suite. Nothing had been
testing this, which is why it survived so long.

**The worked examples run on a rolling twelve months (5.23.1)** rather
than a calendar year — currently July 2025 to June 2026, named at both
ends on the panel. It keeps the figures current without waiting for a
year to close, and it lands on the same window as the hourly store, so a
spill-weighted COP computed later will cover exactly these months rather
than a different set.

The rolling year is a harder year than calendar 2025: **656 GWh of
constrained wind rather than 563, 2,790 GWh of heat, 26% of Northern
Ireland's building heat, and 401 hospitals against an acute estate of
about ten.**

**Tick values fixed on the last two charts (site 5.22.3).** The volume
chart and the three-view chart still drew their tick numbers at 11px in
muted grey, on axes divided into halves and thirds so the values were
arbitrary rather than round. Both now use `niceTicks` at 13px in
`--ink2`, and the three-view chart's right-hand electricity axis gets the
same treatment as its left.

These two were missed when the other charts were fixed, which is why the
axes kept looking unlabelled after three rounds of "fixing the axis
labels": every assertion looked at the rotated label and none looked at
the ticks. A new predicate, `tickValuesReadable`, now requires each axis
to carry at least three distinct tick values, no smaller than 13px and
not in muted grey — proven by reverting one chart's ticks and watching
the suite fail.

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
python3 tests/test_synthetic.py   # 182 tests, no network
node tests/test_vol.js            # 175 front-end fixture checks
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
