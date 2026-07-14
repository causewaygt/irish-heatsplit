#!/usr/bin/env python3
"""
Irish Heat Split - daily build pipeline. PIPELINE_VERSION 0.1.1.

Changes 0.1.0 -> 0.1.1 (from first Actions run log, 14 Jul 2026):
  - Shared http_get() with retries + backoff (eirgrid 503, open-meteo timeout).
  - HDD: all stations batched into one archive + one forecast call; forecast
    tail is now non-fatal - archive-only degrades to "lagging", not failure.
  - gni_ckan: capture DM / LDM / Power Gen / Total ROI alongside NDM
    (header confirmed live: Date, Daily Metered, Non Daily Metered (NDM),
    Large Daily Metered (LDM) non Power Gen, Power Generation, Total ROI demand).
  - semopx: DAM results were crowded out of a 50-row PublishTime window by
    high-frequency balancing reports - multi-strategy resolution added.
  - oil_bulletin: unquote URL-encoded filenames before the "with taxes"
    match ("with%20Taxes" defeated the old regex).
  - ccni_oil: parse the embedded chart JSON series (dated, structured)
    discovered in the first-run diagnostic dump; the blind pound-regex is
    retired - it claimed "ok" without evidence.

Feed status:
  LIVE      eirgrid, hdd, ecb_fx, gni_ckan, ccni_oil
  VERIFY    semopx, oil_bulletin   - re-run and read the log
  STUB      gni_live               - fill GNI_LIVE_ENDPOINT after XHR probe

House rules honoured: self-resolve IDs/links at runtime; dump available
names on failure; every feed try/except with previous values retained and
status "stale"; fetch health vs data recency tracked separately; unit
autodetection; clip future-dated rows; en dashes in user-facing strings.
"""

import datetime as dt
import html as html_mod
import io
import json
import random
import re
import statistics
import sys
import time
import traceback
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree

import requests

# ---------------------------------------------------------------- constants

PIPELINE_VERSION = "0.1.1"
ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "docs" / "data.json"
SERIES_KEEP_DAYS = 400
UA = {"User-Agent": "ioi-heatsplit/0.1 (contact@causewaygt.com)"}
TIMEOUT = 90
RETRIES = 3

# Population weights for degree days - Causeway judgement figures (dagger).
# Challenge and input welcome at contact@causewaygt.com.
STATIONS = {
    #  name        lat      lon     weight  jurisdiction
    "Dublin":    (53.35,  -6.26,   0.40, "ROI"),
    "Belfast":   (54.60,  -5.93,   0.20, "NI"),
    "Cork":      (51.90,  -8.47,   0.12, "ROI"),
    "Galway":    (53.27,  -9.05,   0.08, "ROI"),
    "Limerick":  (52.66,  -8.63,   0.08, "ROI"),
    "Derry":     (54.99,  -7.31,   0.06, "NI"),
    "Waterford": (52.26,  -7.11,   0.06, "ROI"),
}
HDD_BASE_C = 15.5

# STUB - fill after XHR probe of the GNI Data Transparency export
GNI_LIVE_ENDPOINT = None

NTFY_TOPIC = None


# ---------------------------------------------------------------- utilities

def log(*a):
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}]", *a, flush=True)


