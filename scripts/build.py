#!/usr/bin/env python3
"""
Irish Heat Split - daily build pipeline (scaffold).
Sibling of uk-heatsplit build.py. PIPELINE_VERSION 0.1.0.

Feed status at scaffold time (July 2026):
  LIVE      eirgrid       - Smart Grid Dashboard JSON API (15-min; ROI/NI/ALL)
  LIVE      hdd           - Open-Meteo ERA5 archive + forecast tail, Irish pop weights
  LIVE      ecb_fx        - ECB daily EUR/GBP reference rate (keyless XML)
  LIVE      gni_ckan      - data.gov.ie CKAN daily gas demand CSV (quarterly refresh -
                            history/calibration; cadence marked "lagging" by design)
  VERIFY    semopx        - SEMOpx reports API, DAM results (self-resolving report
                            discovery; endpoint pattern from community use, confirm
                            on first run)
  VERIFY    oil_bulletin  - EU Weekly Oil Bulletin xlsx, Ireland heating gas oil
                            (self-resolving link discovery from bulletin page;
                            NOTE gas oil != kerosene - dagger adjustment pending)
  STUB      gni_live      - GNI Data Transparency portal daily NDM export
                            (XHR endpoint not yet probed - fill GNI_LIVE_ENDPOINT)
  STUB      ccni_oil      - Consumer Council NI daily/weekly oil checker
                            (page markup not yet probed - parser is best-effort,
                            dumps diagnostics on failure)

House rules honoured:
  - Self-resolve IDs/links from catalogues at runtime; never hardcode fragile URLs.
  - On failure, dump available names/headers to the Actions log (self-diagnosing).
  - Every feed in try/except; failure -> previous values retained + status "stale".
  - Fetch health and data recency are different facts: "ok" vs "lagging" vs "stale".
  - Auto-detect units from median magnitude where formats are uncertain.
  - Clip future-dated rows and duplicated days before analysis.
  - En dashes in all user-facing strings.
"""

import datetime as dt
import io
import json
import re
import statistics
import sys
import traceback
from pathlib import Path
from xml.etree import ElementTree

import requests

# ---------------------------------------------------------------- constants

PIPELINE_VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "docs" / "data.json"
SERIES_KEEP_DAYS = 400          # keep ~13 months in data.json for YoY panels
UA = {"User-Agent": "ioi-heatsplit/0.1 (contact@causewaygt.com)"}
TIMEOUT = 60

# Population weights for degree days - Causeway judgement figures (dagger).
# All-island set; jurisdiction sets derived for per-panel HDD.
# Challenge and input welcome at contact@causewaygt.com.
STATIONS = {
    #  name        lat      lon     all-island   jurisdiction
    "Dublin":    (53.35,  -6.26,   0.40, "ROI"),
    "Belfast":   (54.60,  -5.93,   0.20, "NI"),
    "Cork":      (51.90,  -8.47,   0.12, "ROI"),
    "Galway":    (53.27,  -9.05,   0.08, "ROI"),
    "Limerick":  (52.66,  -8.63,   0.08, "ROI"),
    "Derry":     (54.99,  -7.31,   0.06, "NI"),
    "Waterford": (52.26,  -7.11,   0.06, "ROI"),
}
HDD_BASE_C = 15.5

# STUB - fill after XHR probe of
# https://www.gasnetworks.ie/about/data-transparency/exit-flows/gas-consumption-by-market-sector
GNI_LIVE_ENDPOINT = None   # e.g. "https://www.gasnetworks.ie/<probed-xhr-path>"

NTFY_TOPIC = None          # set to uk-heatsplit's ntfy topic or a sibling


# ---------------------------------------------------------------- utilities

def log(*a):
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}]", *a, flush=True)


def today_utc():
    return dt.datetime.now(dt.timezone.utc).date()


def clip_days(day_values: dict) -> dict:
    """Drop future-dated keys (NESO lesson) - keys are 'YYYY-MM-DD' strings."""
    cut = today_utc().isoformat()
    return {k: v for k, v in day_values.items() if k <= cut}


def trim_series(day_values: dict) -> dict:
    keep = (today_utc() - dt.timedelta(days=SERIES_KEEP_DAYS)).isoformat()
    return dict(sorted((k, v) for k, v in day_values.items() if k >= keep))


