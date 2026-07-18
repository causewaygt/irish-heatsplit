# Irish Heat Split

**How the island of Ireland heats itself, weekly – and how much of that heat
no one can see.**

Live site: https://causewaygt.github.io/irish-heatsplit/
Sibling of the [UK Heat Split](https://causewaygt.github.io/uk-heatsplit/).
Built and maintained by [Causeway Energies](https://causewaygt.com)
(Causeway Geothermal NI Ltd). Pipeline 3.2.0 / site 3.1.0.

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
- **The invisible majority** – delivered building heat split into
  unmetered (oil, peat, other), gas and electric.
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
  and NI, ≈12 TWh† of electricity rejecting ≈19 TWh† of heat a year –
  refrigeration rejects more heat than the electricity it draws. Flat
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
| `eirgrid` | Smart Grid Dashboard (/api/chart/) | daily | quarter-hour demand → daily GWh, island/NI/ROI; incomplete days excluded; CO₂ probe in progress |

Feed statuses: **ok** (fetched, current), **lagging** (fetched, source
publishes on a lag), **stale** (fetch failed, previous values retained).
`SOFT_FEEDS` fail quietly; `EXPECTED_DOWN` feeds are documented outages.
`FEED_FLAGS` carry value-level caveats distinct from fetch status and
render as ⚑ in the method table. `EVENTS` is a curated policy-event
register rendered as chart markers.

## Methodology

**The scaffold estimator.** Weekly figures are not measurements – no such
measurements exist for most of the island's heat. They are annual anchors
(SEAI, DfE/NISRA, Causeway estimates) shaped by each week's weather: a
non-weather base share of demand is spread evenly across 52 weeks, and
the space-heating share follows the week's fraction of the trailing
year's heating degree days. Each jurisdiction is shaped by its own HDD
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

## Versioning

`x.y.z` – x: new source or panel; y: source update; z: wording/format.
Pipeline and site are versioned independently; both are stamped in the
footer alongside the build time.

## Development

```
pip install requests openpyxl
python3 tests/test_synthetic.py   # 45 tests, no network
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
