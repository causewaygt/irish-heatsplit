# Irish Heat Split

How the island of Ireland heats itself, weekly – a live, self-updating public
dashboard covering Northern Ireland and the Republic of Ireland. Sibling of
the [UK Heat Split](https://causewaygt.github.io/uk-heatsplit/).

Built and maintained by [Causeway Energies](https://causewaygt.com), Belfast.
Pipeline version 0.1.0 – scaffold; front end to follow.

## Why a separate Irish site

The island of Ireland is the most oil-heated region in Western Europe – just
over 60% of NI homes and roughly 35–40% of ROI homes heat with oil delivered
by tanker. Oil has no grid, no meter, and no daily data feed. Most of
Ireland's heat is invisible, and that data gap is the story this site tells.
The gas minority gets the live-regression treatment; oil gets an annual
anchor shaped by degree days, plus a price ticker with genuine daily pulse.

## Architecture

Zero-maintenance by design. A daily GitHub Actions cron (04:17 UTC) runs
`scripts/build.py`, which pulls keyless public feeds, computes the week's
numbers, and commits `docs/data.json`. A self-contained `docs/index.html`
renders it via GitHub Pages. No servers, no keys, no databases.

Every feed runs inside try/except – a failed fetch retains the previous
values and marks the source stale on-page. Fetch health and data recency are
tracked as different facts: `ok` (fetched and current), `lagging` (fetched,
source publishes on a lag), `stale` (fetch failed, previous run retained).
Feed and report identifiers are resolved from catalogues at runtime, never
hardcoded; on failure the pipeline dumps available names to the Actions log.

## Feeds

| Feed | Source | Cadence | Status |
|---|---|---|---|
| Electricity – demand, wind, solar, CO2 intensity (ROI / NI / all-island) | EirGrid Smart Grid Dashboard | 15-min, aggregated daily | live |
| Degree days – island, ROI, NI (population-weighted, base 15.5 °C) | ERA5 via Open-Meteo | daily | live |
| EUR/GBP reference rate | European Central Bank | daily | live |
| Gas – daily demand by sector incl. NDM (history / calibration) | Gas Networks Ireland via data.gov.ie, CC BY 4.0 | daily data, quarterly refresh | live |
| Gas – daily NDM, near-real-time | GNI Data Transparency portal | daily | pending endpoint probe |
| Wholesale power price, dual currency | SEMOpx day-ahead market results | D+1 | verify on first run |
| Heating oil price, ROI (heating gas oil, € per 1 000 L) | European Commission Weekly Oil Bulletin | weekly | verify on first run |
| Heating oil price, NI (300/500/900 L) | Consumer Council for Northern Ireland | daily Mon–Fri + weekly | pending markup probe |

## Methodology spine

Daily non-daily-metered (NDM) gas demand – households and SMEs, power
stations already excluded – is regressed on population-weighted heating
degree days. The temperature-sensitive component is space heat
(Watson/Sansom convention). Trailing figures are calibrated to national
end-use statistics: SEAI energy balances and the BER database for ROI, DfE
Energy in Northern Ireland and the NISRA Continuous Household Survey for NI.
Non-gas fuels – above all oil – are annual anchors shaped by degree days.
Regression logic is validated against synthetic data with injected seasonal
confounds before any release (`tests/test_synthetic.py`).

The ROI Weekly Oil Bulletin product is heating gas oil; Irish homes mostly
burn kerosene. The adjustment between the two is a Causeway judgement figure
pending cross-check against the CSO CPI heating-oil sub-index.

## Sourced vs judged

Figures taken directly from a published source are attributed to it.
Figures requiring Causeway judgement carry a dagger (†) and the footnote:
*Current Causeway Energies estimate – challenge and input welcome at
[contact@causewaygt.com](mailto:contact@causewaygt.com).* That inbox is
monitored and challenges are wanted.

## Running locally

```
pip install requests openpyxl
python3 tests/test_synthetic.py     # synthetic tests, confound-injected
python3 scripts/build.py            # writes docs/data.json
```

## Versioning

`PIPELINE_VERSION` (and later `SITE_VERSION`) follow x.y.z – x new source or
panel, y source update, z wording or format.

## Attribution and licences

Contains data from: Gas Networks Ireland (CC BY 4.0, via data.gov.ie);
EirGrid Group Smart Grid Dashboard; SEMOpx; the European Commission Weekly
Oil Bulletin; the Consumer Council for Northern Ireland; the European
Central Bank; and ERA5 (Copernicus Climate Change Service) via Open-Meteo
(CC BY 4.0). Source data remains the property of the respective publishers;
exact attribution wording per feed is confirmed as each feed goes live.

Dashboard code and Causeway-derived figures © Causeway Energies
(Causeway Geothermal NI Ltd). Contact:
[contact@causewaygt.com](mailto:contact@causewaygt.com).