def autodetect_scale_to_gwh(values):
    """Median-magnitude unit sniff: kWh vs MWh vs GWh for national daily gas."""
    med = statistics.median(abs(v) for v in values if v is not None) if values else 0
    if med > 1e6:
        return 1e-6, "kWh->GWh"
    if med > 1e3:
        return 1e-3, "MWh->GWh"
    return 1.0, "GWh"


def recency_status(latest_day: str | None, fresh_within_days: int) -> str:
    """Fetch succeeded - but is the data itself current?"""
    if not latest_day:
        return "stale"
    age = (today_utc() - dt.date.fromisoformat(latest_day)).days
    return "ok" if age <= fresh_within_days else "lagging"


# ---------------------------------------------------------------- feeds

def feed_eirgrid():
    """
    Smart Grid Dashboard - undocumented but heavily used JSON service.
    15-min rows; aggregated here to daily. Regions: ROI, NI, ALL.
    Self-diagnosis: on unexpected shape, log the first 500 chars of the body.
    """
    base = "https://www.smartgriddashboard.com/DashboardService.svc/data"
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=14)
    fmt = "%d-%b-%Y %H:%M"

    areas = {
        "demand": "demandactual",
        "wind": "windactual",
        "solar": "solaractual",
        "co2_intensity": "co2intensity",
        "co2_emission": "co2emission",
    }
    out = {"regions": {}}
    for region in ("ALL", "ROI", "NI"):
        rec = {}
        for key, area in areas.items():
            r = requests.get(base, params={
                "area": area, "region": region,
                "datefrom": start.strftime(fmt), "dateto": end.strftime(fmt),
            }, headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            try:
                rows = r.json().get("Rows", [])
            except Exception:
                log(f"eirgrid: non-JSON body for {area}/{region}:",
                    r.text[:500])
                raise
            daily = {}
            for row in rows:
                v = row.get("Value")
                if v is None:
                    continue
                d = dt.datetime.strptime(
                    row["EffectiveTime"], "%d-%b-%Y %H:%M:%S").date().isoformat()
                daily.setdefault(d, []).append(float(v))
            if key == "co2_intensity":
                agg = {d: round(statistics.mean(vs), 1) for d, vs in daily.items()}
            else:
                # MW at 15-min -> GWh/day
                agg = {d: round(sum(vs) * 0.25 / 1000, 2) for d, vs in daily.items()}
            rec[key] = trim_series(clip_days(agg))
        out["regions"][region] = rec

    latest = max(out["regions"]["ALL"]["demand"] or {"": None})
    out["latest_day"] = latest or None
    out["units"] = {"demand": "GWh/day", "wind": "GWh/day", "solar": "GWh/day",
                    "co2_intensity": "gCO2/kWh (daily mean)",
                    "co2_emission": "tCO2/day equivalent - verify on first run"}
    out["source"] = ("EirGrid Group Smart Grid Dashboard - all-island system data, "
                     "regions ROI/NI/ALL")
    return out, recency_status(out["latest_day"], 3)


def feed_hdd():
    """Open-Meteo ERA5 archive (history) + forecast past_days (tail). Keyless."""
    daily_by_station = {}
    for name, (lat, lon, w, jur) in STATIONS.items():
        merged = {}
        # archive - trailing 400 days, publishes on ~5-day lag
        a = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": lat, "longitude": lon,
            "start_date": (today_utc() - dt.timedelta(days=SERIES_KEEP_DAYS)).isoformat(),
            "end_date": today_utc().isoformat(),
            "daily": "temperature_2m_mean", "timezone": "UTC",
        }, headers=UA, timeout=TIMEOUT).json()
        for d, t in zip(a["daily"]["time"], a["daily"]["temperature_2m_mean"]):
            if t is not None:
                merged[d] = t
        # forecast API fills the recent tail
        f = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "past_days": 10,
            "forecast_days": 1, "daily": "temperature_2m_mean", "timezone": "UTC",
        }, headers=UA, timeout=TIMEOUT).json()
        for d, t in zip(f["daily"]["time"], f["daily"]["temperature_2m_mean"]):
            if t is not None:
                merged.setdefault(d, t)
        daily_by_station[name] = clip_days(merged)

    def weighted(subset):
        wsum = sum(STATIONS[n][2] for n in subset)
        days = set.intersection(*(set(daily_by_station[n]) for n in subset))
        return {
            d: round(max(0.0, HDD_BASE_C - sum(
                daily_by_station[n][d] * STATIONS[n][2] for n in subset) / wsum), 2)
            for d in sorted(days)
        }

    all_st = list(STATIONS)
    roi = [n for n in STATIONS if STATIONS[n][3] == "ROI"]
    ni = [n for n in STATIONS if STATIONS[n][3] == "NI"]
    out = {
        "hdd_island": trim_series(weighted(all_st)),
        "hdd_roi": trim_series(weighted(roi)),
        "hdd_ni": trim_series(weighted(ni)),
        "base_c": HDD_BASE_C,
        "weights_note": ("Population weights are current Causeway Energies "
                         "estimates - challenge and input welcome at "
                         "contact@causewaygt.com"),
        "source": "ERA5 via Open-Meteo, population-weighted HDD",
    }
    latest = max(out["hdd_island"] or {"": None})
    out["latest_day"] = latest or None
    return out, recency_status(out["latest_day"], 3)


