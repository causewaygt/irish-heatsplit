#!/usr/bin/env python3
"""
Irish Heat Split - daily build pipeline. PIPELINE_VERSION 0.5.0.

Changelog:
  0.5.0 - ONS GB heating-oil feed (kj5u - same-tax control for the NI-GB
          market-structure gap); EVENTS register rendered as chart
          annotations; FEED_FLAGS register for value-level caveats distinct
          from fetch status; tariff anchors re-based on the July 2026
          sourced pass (Power NI/UR review, ROI standard rates);
          derive_heat_gap() - cost of useful heat by route per jurisdiction
          with break-even SPF vs the incumbent oil boiler.
  0.4.0 - oil bulletin fetches with- AND without-taxes files; ex-tax series.
  0.3.0 - gni_live implemented against the probed gasconsumption JSON API.
  0.2.0 - ANCHORS + derive_hero() weekly four-stat and geothermal what-if.
  0.1.x - scaffold, feed fixes from first-run logs.

House rules: self-resolve IDs/links at runtime; dump available names on
failure; every feed try/except with previous values retained and status
"stale"; fetch health vs data recency tracked separately; unit
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

PIPELINE_VERSION = "0.5.0"
ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "docs" / "data.json"
SERIES_KEEP_DAYS = 400
UA = {"User-Agent": "ioi-heatsplit/0.5 (contact@causewaygt.com)"}
TIMEOUT = 90
RETRIES = 3

# Feeds known broken for reasons outside this pipeline - marked stale,
# logged, but neither paged nor allowed to fail the run.
EXPECTED_DOWN = {
    "eirgrid": ("Smart Grid Dashboard redesigned ~09 Jul 2026 - "
                "DashboardService.svc returns 503 from all networks; "
                "awaiting browser XHR probe for the replacement endpoint"),
}

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

# Fill after browser XHR probe (the one remaining probe)
EIRGRID_ENDPOINT = None    # replacement for DashboardService.svc/data

NTFY_TOPIC = None

# Set by main() before the feed loop - lets feeds merge history across runs
PREVIOUS_FEEDS: dict = {}

# ------------------------------------------------- annual anchors
# Sourced figures cite their publication; every judgement figure is marked
# with a dagger and is a current Causeway Energies estimate - challenge and
# input welcome at contact@causewaygt.com.

ANCHORS = {
    "year": 2024,
    "roi": {
        "residential_heat_twh": 22.3,      # SEAI Energy in Ireland 2025
        "services_heat_twh": 8.5,          # dagger - from SEAI sector shares
        "fuel_shares": {"oil": 0.565, "gas": 0.251, "peat": 0.067,
                        "electricity": 0.08, "other": 0.037},
        #             oil/gas/peat SEAI 2024; electricity/other dagger
        "gas_indigenous": 0.18,            # SEAI H1-2025, Corrib, falling
        "elec_indigenous": 0.413,          # SEAI RES-E 2024
    },
    "ni": {
        "residential_heat_twh": 10.0,      # dagger - NISRA stock x intensity
        "services_heat_twh": 3.0,          # dagger
        "fuel_shares": {"oil": 0.62, "gas": 0.26, "peat": 0.0,
                        "electricity": 0.08, "other": 0.04},
        #             oil NISRA CHS 2024/25; gas/electricity/other dagger
        "gas_indigenous": 0.0,             # all NI gas arrives via Moffat
        "elec_indigenous": 0.46,           # dagger - DfE yr-to-Mar-2026 ~48%
    },
    "efficiency": {"oil": 0.82, "gas": 0.85, "peat": 0.60,
                   "electricity": 1.0, "other": 0.70},          # dagger
    "geothermal_spf": 4.0,                                       # dagger
    "ef_g_per_kwh": {"oil": 257, "gas": 205, "peat": 340,
                     "other": 100, "electricity": 280},          # dagger -
    # electricity factor replaced by live grid intensity once eirgrid returns
    "indigenous": {"oil": 0.0, "peat": 1.0, "other": 0.9},      # dagger
    "space_heat_fraction": 0.72,                                 # dagger
    "kerosene_kwh_per_litre": 10.35,   # industry standard figure
    # Tariff anchors, July 2026 pass. Sourced bands, dagger on the point:
    #  ROI electricity: standard 24h ~35c (Electric Ireland, May 2026);
    #    Eurostat H2-2025 all-in ~40c; anchor 36c.
    #  ROI gas: standard unit ~11-12c incl 9% VAT; anchor 11.5c.
    #  NI electricity: Power NI 1 Jul 2026 review - GBP1,093/yr at 3,200 kWh
    #    -> ~32.5p unit ex-standing; anchor 32.5p.
    #  NI gas: Ten Towns GBP972/yr at 12,000 kWh (1 Jul 2026) -> ~7.5p unit.
    # Standard-tariff basis - time-of-use/night rates materially lower for
    # heat-pump households; see heat_gap basis note.
    "retail_eur_per_kwh": {"gas": 0.115, "electricity": 0.36},
    "retail_gbp_per_kwh": {"gas": 0.075, "electricity": 0.325},
}

# Policy events rendered as chart annotations - date, jurisdiction, label.
EVENTS = [
    {"date": "2025-10-08", "jur": "ROI",
     "label": "Carbon tax to \u20ac71/t \u2013 motor fuels"},
    {"date": "2026-03-16", "jur": "UK",
     "label": "UK \u00a350m oil support; CMA review"},
    {"date": "2026-04-01", "jur": "ROI",
     "label": "NORA levy paused (two months)"},
    {"date": "2026-05-01", "jur": "ROI",
     "label": "Heating-fuel carbon increase postponed"},
    {"date": "2026-10-14", "jur": "ROI",
     "label": "Carbon tax \u20ac63.50\u2192\u20ac71/t \u2013 heating fuels (due)"},
]

# Value-level caveats, distinct from fetch status - machine-carried nuance.
FEED_FLAGS = {
    "ccni_oil": ["Verification pending that parsed values are the NI "
                 "average series, not a council-area series"],
    "oil_bulletin": ["Bulletin heading is gas oil; treated as ROI "
                     "heating-oil (kerosene) price level - Causeway "
                     "judgement"],
    "hdd": ["Population weights are Causeway estimates"],
    "ons_gb_oil": ["Monthly official series - lags the daily NI survey by "
                   "design; unit basis autodetected"],
}


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
        except requests.RequestException as e:
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


def find_date_in_text(s: str) -> str | None:
    """dd/mm/yyyy anywhere inside a longer string (bulletin title cells)."""
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if not m:
        return None
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"


def prev_series(feed: str, *keys) -> dict:
    """Previously stored series for cross-run history accumulation."""
    node = PREVIOUS_FEEDS.get(feed, {})
    for k in keys:
        node = node.get(k, {}) if isinstance(node, dict) else {}
    return dict(node) if isinstance(node, dict) else {}


def _num(s) -> float | None:
    """Parse a number that may use a decimal comma (SEMOpx CSV convention)."""
    try:
        return float(str(s).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------- pure parsers (unit tested)

def extract_chart_data_arrays(page_html: str) -> list:
    """Bracket-matched '"data":[[...]]' chart payloads, entity-unescaped."""
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
    """{"300l": {iso: gbp}, ...} from litre-labelled embedded charts."""
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


def resolve_oil_bulletin_url(page_html: str, with_tax: bool = True) -> str | None:
    """Weekly prices xlsx, with or without taxes - unquote before matching."""
    for m in re.finditer(r'href="([^"]+)"', page_html):
        u = m.group(1)
        decoded = urllib.parse.unquote(u).lower()
        if ".xlsx" not in decoded:
            continue
        has_without = "without" in decoded
        has_with = re.search(r"with[ _]tax", decoded) is not None
        hit = (has_with and not has_without) if with_tax \
            else (has_without and "tax" in decoded)
        if hit:
            return u if u.startswith("http") else "https://energy.ec.europa.eu" + u
    return None


def parse_bulletin_rows(rows) -> tuple:
    """
    One-week-snapshot layout confirmed live (14 Jul 2026): a title cell
    carries the bulletin date; a header row names products ('...Heating...'
    at some column); country rows carry values with no per-row dates.
    Returns (iso_date | None, ireland_heating_value | None).
    Tolerates per-row dates too, should the layout ever grow them.
    """
    bulletin_date, idx_heat, value = None, None, None
    for row in rows:
        cells = list(row)
        strs = [str(c) if c is not None else "" for c in cells]
        joined = " ".join(strs).lower()

        if bulletin_date is None:
            for c in cells:
                if isinstance(c, dt.datetime):
                    bulletin_date = c.date().isoformat()
                    break
                if isinstance(c, dt.date):
                    bulletin_date = c.isoformat()
                    break
                iso = find_date_in_text(str(c)) if c is not None else None
                if iso:
                    bulletin_date = iso
                    break

        if idx_heat is None and ("heating" in joined or "chauffage" in joined):
            for i, c in enumerate(strs):
                if "heating" in c.lower() or "chauffage" in c.lower():
                    idx_heat = i
                    break
            continue

        if idx_heat is not None and value is None and (
                "ireland" in joined
                or (strs and strs[0].strip().upper() in ("IE", "EI"))):
            row_date = None
            for c in cells:
                if isinstance(c, (dt.datetime, dt.date)):
                    row_date = (c.date() if isinstance(c, dt.datetime)
                                else c).isoformat()
                    break
            try:
                v = float(cells[idx_heat])
            except (TypeError, ValueError, IndexError):
                continue
            value = round(v, 2)
            if row_date:
                bulletin_date = row_date
    return bulletin_date, value


def parse_semopx_csv(text: str) -> dict:
    """
    SEMOpx MarketResult CSV, format confirmed live (14 Jul 2026):
    semicolon-delimited, decimal commas, sections -
        Auction;SEM-DA
        FX rates
        EUR;GBP;0,85506627
        Market;NI-DA
        Index prices;30;EUR
        <row of ISO delivery timestamps>
        <row of prices>
    Returns {"fx_eur_gbp", "day", "auction", "markets"}.
    """
    fx, day, auction = None, None, None
    markets: dict = {}
    market, currency, expect_series = None, None, False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(";")]
        key = parts[0].lower()

        if key == "auction" and len(parts) > 1:
            auction = parts[1]
            continue
        if key == "market" and len(parts) > 1:
            market = parts[1]
            expect_series = False
            continue
        if key.startswith("index prices"):
            currency = parts[-1].upper() if len(parts) >= 2 else "EUR"
            expect_series = True
            continue
        if key == "eur" and len(parts) >= 3 and parts[1].upper() == "GBP":
            fx = _num(parts[2])
            continue
        if expect_series:
            if re.match(r"20\d\d-\d\d-\d\dT", parts[0]):
                if day is None:
                    day = parts[0][:10]
                continue
            nums = [n for n in (_num(p) for p in parts) if n is not None]
            if nums and market and currency:
                markets.setdefault(market, {}).setdefault(
                    currency, []).extend(nums)
                expect_series = False
    return {"fx_eur_gbp": fx, "day": day, "auction": auction,
            "markets": markets}


def parse_gni_series(series_list) -> dict:
    """
    Pure parser for the GNI gasconsumption JSON API. Input: list of series
    objects {name, location, group, ..., data: [[unix_ms, value], ...]}.
    Output: {location: {iso_date: value}}. Keys off `location`, tolerates
    missing fields, skips unparseable points.
    """
    out = {}
    for s in series_list or []:
        loc = (s or {}).get("location")
        if not loc:
            continue
        pts = {}
        for pair in s.get("data") or []:
            try:
                ms, val = pair[0], pair[1]
                d = dt.datetime.fromtimestamp(
                    ms / 1000.0, tz=dt.timezone.utc).date().isoformat()
                pts[d] = float(val)
            except (TypeError, ValueError, IndexError, OSError):
                continue
        if pts:
            out.setdefault(loc, {}).update(pts)
    return out


# ---------------------------------------------------------------- feeds

def feed_eirgrid():
    """
    Smart Grid Dashboard - PROBE PENDING. The pre-redesign endpoint
    (DashboardService.svc/data) returns 503 from all networks since
    ~09 Jul 2026. Set EIRGRID_ENDPOINT after the browser XHR probe and
    implement the parser against the captured response shape.
    """
    if EIRGRID_ENDPOINT is None:
        raise NotImplementedError(EXPECTED_DOWN["eirgrid"])
    raise NotImplementedError("endpoint probed? implement the parser here")


def feed_hdd():
    """Open-Meteo, batched; forecast tail optional (degrades to lagging)."""
    names = list(STATIONS)
    lats = ",".join(str(STATIONS[n][0]) for n in names)
    lons = ",".join(str(STATIONS[n][1]) for n in names)

    def unpack(payload):
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
    """data.gov.ie CKAN - GNI daily demand by sector, CC BY 4.0, quarterly."""
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
        "dm": None,
        "ldm": col("ldm"),
        "power": col("power"),
        "total_roi": col("total"),
    }
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
    """
    GNI Data Transparency JSON API - probed 14 Jul 2026, daily/hourly/
    monthly all 200. The CSV export route 503s and is not used. Window per
    call unknown: anchor four dates a month apart, log the observed span,
    merge across runs. Values arrive in kWh by default - unit autodetected.
    JURISDICTION FLAG: DM/NDM carry no ROI prefix while LDM and Power Gen
    do - whether unprefixed series include NI exits is unconfirmed; the
    space-heat regression stays on the confirmed-ROI gni_ckan series until
    resolved.
    """
    base = "https://www.gasnetworks.ie/api/v1/gasconsumption"
    raw = {}
    for back in (0, 30, 60, 90):
        anchor = (today_utc() - dt.timedelta(days=back)).isoformat()
        try:
            body = http_get(base, params={
                "date": anchor, "frequency": "daily", "unit": ""}).json()
        except Exception as e:
            log(f"gni_live: anchor {anchor} failed - {e.__class__.__name__}: {e}")
            continue
        if not isinstance(body, list):
            log("gni_live: unexpected shape for", anchor, "-", str(body)[:300])
            continue
        parsed = parse_gni_series(body)
        if back == 0:
            log("gni_live: locations seen:", sorted(parsed))
        for loc, pts in parsed.items():
            raw.setdefault(loc, {}).update(pts)
    if not raw:
        raise ValueError("gni_live: no series parsed from any anchor")

    spans = {loc: (min(p), max(p), len(p)) for loc, p in raw.items()}
    log("gni_live: spans:", spans)

    ndm_vals = list(raw.get("NDM", {}).values())
    scale, unit_note = autodetect_scale_to_gwh(
        ndm_vals or [v for p in raw.values() for v in p.values()])

    def keyname(loc):
        return loc.lower().replace(" ", "_")

    out = {"unit_detection": unit_note,
           "jurisdiction_note": ("DM/NDM carry no ROI prefix while LDM and "
                                 "Power Gen do - whether unprefixed series "
                                 "include NI exits is unconfirmed; regression "
                                 "remains on the confirmed-ROI calibration "
                                 "series until resolved"),
           "source": ("Gas Networks Ireland Data Transparency - "
                      "gasconsumption API, daily by market sector")}
    latest = None
    for loc, pts in raw.items():
        merged = prev_series("gni_live", f"{keyname(loc)}_gwh")
        merged.update({d: round(v * scale, 3) for d, v in pts.items()})
        merged = trim_series(clip_days(merged))
        out[f"{keyname(loc)}_gwh"] = merged
        if merged:
            latest = max(latest or "", max(merged))
    out["latest_day"] = latest
    return out, recency_status(latest, 3)


def feed_semopx():
    """
    SEMOpx DAM results. DPuG_ID=EA-001 listing confirmed live but mixes DA
    with IDA1/2/3 - select _SEM-DA_ resources explicitly, widening the page
    if the first window holds none. Document is semicolon-CSV with decimal
    commas - see parse_semopx_csv().
    """
    base = "https://reports.semopx.com/api/v1/documents/static-reports"

    def da_items(items):
        return [it for it in items
                if re.search(r"_SEM-DA_", str(it.get("ResourceName") or ""))]

    chosen = None
    for page_size in (20, 100):
        items = http_get(base, params={
            "DPuG_ID": "EA-001", "page_size": page_size,
            "sort_by": "Date", "order_by": "DESC"}).json().get("items", [])
        hits = da_items(items)
        tags = sorted({m.group(0) for it in items
                       for m in [re.search(r"SEM-[A-Z0-9]+",
                                           str(it.get("ResourceName") or ""))]
                       if m})
        log(f"semopx: page_size {page_size} - {len(items)} items, "
            f"{len(hits)} DA, auction tags seen: {tags}")
        if hits:
            chosen = hits[0]
            break
    if not chosen:
        raise ValueError("semopx: no _SEM-DA_ resource in EA-001 listing")

    resource = chosen.get("ResourceName") or chosen.get("_id")
    log("semopx: resolved", resource)
    body = http_get(f"https://reports.semopx.com/documents/{resource}")
    parsed = parse_semopx_csv(body.text)

    if not parsed["markets"]:
        log("semopx: CSV parse empty - first 800 chars:", body.text[:800])
        raise ValueError("semopx CSV parse failed - inspect log")

    def avg(currency):
        vals = [v for mk, cur in parsed["markets"].items()
                for c, series in cur.items() if c == currency
                for v in series]
        return round(statistics.mean(vals), 2) if vals else None

    out = {
        "dam_avg_eur_mwh": avg("EUR"),
        "dam_avg_gbp_mwh": avg("GBP"),
        "markets": {mk: {c: round(statistics.mean(v), 2)
                         for c, v in cur.items() if v}
                    for mk, cur in parsed["markets"].items()},
        "sem_fx_eur_gbp": parsed["fx_eur_gbp"],
        "auction": parsed["auction"],
        "trade_day": parsed["day"], "latest_day": parsed["day"],
        "source": ("SEMOpx day-ahead market results - dual currency "
                   "(EUR/GBP), incl. SEM trading-day FX rate"),
    }
    log("semopx: markets parsed:", list(parsed["markets"]))
    return out, recency_status(parsed["day"], 4)


def feed_oil_bulletin():
    """
    EU Weekly Oil Bulletin - Ireland heating gas oil, EUR/1000 L, with AND
    without taxes. Snapshot files; history accumulates in data.json across
    runs. Both sides of the border burn the same C2 kerosene; the series is
    treated as the ROI heating-oil price level (see FEED_FLAGS).
    """
    page = http_get(
        "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
    ).text

    import openpyxl

    def fetch_ireland(with_tax):
        url = resolve_oil_bulletin_url(page, with_tax=with_tax)
        if not url:
            seen = [urllib.parse.unquote(u)[:110] for u in
                    re.findall(r'href="([^"]+)"', page)
                    if ".xlsx" in urllib.parse.unquote(u).lower()]
            log(f"oil_bulletin: no '{'with' if with_tax else 'without'} "
                "taxes' xlsx resolved - decoded links:", seen)
            return None, None
        log("oil_bulletin: resolved", urllib.parse.unquote(url)[:120])
        wb = openpyxl.load_workbook(
            io.BytesIO(http_get(url, timeout=180).content),
            read_only=True, data_only=True)
        for ws in wb.worksheets:
            d, v = parse_bulletin_rows(ws.iter_rows(values_only=True))
            if v is not None:
                return d, v
        for ws in wb.worksheets:
            head = [r for _, r in zip(range(6), ws.iter_rows(values_only=True))]
            log(f"oil_bulletin: sheet '{ws.title}' first rows:", head)
        return None, None

    d_wt, v_wt = fetch_ireland(True)
    d_nt, v_nt = fetch_ireland(False)
    if v_wt is None:
        raise ValueError("oil bulletin with-taxes parse failed - see log")
    for label, v in (("with", v_wt), ("without", v_nt)):
        if v is not None and not 300 <= v <= 3000:
            log(f"oil_bulletin: WARNING - {label}-taxes {v} EUR/1000L "
                "outside plausible range, check column selection")
    if d_wt is None:
        log("oil_bulletin: no bulletin date found - using today, verify")
        d_wt = today_utc().isoformat()
    log(f"oil_bulletin: Ireland heating {v_wt} EUR/1000L with taxes, "
        f"{v_nt} without, at {d_wt}")

    series = prev_series("oil_bulletin", "roi_heating_gasoil_eur_per_1000l")
    series[d_wt] = v_wt
    series = trim_series(clip_days(series))
    series_nt = prev_series("oil_bulletin",
                            "roi_heating_gasoil_eur_per_1000l_ex_tax")
    if v_nt is not None:
        series_nt[d_nt or d_wt] = v_nt
    series_nt = trim_series(clip_days(series_nt))
    out = {
        "roi_heating_gasoil_eur_per_1000l": series,
        "roi_heating_gasoil_eur_per_1000l_ex_tax": series_nt,
        "latest_value": v_wt,
        "latest_value_ex_tax": v_nt,
        "latest_day": max(series),
        "source": ("European Commission Weekly Oil Bulletin - prices with "
                   "and without taxes"),
    }
    return out, recency_status(out["latest_day"], 10)


def feed_ccni_oil():
    """
    Consumer Council NI - daily checker page (weekly page confirmed
    chart-free). Parsed series merges with previous runs so history extends
    beyond the page's rolling window. See FEED_FLAGS for the average-vs-
    council-area verification item.
    """
    url = "https://www.consumercouncil.org.uk/home-heating/price-checker/daily"
    page = http_get(url).text
    parsed = parse_ccni_series(page)
    n = sum(len(v) for v in parsed.values())
    if not n:
        arrays = extract_chart_data_arrays(page)
        log("ccni_oil: no litre-labelled chart; "
            f"{len(arrays)} chart array(s) found, first headers:",
            [a[0] for a in arrays[:3] if a])
        raise ValueError("ccni_oil: no series parsed - inspect log")
    log(f"ccni_oil: {n} datapoints across "
        f"{[k for k, v in parsed.items() if v]}")

    merged = {}
    for k, new in parsed.items():
        old = prev_series("ccni_oil", "series_gbp", "daily", k)
        old.update(new)
        merged[k] = trim_series(clip_days(old))
    out = {"series_gbp": {"daily": merged}}

    all_days = [d for s in merged.values() for d in s]
    out["latest_day"] = max(all_days) if all_days else None
    out["source"] = ("Consumer Council for Northern Ireland home heating oil "
                     "price checker - daily (Mon-Fri), NI average, "
                     "300/500/900 L")
    return out, recency_status(out["latest_day"], 7)


def feed_ons_gb_oil():
    """
    ONS average heating oil price, GB context line - series kj5u
    (RPI: ave price, heating oil per 1000 litres), keyless JSON. Monthly.
    Same tax regime as NI: the NI-GB gap isolates market structure.
    """
    j = http_get("https://www.ons.gov.uk/economy/inflationandpriceindices/"
                 "timeseries/kj5u/mm23/data").json()
    months = j.get("months", [])
    if not months:
        log("ons_gb_oil: no months in response - keys:", list(j)[:15])
        raise ValueError("ons_gb_oil: unexpected response shape")
    mon = {"JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5,
           "JUNE": 6, "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10,
           "NOVEMBER": 11, "DECEMBER": 12}
    raw = {}
    for m in months:
        try:
            y, name = m["date"].split()
            d = f"{int(y):04d}-{mon[name.upper()]:02d}-01"
            raw[d] = float(m["value"])
        except (KeyError, ValueError):
            continue
    if not raw:
        raise ValueError("ons_gb_oil: no parseable months")
    med = statistics.median(raw.values())
    # per-1000L in pence vs pounds vs already p/L: autodetect
    if med > 2000:
        scale, unit_note = 0.001, "p/1000L->p/L"
    elif med > 200:
        scale, unit_note = 0.1, "GBP/1000L->p/L"
    else:
        scale, unit_note = 1.0, "p/L"
    series = trim_series(clip_days(
        {d: round(v * scale, 2) for d, v in raw.items()}))
    latest = max(series) if series else None
    out = {"gb_ppl_monthly": series, "unit_detection": unit_note,
           "latest_day": latest,
           "source": ("ONS average heating oil price, GB (series kj5u) - "
                      "monthly, same tax regime as NI")}
    return out, recency_status(latest, 62)


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


def derive_hero(feeds, anchors=None):
    """
    Weekly hero four-stat + what-if, all-island, twin currencies.
    Scaffold estimator: annual buildings-heat anchors shaped by the week's
    island HDD (space-heat fraction HDD-proportional, remainder flat).
    Pure function - unit tested. Returns None until HDD data is present.
    """
    a = anchors or ANCHORS
    hdd = (feeds.get("hdd") or {}).get("hdd_island") or {}
    if len(hdd) < 200:
        return None
    days = sorted(hdd)
    week_days = days[-7:]
    hdd_week = sum(hdd[d] for d in week_days)
    hdd_year = sum(hdd[d] for d in days[-365:])
    if hdd_year <= 0:
        return None
    shf = a["space_heat_fraction"]

    fx = (feeds.get("ecb_fx") or {}).get("eur_gbp")  # GBP per EUR
    fx = fx or 0.855

    oil_eur_kwh = None
    ob = (feeds.get("oil_bulletin") or {}).get("latest_value")
    if ob:
        oil_eur_kwh = ob / 1000.0 / a["kerosene_kwh_per_litre"]
    oil_gbp_kwh = None
    ccni = ((feeds.get("ccni_oil") or {}).get("series_gbp") or {}).get(
        "daily", {}).get("900l") or {}
    if ccni:
        oil_gbp_kwh = ccni[max(ccni)] / 900.0 / a["kerosene_kwh_per_litre"]

    def week_input_gwh(annual_twh):
        annual_gwh = annual_twh * 1000.0
        return annual_gwh * ((1 - shf) / 52.0 + shf * hdd_week / hdd_year)

    totals = {"input_gwh": 0.0, "useful_gwh": 0.0, "indig_gwh": 0.0,
              "kt_co2": 0.0, "bill_eur_m": 0.0, "bill_gbp_m": 0.0}
    for jur, cur in (("roi", "eur"), ("ni", "gbp")):
        j = a[jur]
        heat_twh = j["residential_heat_twh"] + j["services_heat_twh"]
        for fuel, share in j["fuel_shares"].items():
            inp = week_input_gwh(heat_twh) * share
            eff = a["efficiency"][fuel]
            useful = inp * eff
            indig = useful * (
                j["gas_indigenous"] if fuel == "gas" else
                j["elec_indigenous"] if fuel == "electricity" else
                a["indigenous"].get(fuel, 0.0))
            # GWh x g/kWh -> tonnes; /1000 -> kt
            kt = inp * a["ef_g_per_kwh"][fuel] / 1000.0
            if fuel == "oil":
                price = oil_eur_kwh if cur == "eur" else oil_gbp_kwh
                if price is None:
                    price = 0.11 if cur == "eur" else 0.09  # dagger fallback
            else:
                table = a["retail_eur_per_kwh"] if cur == "eur" \
                    else a["retail_gbp_per_kwh"]
                price = table.get(fuel, table["gas"])
            bill_m = inp * 1e6 * price / 1e6  # GWh->kWh, price/kWh, ->millions
            totals["input_gwh"] += inp
            totals["useful_gwh"] += useful
            totals["indig_gwh"] += indig
            totals["kt_co2"] += kt
            if cur == "eur":
                totals["bill_eur_m"] += bill_m
            else:
                totals["bill_gbp_m"] += bill_m

    bill_eur_total = totals["bill_eur_m"] + totals["bill_gbp_m"] / fx
    bill_gbp_total = totals["bill_eur_m"] * fx + totals["bill_gbp_m"]

    spf = a["geothermal_spf"]
    moved_useful = totals["useful_gwh"] * 0.20
    elec_in = moved_useful / spf
    ambient = moved_useful - elec_in
    scale = 0.80
    wf_input = totals["input_gwh"] * scale + elec_in
    wf_indig = (totals["indig_gwh"] * scale + ambient
                + elec_in * (a["roi"]["elec_indigenous"] * 0.7
                             + a["ni"]["elec_indigenous"] * 0.3))
    wf_kt = totals["kt_co2"] * scale + elec_in * \
        a["ef_g_per_kwh"]["electricity"] / 1000.0
    blend_eur = a["retail_eur_per_kwh"]["electricity"]
    blend_gbp = a["retail_gbp_per_kwh"]["electricity"]
    wf_bill_eur = bill_eur_total * scale + elec_in * 1e3 * blend_eur / 1e3 * 0.7 \
        + (elec_in * 1e3 * blend_gbp / 1e3 * 0.3) / fx
    wf_bill_gbp = wf_bill_eur * fx

    r1 = lambda x: round(x, 1)
    return {
        "week_ending": week_days[-1],
        "hdd_week": r1(hdd_week), "hdd_year": r1(hdd_year),
        "heat_purchased_gwh": r1(totals["input_gwh"]),
        "heat_delivered_gwh": r1(totals["useful_gwh"]),
        "indigenous_share_pct": r1(100 * totals["indig_gwh"]
                                   / max(totals["useful_gwh"], 1e-9)),
        "bill_eur_m": r1(bill_eur_total), "bill_gbp_m": r1(bill_gbp_total),
        "emissions_kt_co2": r1(totals["kt_co2"]),
        "what_if_20pct_geothermal": {
            "heat_purchased_gwh": r1(wf_input),
            "indigenous_share_pct": r1(100 * wf_indig
                                       / max(totals["useful_gwh"], 1e-9)),
            "bill_eur_m": r1(wf_bill_eur), "bill_gbp_m": r1(wf_bill_gbp),
            "emissions_kt_co2": r1(wf_kt),
            "geothermal_spf": spf,
        },
        "basis": ("Scaffold estimator (dagger throughout) - annual anchors "
                  "shaped by the week's island HDD; SEAI 2024, DfE/NISRA, "
                  "Causeway estimates. Challenge and input welcome at "
                  "contact@causewaygt.com"),
        "anchors_used": a,
    }


def derive_heat_gap(feeds, anchors=None):
    """
    Cost of useful heat by route, per jurisdiction, standard tariffs -
    plus the break-even SPF against the incumbent oil boiler. Pure,
    unit tested. Native currency minor units (p or c) per useful kWh.
    """
    a = anchors or ANCHORS
    fx = (feeds.get("ecb_fx") or {}).get("eur_gbp") or 0.855

    ccni = ((feeds.get("ccni_oil") or {}).get("series_gbp") or {}).get(
        "daily", {}).get("900l") or {}
    oil_ni_ppl = ccni[max(ccni)] * 100 / 900 if ccni else None
    ob = (feeds.get("oil_bulletin") or {}).get("latest_value")
    oil_roi_cpl = ob * 100 / 1000 if ob else None
    kwh_l = a["kerosene_kwh_per_litre"]
    eff_oil, eff_gas = a["efficiency"]["oil"], a["efficiency"]["gas"]
    spf_hp, spf_geo = 3.2, a["geothermal_spf"]

    def jur(oil_pl, elec, gas):
        if oil_pl is None:
            return None
        oil_useful = oil_pl / kwh_l / eff_oil
        r2 = lambda x: round(x, 2)
        return {
            "oil_boiler": r2(oil_useful),
            "gas_boiler": r2(gas * 100 / eff_gas),
            "heat_pump_spf32": r2(elec * 100 / spf_hp),
            "geothermal_spf40": r2(elec * 100 / spf_geo),
            "breakeven_spf_vs_oil": r2(elec * 100 / oil_useful),
            "breakeven_spf_vs_gas": r2(elec * 100 / (gas * 100 / eff_gas)),
            "inputs": {"oil_per_litre": round(oil_pl, 2),
                       "electricity_per_kwh": elec, "gas_per_kwh": gas},
        }

    ni = jur(oil_ni_ppl, a["retail_gbp_per_kwh"]["electricity"],
             a["retail_gbp_per_kwh"]["gas"])
    roi = jur(oil_roi_cpl, a["retail_eur_per_kwh"]["electricity"],
              a["retail_eur_per_kwh"]["gas"])
    if not (ni and roi):
        return None
    return {
        "ni": ni, "roi": roi, "fx_eur_gbp": fx,
        "hp_spf": spf_hp, "geo_spf": spf_geo,
        "basis": ("Standard tariffs, July 2026 pass (Power NI/UR review, "
                  "ROI standard 24h rates) - dagger; time-of-use and night "
                  "tariffs materially lower for heat-pump households. Oil "
                  "prices live. Kerosene 10.35 kWh/L; boiler efficiencies "
                  "82%/85% dagger. Challenge and input welcome at "
                  "contact@causewaygt.com"),
    }


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
    "ons_gb_oil": feed_ons_gb_oil,
}


def main():
    global PREVIOUS_FEEDS
    if DATA_PATH.exists():
        try:
            PREVIOUS_FEEDS = json.loads(DATA_PATH.read_text()).get("feeds", {})
        except Exception:
            log("warning - previous data.json unreadable, starting clean")

    feeds, failures = {}, []
    for name, fn in FEEDS.items():
        log(f"--- {name}")
        try:
            payload, status = fn()
            payload["status"] = status
            if name in FEED_FLAGS:
                payload["flags"] = FEED_FLAGS[name]
            payload["fetched_utc"] = dt.datetime.now(
                dt.timezone.utc).isoformat(timespec="seconds")
            feeds[name] = payload
            log(f"{name}: {status}, latest_day={payload.get('latest_day')}")
        except Exception as e:
            expected = isinstance(e, NotImplementedError) or name in EXPECTED_DOWN
            log(f"{name}: {'EXPECTED DOWN' if expected else 'FAILED'} - "
                f"{e.__class__.__name__}: {e}")
            if not expected:
                traceback.print_exc()
            prev = PREVIOUS_FEEDS.get(name, {})
            prev["status"] = "stale"
            if name in EXPECTED_DOWN:
                prev["pending_note"] = EXPECTED_DOWN[name]
            if name in FEED_FLAGS:
                prev["flags"] = FEED_FLAGS[name]
            prev.setdefault("source", "previous run retained")
            feeds[name] = prev
            if not expected:
                failures.append(name)

    gas = feeds.get("gni_ckan", {}).get("ndm_gwh") or {}
    hdd = feeds.get("hdd", {}).get("hdd_roi") or {}
    reg = space_heat_split(gas, hdd)
    derived = {"roi_space_heat_regression": reg} if reg else {}
    if reg:
        log("regression:", reg)
    hero = derive_hero(feeds)
    if hero:
        derived["hero"] = hero
        log("hero:", {k: hero[k] for k in
                      ("week_ending", "heat_purchased_gwh",
                       "indigenous_share_pct", "bill_eur_m", "bill_gbp_m",
                       "emissions_kt_co2")})
    hg = derive_heat_gap(feeds)
    if hg:
        derived["heat_gap"] = hg
        log("heat_gap: breakeven SPF vs oil - NI",
            hg["ni"]["breakeven_spf_vs_oil"], "ROI",
            hg["roi"]["breakeven_spf_vs_oil"])

    doc = {
        "pipeline_version": PIPELINE_VERSION,
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "feeds": feeds,
        "derived": derived,
        "events": EVENTS,
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