def http_get(url, *, params=None, timeout=TIMEOUT, retries=RETRIES, headers=None):
    """GET with retries + exponential backoff + jitter. Raises on final failure."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers=headers or UA)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} {r.reason}", response=r)
            r.raise_for_status()
            return r
        except (requests.RequestException,) as e:
            last = e
            if attempt == retries:
                break
            wait = 2 ** attempt + random.uniform(0, 1.5)
            log(f"retry {attempt}/{retries - 1} after "
                f"{e.__class__.__name__} - sleeping {wait:.1f}s: {url[:80]}")
            time.sleep(wait)
    raise last


def today_utc():
    return dt.datetime.now(dt.timezone.utc).date()


def clip_days(day_values: dict) -> dict:
    """Drop future-dated keys (NESO lesson)."""
    cut = today_utc().isoformat()
    return {k: v for k, v in day_values.items() if k <= cut}


def trim_series(day_values: dict) -> dict:
    keep = (today_utc() - dt.timedelta(days=SERIES_KEEP_DAYS)).isoformat()
    return dict(sorted((k, v) for k, v in day_values.items() if k >= keep))


def autodetect_scale_to_gwh(values):
    med = statistics.median(abs(v) for v in values if v is not None) if values else 0
    if med > 1e6:
        return 1e-6, "kWh->GWh"
    if med > 1e3:
        return 1e-3, "MWh->GWh"
    return 1.0, "GWh"


def recency_status(latest_day: str | None, fresh_within_days: int) -> str:
    if not latest_day:
        return "stale"
    age = (today_utc() - dt.date.fromisoformat(latest_day)).days
    return "ok" if age <= fresh_within_days else "lagging"


def ddmmyyyy_to_iso(s: str) -> str | None:
    m = re.match(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s.strip())
    if not m:
        return None
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"


# ------------------------------------------------- pure parsers (unit tested)

def extract_chart_data_arrays(page_html: str) -> list:
    """
    Find every '"data":[[...]]' chart payload embedded in a page (possibly
    HTML-entity-escaped), bracket-matched, and return them json-parsed.
    Confirmed live format on the Consumer Council NI checker pages:
      [["","300 litres","500 litres","900 litres"],
       ["26/02/2026",202.12,307.38,536.72], ...]
    """
    text = html_mod.unescape(page_html)
    out = []
    for m in re.finditer(r'"data"\s*:\s*(\[\[)', text):
        i = m.start(1)
        depth = 0
        for j in range(i, min(len(text), i + 2_000_000)):
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        out.append(json.loads(text[i:j + 1]))
                    except json.JSONDecodeError:
                        pass
                    break
    return out


def parse_ccni_series(page_html: str) -> dict:
    """
    From a Consumer Council checker page, return
      {"300l": {iso_date: gbp}, "500l": {...}, "900l": {...}}
    using any embedded chart whose header row mentions "litre".
    """
    series = {"300l": {}, "500l": {}, "900l": {}}
    for arr in extract_chart_data_arrays(page_html):
        if not arr or not isinstance(arr[0], list):
            continue
        header = [str(c).lower() for c in arr[0]]
        if not any("litre" in h for h in header):
            continue
        cols = {}
        for idx, h in enumerate(header):
            for litres in ("300", "500", "900"):
                if litres in h:
                    cols[idx] = f"{litres}l"
        for row in arr[1:]:
            if not row:
                continue
            d = ddmmyyyy_to_iso(str(row[0]))
            if not d:
                continue
            for idx, key in cols.items():
                try:
                    v = float(row[idx])
                except (TypeError, ValueError, IndexError):
                    continue
                series[key][d] = round(v, 2)
    return series


def resolve_oil_bulletin_url(page_html: str) -> str | None:
    """
    Resolve the 'weekly prices WITH taxes' xlsx from the bulletin page.
    Filenames arrive URL-encoded ('with%20Taxes') - unquote before matching.
    """
    for m in re.finditer(r'href="([^"]+)"', page_html):
        u = m.group(1)
        decoded = urllib.parse.unquote(u).lower()
        if ".xlsx" not in decoded:
            continue
        if re.search(r"with[ _]tax", decoded) and "without" not in decoded:
            return u if u.startswith("http") else "https://energy.ec.europa.eu" + u
    return None


# ---------------------------------------------------------------- feeds

def feed_eirgrid():
    """Smart Grid Dashboard - retries added after a 503 on first run."""
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
            r = http_get(base, params={
                "area": area, "region": region,
                "datefrom": start.strftime(fmt), "dateto": end.strftime(fmt),
            })
            try:
                rows = r.json().get("Rows", [])
            except Exception:
                log(f"eirgrid: non-JSON body for {area}/{region}:", r.text[:500])
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
                agg = {d: round(sum(vs) * 0.25 / 1000, 2) for d, vs in daily.items()}
            rec[key] = trim_series(clip_days(agg))
            time.sleep(0.5)          # polite pacing - 15 calls total
        out["regions"][region] = rec

    latest = max(out["regions"]["ALL"]["demand"] or {"": None})
    out["latest_day"] = latest or None
    out["units"] = {"demand": "GWh/day", "wind": "GWh/day", "solar": "GWh/day",
                    "co2_intensity": "gCO2/kWh (daily mean)",
                    "co2_emission": "tCO2/day equivalent - verify on first success"}
    out["source"] = ("EirGrid Group Smart Grid Dashboard - all-island system "
                     "data, regions ROI/NI/ALL")
    return out, recency_status(out["latest_day"], 3)


def feed_hdd():
    """
    Open-Meteo, batched: one archive call + one forecast call for all seven
    stations (14 requests -> 2). Forecast tail is optional - archive alone
    yields data on a ~5-day lag, reported as "lagging" rather than failing.
    """
    names = list(STATIONS)
    lats = ",".join(str(STATIONS[n][0]) for n in names)
    lons = ",".join(str(STATIONS[n][1]) for n in names)

    def unpack(payload):
        # multi-location responses arrive as a list; single as a dict
        locs = payload if isinstance(payload, list) else [payload]
        per_station = {}
        for name, loc in zip(names, locs):
            d = loc.get("daily", {})
            per_station[name] = {
                day: t for day, t in zip(d.get("time", []),
                                         d.get("temperature_2m_mean", []))
                if t is not None
            }
        return per_station

    arch = unpack(http_get(
        "https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": lats, "longitude": lons,
            "start_date": (today_utc()
                           - dt.timedelta(days=SERIES_KEEP_DAYS)).isoformat(),
            "end_date": today_utc().isoformat(),
            "daily": "temperature_2m_mean", "timezone": "UTC",
        }, timeout=120).json())

    tail_ok = True
    try:
        tail = unpack(http_get(
            "https://api.open-meteo.com/v1/forecast", params={
                "latitude": lats, "longitude": lons, "past_days": 10,
                "forecast_days": 1, "daily": "temperature_2m_mean",
                "timezone": "UTC",
            }).json())
        for n in names:
            for d, t in tail.get(n, {}).items():
                arch[n].setdefault(d, t)
    except Exception as e:
        tail_ok = False
        log(f"hdd: forecast tail unavailable ({e.__class__.__name__}) - "
            "continuing archive-only, expect 'lagging'")

    daily_by_station = {n: clip_days(v) for n, v in arch.items()}

    def weighted(subset):
        wsum = sum(STATIONS[n][2] for n in subset)
        days = set.intersection(*(set(daily_by_station[n]) for n in subset))
        return {
            d: round(max(0.0, HDD_BASE_C - sum(
                daily_by_station[n][d] * STATIONS[n][2] for n in subset) / wsum), 2)
            for d in sorted(days)
        }

    roi = [n for n in names if STATIONS[n][3] == "ROI"]
    ni = [n for n in names if STATIONS[n][3] == "NI"]
    out = {
        "hdd_island": trim_series(weighted(names)),
        "hdd_roi": trim_series(weighted(roi)),
        "hdd_ni": trim_series(weighted(ni)),
        "base_c": HDD_BASE_C,
        "forecast_tail": tail_ok,
        "weights_note": ("Population weights are current Causeway Energies "
                         "estimates - challenge and input welcome at "
                         "contact@causewaygt.com"),
        "source": "ERA5 via Open-Meteo, population-weighted HDD",
    }
    latest = max(out["hdd_island"] or {"": None})
    out["latest_day"] = latest or None
    return out, recency_status(out["latest_day"], 3 if tail_ok else 7)


def feed_ecb_fx():
    r = http_get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")
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
           "rate_date": cube_day.get("time"), "latest_day": cube_day.get("time"),
           "source": "ECB euro foreign exchange reference rates (daily)"}
    return out, recency_status(out["latest_day"], 5)


def feed_gni_ckan():
    """
    data.gov.ie CKAN - GNI daily demand, CC BY 4.0. Confirmed live header:
    Date, Daily Metered, Non Daily Metered (NDM), Large Daily Metered (LDM)
    non Power Gen, Power Generation, Total ROI demand. Quarterly refresh -
    100-day recency tolerance, calibration series.
    """
    pkg = http_get("https://data.gov.ie/api/3/action/package_search",
                   params={"q": "daily gas demand", "rows": 10}).json()
    results = pkg.get("result", {}).get("results", [])
    resource_url = None
    for ds in results:
        if "gas networks ireland" not in json.dumps(
                ds.get("organization", {})).lower() \
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

    csv_text = http_get(resource_url).text
    lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    log("gni_ckan: header:", header)

    def col(*needles):
        for i, h in enumerate(header):
            hl = h.lower()
            if all(n in hl for n in needles):
                return i
        return None

    cols = {
        "ndm": col("ndm") if col("ndm") is not None else col("non", "daily"),
        "dm": col("daily metered") if "ndm" not in
              (header[col("daily metered")].lower()
               if col("daily metered") is not None else "ndm") else None,
        "ldm": col("ldm"),
        "power": col("power"),
        "total_roi": col("total"),
    }
    # "Daily Metered" matches inside "Non Daily Metered (NDM)" - take the
    # first exact-prefix match instead
    for i, h in enumerate(header):
        if h.lower().startswith("daily metered"):
            cols["dm"] = i
            break
    if cols["ndm"] is None:
        raise ValueError(f"gni_ckan: NDM column not found in {header}")

    series = {k: {} for k in cols if cols[k] is not None}
    i_date = col("date") if col("date") is not None else 0
    for ln in lines[1:]:
        parts = [p.strip().strip('"') for p in ln.split(",")]
        raw_d = parts[i_date][:10]
        d = ddmmyyyy_to_iso(raw_d) or raw_d.replace("/", "-")
        try:
            d = dt.date.fromisoformat(d).isoformat()
        except ValueError:
            continue
        for k, i in cols.items():
            if i is None:
                continue
            try:
                series[k][d] = float(parts[i])
            except (ValueError, IndexError):
                continue

    scale, unit_note = autodetect_scale_to_gwh(list(series["ndm"].values()))
    out = {"unit_detection": unit_note,
           "latest_day": max(series["ndm"]) if series["ndm"] else None,
           "source": ("Gas Networks Ireland via data.gov.ie, CC BY 4.0 - "
                      "quarterly refresh, calibration series")}
    for k, vals in series.items():
        out[f"{k}_gwh"] = clip_days(
            {d: round(v * scale, 2) for d, v in vals.items()})
    return out, recency_status(out["latest_day"], 100)


def feed_gni_live():
    """STUB - fill GNI_LIVE_ENDPOINT after the dev-tools XHR probe."""
    if GNI_LIVE_ENDPOINT is None:
        raise NotImplementedError(
            "GNI live endpoint not yet probed - see scripts/build.py header")
    raise NotImplementedError("probe done? then implement the parser here")


def feed_semopx():
    """
    SEMOpx DAM results. First run showed the unfiltered top-50 listing is
    all high-frequency balancing reports - DAM results (daily) never make
    the window. Strategies, in order, each logged:
      1. DPuG_ID=EA-001 filter (ex-ante group ID used by community clients)
      2. ReportName filter for 'ETS Market Results'
      3. page_size=500 listing, name-matched
    """
    base = "https://reports.semopx.com/api/v1/documents/static-reports"

    def is_dam(it):
        name = " ".join(str(it.get(k) or "") for k in
                        ("ReportName", "DPuG_ID", "ResourceName", "Group"))
        return bool(re.search(r"market\s*result|marketresult", name, re.I)
                    and re.search(r"ETS|day[- ]?ahead|\bDA\b|EA[-_]?00", name, re.I))

    strategies = [
        ("DPuG_ID filter", {"DPuG_ID": "EA-001", "page_size": 20,
                            "sort_by": "Date", "order_by": "DESC"}),
        ("ReportName filter", {"ReportName": "ETS Market Results",
                               "page_size": 20, "sort_by": "Date",
                               "order_by": "DESC"}),
        ("wide listing", {"page_size": 500, "sort_by": "PublishTime",
                          "order_by": "DESC"}),
    ]
    dam = []
    for label, params in strategies:
        try:
            items = http_get(base, params=params).json().get("items", [])
        except Exception as e:
            log(f"semopx: strategy '{label}' errored - {e}")
            continue
        hits = [it for it in items if is_dam(it)] or \
               (items if label != "wide listing" and items else [])
        log(f"semopx: strategy '{label}' - {len(items)} items, "
            f"{len(hits)} candidate(s)")
        if hits:
            dam = hits
            break
        if label == "wide listing" and items:
            log("semopx: names seen (wide):",
                sorted({str(it.get('ReportName') or '?') for it in items})[:40])
    if not dam:
        raise ValueError("semopx DAM report not found by any strategy")

    doc = dam[0]
    resource = doc.get("ResourceName") or doc.get("_id")
    log("semopx: resolved report", doc.get("ReportName"), resource)
    body = http_get(f"https://reports.semopx.com/documents/{resource}")

    prices_eur, prices_gbp, day = [], [], None
    try:
        j = body.json()
        blob = json.dumps(j)
    except ValueError:
        log("semopx: non-JSON document, first 800 chars:", body.text[:800])
        blob = body.text
        j = None
    day_m = re.search(r"20\d\d-\d\d-\d\d", blob)
    day = day_m.group(0) if day_m else None
    for m in re.finditer(
            r'"?(EUR|GBP)"?\s*(?:Price[s]?|_PRICE)"?\s*[:=]\s*"?(-?\d+\.?\d*)',
            blob, re.I):
        (prices_eur if m.group(1).upper() == "EUR" else prices_gbp).append(
            float(m.group(2)))
    if not prices_eur and not prices_gbp:
        keys = list(j)[:20] if isinstance(j, dict) else "n/a"
        log("semopx: parsed no prices - top-level keys:", keys)
        log("semopx: blob head:", blob[:800])
        raise ValueError("semopx price parse failed - inspect log")

    out = {
        "dam_avg_eur_mwh": round(statistics.mean(prices_eur), 2)
                           if prices_eur else None,
        "dam_avg_gbp_mwh": round(statistics.mean(prices_gbp), 2)
                           if prices_gbp else None,
        "trade_day": day, "latest_day": day,
        "source": "SEMOpx day-ahead market results - dual currency (EUR/GBP)",
    }
    return out, recency_status(day, 4)


def feed_oil_bulletin():
    """
    EU Weekly Oil Bulletin - Ireland heating gas oil, EUR/1000 L with taxes.
    Fix 0.1.1: unquote filenames before matching. Kerosene caveat stands.
    """
    page = http_get(
        "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
    ).text
    url = resolve_oil_bulletin_url(page)
    if not url:
        seen = [urllib.parse.unquote(u)[:110] for u in
                re.findall(r'href="([^"]+)"', page)
                if ".xlsx" in urllib.parse.unquote(u).lower()]
        log("oil_bulletin: no 'with taxes' xlsx resolved - decoded links:", seen)
        raise ValueError("oil bulletin link resolution failed")
    log("oil_bulletin: resolved", urllib.parse.unquote(url)[:120])

    import openpyxl
    wb = openpyxl.load_workbook(
        io.BytesIO(http_get(url, timeout=180).content),
        read_only=True, data_only=True)
    log("oil_bulletin: sheets:", wb.sheetnames)

    series = {}
    for ws in wb.worksheets:
        header, idx_heat = None, None
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            joined = " ".join(cells).lower()
            if header is None:
                if "heating" in joined and ("gas" in joined or "oil" in joined):
                    header = cells
                    idx_heat = next(i for i, c in enumerate(cells)
                                    if "heating" in c.lower())
                continue
            if "ireland" in joined or (cells and cells[0].strip() in ("IE", "EI")):
                d = None
                for c in row:
                    if isinstance(c, dt.datetime):
                        d = c.date().isoformat()
                        break
                    iso = ddmmyyyy_to_iso(str(c))
                    if iso:
                        d = iso
                        break
                try:
                    v = float(row[idx_heat])
                except (TypeError, ValueError, IndexError):
                    continue
                if d:
                    series[d] = round(v, 2)
        if header:
            log(f"oil_bulletin: sheet '{ws.title}' header:",
                [h[:30] for h in header if h][:12])
    if not series:
        raise ValueError("oil bulletin parse failed - header dumps above")

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
    Consumer Council NI - both checker pages embed full dated price series
    as chart JSON (found in the first-run diagnostic dump). Parse those;
    the daily page carries the daily Mon-Fri series, the weekly page the
    weekly survey. NI-average series assumed - council-area splits are in
    separate charts and can be added once inspected.
    """
    urls = {
        "daily": "https://www.consumercouncil.org.uk/home-heating/price-checker/daily",
        "weekly": "https://www.consumercouncil.org.uk/home-heating/price-checker",
    }
    out = {"series_gbp": {}}
    got_any = False
    for cadence, url in urls.items():
        page = http_get(url).text
        parsed = parse_ccni_series(page)
        n = sum(len(v) for v in parsed.values())
        if n:
            out["series_gbp"][cadence] = {
                k: trim_series(clip_days(v)) for k, v in parsed.items()}
            got_any = True
            log(f"ccni_oil: {cadence} - {n} datapoints across "
                f"{[k for k, v in parsed.items() if v]}")
        else:
            arrays = extract_chart_data_arrays(page)
            log(f"ccni_oil: {cadence} - no litre-labelled chart; "
                f"{len(arrays)} chart array(s) found, first headers:",
                [a[0] for a in arrays[:3] if a])
    if not got_any:
        raise ValueError("ccni_oil: no series parsed - inspect log")

    all_days = [d for c in out["series_gbp"].values()
                for s in c.values() for d in s]
    out["latest_day"] = max(all_days) if all_days else None
    out["source"] = ("Consumer Council for Northern Ireland home heating oil "
                     "price checker - daily (Mon-Fri) and weekly survey, "
                     "NI average, 300/500/900 L")
    return out, recency_status(out["latest_day"], 7)


# ------------------------------------------------- analysis (pure functions)

def space_heat_split(gas_daily: dict, hdd_daily: dict):
    """OLS of daily NDM gas on HDD - see tests/test_synthetic.py."""
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
            if not isinstance(e, NotImplementedError):
                failures.append(name)

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