def feed_ecb_fx():
    """ECB daily reference rate - keyless XML. EUR base."""
    r = requests.get(
        "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
        headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    root = ElementTree.fromstring(r.content)
    ns = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    cube_day = root.find(".//e:Cube[@time]", ns)
    rate = None
    for c in cube_day.findall("e:Cube", ns):
        if c.get("currency") == "GBP":
            rate = float(c.get("rate"))
    if rate is None:
        avail = [c.get("currency") for c in cube_day.findall("e:Cube", ns)]
        log("ecb_fx: GBP missing - available currencies:", avail)
        raise ValueError("GBP not in ECB daily cube")
    out = {"eur_gbp": rate, "gbp_eur": round(1 / rate, 5),
           "rate_date": cube_day.get("time"),
           "latest_day": cube_day.get("time"),
           "source": "ECB euro foreign exchange reference rates (daily)"}
    return out, recency_status(out["latest_day"], 5)


def feed_gni_ckan():
    """
    data.gov.ie CKAN - GNI daily gas demand by sector, CC-BY 4.0.
    Quarterly refresh: history and calibration, deliberately marked
    "lagging" once older than 100 days. Resource URL self-resolved from
    the CKAN catalogue at runtime - never hardcoded.
    """
    pkg = requests.get(
        "https://data.gov.ie/api/3/action/package_search",
        params={"q": "daily gas demand", "rows": 10},
        headers=UA, timeout=TIMEOUT).json()
    results = pkg.get("result", {}).get("results", [])
    resource_url = None
    for ds in results:
        if "gas networks ireland" not in json.dumps(ds.get("organization", {})).lower() \
           and "gas" not in ds.get("title", "").lower():
            continue
        for res in ds.get("resources", []):
            if res.get("format", "").upper() == "CSV" \
               and "demand" in (res.get("name", "") + ds.get("title", "")).lower():
                resource_url = res.get("url")
                break
        if resource_url:
            break
    if not resource_url:
        log("gni_ckan: no CSV resource matched - datasets found:",
            [d.get("title") for d in results])
        raise ValueError("CKAN resolution failed")
    log("gni_ckan: resolved", resource_url)

    csv_text = requests.get(resource_url, headers=UA, timeout=TIMEOUT).text
    lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    log("gni_ckan: header:", header)

    def col(*needles):
        for i, h in enumerate(header):
            hl = h.lower()
            if all(n in hl for n in needles):
                return i
        return None

    i_date = col("date") if col("date") is not None else 0
    i_ndm = col("ndm") or col("non", "daily")
    i_power = col("power")
    if i_ndm is None:
        raise ValueError(f"gni_ckan: NDM column not found in {header}")

    ndm, power = {}, {}
    for ln in lines[1:]:
        parts = [p.strip().strip('"') for p in ln.split(",")]
        try:
            d = parts[i_date][:10]
            d = dt.date.fromisoformat(d.replace("/", "-")).isoformat()
        except Exception:
            continue
        try:
            ndm[d] = float(parts[i_ndm])
            if i_power is not None:
                power[d] = float(parts[i_power])
        except (ValueError, IndexError):
            continue

    scale, unit_note = autodetect_scale_to_gwh(list(ndm.values()))
    ndm = {k: round(v * scale, 2) for k, v in ndm.items()}
    power = {k: round(v * scale, 2) for k, v in power.items()}
    out = {"ndm_gwh": clip_days(ndm),          # full history kept - calibration
           "power_gwh": clip_days(power),
           "unit_detection": unit_note,
           "latest_day": max(ndm) if ndm else None,
           "source": ("Gas Networks Ireland via data.gov.ie, CC-BY 4.0 - "
                      "quarterly refresh, calibration series")}
    # 100-day tolerance: quarterly cadence is expected, not a failure
    return out, recency_status(out["latest_day"], 100)


def feed_gni_live():
    """
    STUB - GNI Data Transparency portal daily NDM ("Export all data").
    Endpoint requires one browser dev-tools probe. Once GNI_LIVE_ENDPOINT
    is set, implement: fetch date range, parse sectors DM / NDM / ROI LDM /
    ROI Power Gen, autodetect units, clip future rows, dedupe days.
    Until then this raises cleanly and data.json carries status "stale"
    with the note below - the front end can render the panel as pending.
    """
    if GNI_LIVE_ENDPOINT is None:
        raise NotImplementedError(
            "GNI live endpoint not yet probed - see scripts/build.py header")
    raise NotImplementedError("probe done? then implement the parser here")


def feed_semopx():
    """
    SEMOpx DAM results - public reports API. Report group discovered at
    runtime by name match, not hardcoded ID (self-resolving). D+1 cadence,
    weekend batch Monday: recency tolerance 4 days.
    """
    listing = requests.get(
        "https://reports.semopx.com/api/v1/documents/static-reports",
        params={"page_size": 50, "sort_by": "PublishTime", "order_by": "DESC"},
        headers=UA, timeout=TIMEOUT).json()
    items = listing.get("items", [])
    if not items:
        log("semopx: empty listing - raw:", json.dumps(listing)[:500])
        raise ValueError("semopx listing empty")

    def is_dam_result(it):
        name = (it.get("ReportName") or it.get("DPuG_ID") or "") + \
               (it.get("ResourceName") or "")
        return re.search(r"market result", name, re.I) and \
            re.search(r"day[- ]?ahead|DA", name, re.I)

    dam = [it for it in items if is_dam_result(it)]
    if not dam:
        log("semopx: no DAM result matched - report names seen:",
            sorted({(it.get("ReportName") or "?") for it in items}))
        raise ValueError("semopx DAM report not found in listing")

    doc = dam[0]
    resource = doc.get("ResourceName") or doc.get("_id")
    log("semopx: resolved report", doc.get("ReportName"), resource)
    body = requests.get(
        f"https://reports.semopx.com/documents/{resource}",
        headers=UA, timeout=TIMEOUT)
    body.raise_for_status()

    prices_eur, prices_gbp, day = [], [], None
    try:
        j = body.json()
        blob = json.dumps(j)
        day_m = re.search(r"20\d\d-\d\d-\d\d", blob)
        day = day_m.group(0) if day_m else None
        for m in re.finditer(r'"(EUR|GBP)Price[s]?"\s*:\s*(-?\d+\.?\d*)', blob):
            (prices_eur if m.group(1) == "EUR" else prices_gbp).append(
                float(m.group(2)))
    except ValueError:
        # XML report - keep the raw head in the log for the first-run check
        log("semopx: non-JSON document, first 500 chars:", body.text[:500])
        raise

    if not prices_eur and not prices_gbp:
        log("semopx: parsed no prices - document keys:",
            list(j)[:20] if isinstance(j, dict) else type(j).__name__)
        raise ValueError("semopx price parse failed - inspect log")

    out = {
        "dam_avg_eur_mwh": round(statistics.mean(prices_eur), 2) if prices_eur else None,
        "dam_avg_gbp_mwh": round(statistics.mean(prices_gbp), 2) if prices_gbp else None,
        "trade_day": day, "latest_day": day,
        "source": "SEMOpx day-ahead market results - dual currency (EUR/GBP)",
    }
    return out, recency_status(day, 4)


def feed_oil_bulletin():
    """
    EU Weekly Oil Bulletin - Ireland heating gas oil, EUR per 1000 L,
    prices WITH taxes. Link self-resolved from the bulletin page at runtime
    (download URLs are UUID-based and fragile). Weekly cadence: tolerance
    10 days. NOTE - bulletin product is gas oil; Irish homes mostly burn
    kerosene. Dagger adjustment pending: cross-check vs CSO CPI sub-index.
    """
    page = requests.get(
        "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en",
        headers=UA, timeout=TIMEOUT).text
    links = re.findall(r'href="([^"]+)"[^>]*>([^<]*)', page)
    xlsx = [(u, t) for u, t in links
            if ".xlsx" in u.lower() or ".xlsx" in t.lower()]
    with_tax = [u for u, t in xlsx
                if re.search(r"with[ _]tax", (u + t), re.I)
                and not re.search(r"without", (u + t), re.I)]
    if not with_tax:
        log("oil_bulletin: no 'with taxes' xlsx resolved - xlsx links seen:",
            [(u[:90], t[:60]) for u, t in xlsx][:10])
        raise ValueError("oil bulletin link resolution failed")
    url = with_tax[0]
    if url.startswith("/"):
        url = "https://energy.ec.europa.eu" + url
    log("oil_bulletin: resolved", url)

    import openpyxl
    wb = openpyxl.load_workbook(
        io.BytesIO(requests.get(url, headers=UA, timeout=120).content),
        read_only=True, data_only=True)
    log("oil_bulletin: sheets:", wb.sheetnames)

    series = {}   # date -> EUR/1000L
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = None
        for row in rows:
            cells = [str(c) if c is not None else "" for c in row]
            joined = " ".join(cells).lower()
            if header is None:
                if "heating" in joined and ("gas" in joined or "oil" in joined):
                    header = cells
                    idx_heat = next(i for i, c in enumerate(cells)
                                    if "heating" in c.lower())
                continue
            if "ireland" in joined or (cells and cells[0].strip() == "IE"):
                # date column: first parseable date-ish cell
                d = None
                for c in row:
                    if isinstance(c, dt.datetime):
                        d = c.date().isoformat()
                        break
                    m = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", str(c))
                    if m:
                        d = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
                        break
                try:
                    v = float(row[idx_heat])
                except (TypeError, ValueError, IndexError):
                    continue
                if d:
                    series[d] = round(v, 2)
    if not series:
        log("oil_bulletin: Ireland heating gas oil not parsed - "
            "sheet/header dump above; adjust parser after first-run log")
        raise ValueError("oil bulletin parse failed - inspect log")

    series = trim_series(clip_days(series))
    latest = max(series)
    out = {
        "roi_heating_gasoil_eur_per_1000l": series,
        "latest_value": series[latest], "latest_day": latest,
        "kerosene_caveat": ("Bulletin product is gas oil - Irish homes mostly "
                            "burn kerosene; adjustment is a current Causeway "
                            "Energies estimate pending CSO CPI cross-check"),
        "source": "European Commission Weekly Oil Bulletin - prices with taxes",
    }
    return out, recency_status(latest, 10)


def feed_ccni_oil():
    """
    Consumer Council NI oil checker - daily (Mon-Fri) + weekly, 300/500/900 L.
    Markup not yet probed: parser is best-effort table extraction and dumps
    diagnostics for the first-run check. Failure -> stale, previous retained.
    """
    urls = {
        "daily": "https://www.consumercouncil.org.uk/home-heating/price-checker/daily",
        "weekly": "https://www.consumercouncil.org.uk/home-heating/price-checker",
    }
    out = {"prices_gbp": {}}
    got_any = False
    for cadence, url in urls.items():
        html = requests.get(url, headers=UA, timeout=TIMEOUT).text
        # generic scan: pound amounts near litre labels
        found = {}
        for litres in ("300", "500", "900"):
            m = re.search(
                litres + r"\s*(?:litre|l)\b.{0,300}?£\s*(\d{2,3}(?:\.\d{2})?)",
                html, re.I | re.S) or re.search(
                r"£\s*(\d{2,3}(?:\.\d{2})?).{0,300}?" + litres + r"\s*(?:litre|l)\b",
                html, re.I | re.S)
            if m:
                found[f"{litres}l"] = float(m.group(1))
        if found:
            out["prices_gbp"][cadence] = found
            got_any = True
        else:
            snippet = re.sub(r"\s+", " ", html)
            i = snippet.lower().find("litre")
            log(f"ccni_oil: {cadence} parse empty - context around 'litre':",
                snippet[max(0, i - 300):i + 300] if i >= 0 else snippet[:600])
    if not got_any:
        raise ValueError("ccni_oil: no prices parsed - inspect log, fix selector")
    out["latest_day"] = today_utc().isoformat()   # survey date not yet parsed - TODO
    out["source"] = ("Consumer Council for Northern Ireland home heating oil "
                     "price checker - daily (Mon-Fri) and weekly survey")
    return out, "ok"


# ------------------------------------------------- analysis (pure functions)

def space_heat_split(gas_daily: dict, hdd_daily: dict):
    """
    OLS of daily NDM gas on HDD; temperature-sensitive component = space heat
    (Watson/Sansom convention, as per UK pipeline). Pure function - unit
    tested synthetically in tests/test_synthetic.py, including an injected
    seasonal confound. Returns (slope GWh/HDD, intercept GWh/day, r2, n).
    """
    days = sorted(set(gas_daily) & set(hdd_daily))
    if len(days) < 30:
        return None
    x = [hdd_daily[d] for d in days]
    y = [gas_daily[d] for d in days]
    n = len(days)
    mx, my = statistics.mean(x), statistics.mean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        return None
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    ss_tot = sum((yi - my) ** 2 for yi in y) or 1e-9
    return {"slope_gwh_per_hdd": round(slope, 3),
            "baseload_gwh_per_day": round(intercept, 2),
            "r2": round(1 - ss_res / ss_tot, 3), "n_days": n}


# ---------------------------------------------------------------- assembly

FEEDS = {
    "eirgrid": feed_eirgrid,
    "hdd": feed_hdd,
    "ecb_fx": feed_ecb_fx,
    "gni_ckan": feed_gni_ckan,
    "semopx": feed_semopx,
    "oil_bulletin": feed_oil_bulletin,
    "gni_live": feed_gni_live,
    "ccni_oil": feed_ccni_oil,
}


def main():
    previous = {}
    if DATA_PATH.exists():
        try:
            previous = json.loads(DATA_PATH.read_text()).get("feeds", {})
        except Exception:
            log("warning - previous data.json unreadable, starting clean")

    feeds, failures = {}, []
    for name, fn in FEEDS.items():
        log(f"--- {name}")
        try:
            payload, status = fn()
            payload["status"] = status
            payload["fetched_utc"] = dt.datetime.now(
                dt.timezone.utc).isoformat(timespec="seconds")
            feeds[name] = payload
            log(f"{name}: {status}, latest_day={payload.get('latest_day')}")
        except Exception as e:
            log(f"{name}: FAILED - {e.__class__.__name__}: {e}")
            traceback.print_exc()
            prev = previous.get(name, {})
            prev["status"] = "stale"
            prev.setdefault("source", "previous run retained")
            feeds[name] = prev
            # stubs failing is expected - do not page for them
            if not isinstance(e, NotImplementedError):
                failures.append(name)

    # derived: ROI space-heat regression once both series present
    gas = feeds.get("gni_ckan", {}).get("ndm_gwh") or {}
    hdd = feeds.get("hdd", {}).get("hdd_roi") or {}
    reg = space_heat_split(gas, hdd)
    derived = {"roi_space_heat_regression": reg} if reg else {}
    if reg:
        log("regression:", reg)

    doc = {
        "pipeline_version": PIPELINE_VERSION,
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "feeds": feeds,
        "derived": derived,
        "notes": ("Feed statuses - ok: fetched and current; lagging: fetched, "
                  "source publishes on a lag; stale: fetch failed, previous "
                  "values retained. Judgement figures are current Causeway "
                  "Energies estimates - challenge and input welcome at "
                  "contact@causewaygt.com"),
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(doc, indent=1, sort_keys=True))
    log(f"wrote {DATA_PATH} ({DATA_PATH.stat().st_size/1024:.0f} kB)")

    if failures:
        log("hard failures:", failures)
        if NTFY_TOPIC:
            try:
                requests.post(f"https://ntfy.sh/{NTFY_TOPIC}",
                              data=f"ioi-heatsplit build: failed {failures}",
                              timeout=15)
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
