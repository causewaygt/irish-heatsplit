# Irish Heat Split

**How the island of Ireland heats itself, weekly – and how much of that heat
no one can see.**

Live site: https://causewaygt.github.io/irish-heatsplit/
Sibling of the [UK Heat Split](https://causewaygt.github.io/uk-heatsplit/).
Built and maintained by [Causeway Energies](https://causewaygt.com)
(Causeway Geothermal NI Ltd). Pipeline 1.3.0 / site 1.2.1.

## The premise

The island of Ireland is the most oil-heated corner of Western Europe.
Oil has no meter, no grid and no daily statistics – the majority of the
island's heat is invisible to the systems that watch everything else.
This tracker makes the visible parts visible daily, carries the invisible
majority as clearly-labelled annual anchors shaped by each week's weather,
and prices the alternative. The data gap is the story.

## What the site shows

- **Masthead** – the live border gap: the same kerosene priced either
  side of the border, and what the border is worth per litre.
- **Hero** – the week's heat purchased and delivered, indigenous share,
  bill in both currencies and emissions, toggled all-island / NI / ROI,
  each jurisdiction shaped by its own heating degree days; a what-if
  strip (the same week with 20% of heat from geothermal heat pumps); and
  energy-in vs useful-heat-out bars by fuel, with combustion losses
  hatched – all three responding to the jurisdiction toggle.
- **The invisible majority** – delivered building heat split into
  unmetered (oil, peat, other), gas and electric.
- **The oil ticker** – NI kerosene daily (Consumer Council survey), ROI
  weekly (EU Oil Bulletin, with- and without-taxes), both per litre on
  FX-locked twin axes; GB as a same-tax control line; dashed pre-tax
  lines making the tax wedge visible; policy events as chart markers.
  Same fuel, two price regimes, one island.
- **The gas engine room** – daily ROI gas demand against degree days;
  the temperature-sensitive slope is space heat.
- **The heat gap** – cost of one useful kWh by route (oil boiler, gas
  boiler, air-source heat pump, geothermal), toggled by jurisdiction,
  with the break-even SPF against the incumbent oil boiler as the
  headline stat. The ASHP SPF is modelled from each jurisdiction's own
  climate, not the brochure.
- **The cool side** – data-centre waste heat against the shape of heat
  demand; the stranded-summer share is the seasonal-storage (ATES) wedge.
- **Geothermal – the empty bar** – installed ground-source capacity per
  person (ROI sourced from the WGC2026 country update; NI from the
  Causeway register) stacked against what the 20% what-if requires, with
  Sweden, the Netherlands and France as installed-reality reference
  points.
- **Method & sources** – every feed, its status and its flags.

## Architecture

Static site, no backend. A GitHub Action runs `scripts/build.py` daily at
04:17 UTC, fetching every feed with retries, merging history across runs,
and writing a single `docs/data.json` (~0.5 MB) that `docs/index.html`
renders client-side with Plotly. GitHub Pages serves `/docs`.

### Feeds

| Feed | Source | Cadence | Notes |
|---|---|---|---|
| `hdd` | ERA5 via Open-Meteo | daily | population-weighted HDD, island/ROI/NI |
| `ecb_fx` | ECB reference rates | daily | EUR/GBP twin-currency lock |
| `ccni_oil` | Consumer Council NI price checker | daily (Mon–Fri) | 300/500/900 L; history merged across runs |
| `oil_bulletin` | EU Weekly Oil Bulletin + price-history workbook | weekly | Ireland heating gas oil, with & without taxes, backfilled from 2005-onwards history |
| `gb_oil` | BoilerJuice sentence, DESNZ fallback | daily / monthly | SOFT feed – same-tax GB control line |
| `gni_live` | Gas Networks Ireland gasconsumption API | daily | ~8-day windows, weekly anchors backfill |
| `gni_ckan` | GNI via data.gov.ie (CC BY 4.0) | quarterly | calibration series for the regression |
| `semopx` | SEMOpx day-ahead results | daily | dual-currency power price |
| `eirgrid` | Smart Grid Dashboard | – | EXPECTED DOWN – endpoint probe pending |

Feed statuses: **ok** (fetched, current), **lagging** (fetched, source
publishes on a lag), **stale** (fetch failed, previous values retained).
`SOFT_FEEDS` fail quietly; `EXPECTED_DOWN` feeds are documented outages.
`FEED_FLAGS` carry value-level caveats distinct from fetch status and
render as ⚑ in the method table. `EVENTS` is a curated policy-event
register rendered as chart markers.

### Derivations (all pure functions, unit tested)

- `derive_hero` – annual anchors shaped by weekly HDD, per jurisdiction,
  island as the reconciled sum; per-fuel in/useful breakdown, peak winter
  week, and the 20% geothermal what-if.
- `derive_heat_gap` – useful-heat cost by route at live oil prices and
  standard tariffs; break-even SPF vs the oil boiler.
- `derive_ashp_spf` – air-source SPF from the HDD-weighted outdoor
  temperature via a Carnot-fraction COP with defrost derate and DHW
  share, calibrated to field-trial medians.
- `derive_cool` – data-centre waste heat vs demand shape; stranded share.
- `derive_geo_percap` – installed ground-source Wth per person vs the
  20% what-if requirement.
- `space_heat_split` – month-demeaned OLS of daily gas on HDD (within-
  month deviations, seasonal confounds removed); naive slope retained
  for reference.

## Provenance rules

Sourced figures cite their publisher. Judgement figures are marked with a
dagger (†) and are current Causeway Energies estimates – challenge and
input welcome at contact@causewaygt.com. The NI geothermal register names,
dates and statuses every system in `data.json`.

## Versioning

`x.y.z` – x: new source or panel; y: source update; z: wording/format.
Pipeline and site are versioned independently; both are stamped in the
footer alongside the build time.

## Development

```
pip install requests openpyxl
python3 tests/test_synthetic.py   # 36 tests, no network
python3 scripts/build.py          # full build, writes docs/data.json
```

Tests validate parsers against verbatim formats captured from live run
logs, derivations against hand calculations, and the regression against
synthetic data with injected confounds.

## Attribution

Contains data from Gas Networks Ireland (CC BY 4.0 via data.gov.ie),
EirGrid Group, SEMOpx, the European Commission Weekly Oil Bulletin, the
Consumer Council for Northern Ireland, BoilerJuice, the European Central
Bank, ERA5/Copernicus via Open-Meteo, the WGC2026 Ireland country update
(Ireland, Blake, Pasquali, Dunphy & Hunter Williams), the EGEC Geothermal
Market Report 2025 (Key Findings), and NISRA/SEAI/DfE
publications as cited on the site. Sherwood Sandstone geothermal context:
Todd et al., *Geoenergy* (2026), doi:10.1144/geoenergy2025-057.
