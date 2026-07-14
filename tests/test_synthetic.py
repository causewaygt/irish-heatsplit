"""
Synthetic tests for ioi-heatsplit pipeline logic - run before shipping,
per house rule: validate estimators and parsers against synthetic data,
including injected confounds and the actual formats captured in the
first Actions run log (14 Jul 2026).

    python3 tests/test_synthetic.py
"""

import datetime as dt
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build import (space_heat_split, autodetect_scale_to_gwh,   # noqa: E402
                   clip_days, recency_status, ddmmyyyy_to_iso,
                   extract_chart_data_arrays, parse_ccni_series,
                   resolve_oil_bulletin_url)


# ------------------------------------------------------------- regression

def synth_year(slope=3.0, baseload=8.0, noise=0.5, seed=1):
    rng = random.Random(seed)
    gas, hdd = {}, {}
    d0 = dt.date(2025, 1, 1)
    for i in range(365):
        d = (d0 + dt.timedelta(days=i)).isoformat()
        doy = i / 365 * 2 * math.pi
        h = max(0.0, 8.0 + 6.0 * math.cos(doy) + rng.gauss(0, 1))
        hdd[d] = round(h, 2)
        gas[d] = round(baseload + slope * h + rng.gauss(0, noise), 2)
    return gas, hdd


def test_regression_recovers_truth():
    gas, hdd = synth_year(slope=3.0, baseload=8.0)
    r = space_heat_split(gas, hdd)
    assert r is not None
    assert abs(r["slope_gwh_per_hdd"] - 3.0) < 0.1, r
    assert abs(r["baseload_gwh_per_day"] - 8.0) < 1.0, r
    assert r["r2"] > 0.95, r


def test_regression_with_holiday_confound():
    """Late-December demand drop at high HDD - slope bias must stay bounded."""
    gas, hdd = synth_year(slope=3.0, baseload=8.0, noise=0.2)
    for i in range(20, 32):
        d = dt.date(2025, 12, i % 31 + 1).isoformat()
        if d in gas:
            gas[d] = round(gas[d] * 0.7, 2)
    r = space_heat_split(gas, hdd)
    assert r is not None
    assert abs(r["slope_gwh_per_hdd"] - 3.0) < 0.3, (
        "confound bias exceeds tolerance - month-demean before regression", r)


# ------------------------------------------------------------- utilities

def test_unit_autodetect():
    assert autodetect_scale_to_gwh([5e7, 6e7])[1] == "kWh->GWh"
    assert autodetect_scale_to_gwh([5e4, 6e4])[1] == "MWh->GWh"
    assert autodetect_scale_to_gwh([25.0, 40.0])[1] == "GWh"


def test_clip_future_rows():
    today = dt.date.today()
    d = {(today + dt.timedelta(days=k)).isoformat(): 1.0 for k in (-2, -1, 0, 1, 2)}
    kept = clip_days(d)
    assert (today + dt.timedelta(days=1)).isoformat() not in kept
    assert today.isoformat() in kept


def test_recency_states():
    today = dt.date.today().isoformat()
    old = (dt.date.today() - dt.timedelta(days=40)).isoformat()
    assert recency_status(today, 3) == "ok"
    assert recency_status(old, 3) == "lagging"
    assert recency_status(None, 3) == "stale"


def test_ddmmyyyy():
    assert ddmmyyyy_to_iso("26/02/2026") == "2026-02-26"
    assert ddmmyyyy_to_iso("2/3/2026") == "2026-03-02"
    assert ddmmyyyy_to_iso("not a date") is None


# ---------------------------------------------- ccni parser - live format

# Verbatim structure from the first-run diagnostic dump (14 Jul 2026),
# HTML-entity-escaped chart config embedded in the daily checker page.
CCNI_SAMPLE = (
    'prefix junk {&quot;color&quot;:&quot;#579b17&quot;,&quot;_format&quot;:'
    '{&quot;format&quot;:&quot;\\u00a3#&quot;}}]},'
    '&quot;data&quot;:[[&quot;&quot;,&quot;300 litres&quot;,'
    '&quot;500 litres&quot;,&quot;900 litres&quot;],'
    '[&quot;26/02/2026&quot;,202.12,307.38,536.72000000000003],'
    '[&quot;02/03/2026&quot;,271.50999999999999,416.25999999999999,'
    '723.48000000000002],'
    '[&quot;03/03/2026&quot;,309.45999999999998,481.50999999999999,'
    '831.03999999999996]] , trailing junk'
)


def test_ccni_chart_extraction():
    arrays = extract_chart_data_arrays(CCNI_SAMPLE)
    assert len(arrays) == 1, arrays
    assert arrays[0][0] == ["", "300 litres", "500 litres", "900 litres"]
    assert arrays[0][1][0] == "26/02/2026"


def test_ccni_series_parse():
    s = parse_ccni_series(CCNI_SAMPLE)
    assert s["300l"]["2026-02-26"] == 202.12
    assert s["500l"]["2026-03-02"] == 416.26
    assert s["900l"]["2026-03-03"] == 831.04
    assert len(s["300l"]) == 3


def test_ccni_ignores_non_litre_charts():
    other = ('&quot;data&quot;:[[&quot;&quot;,&quot;tariff&quot;],'
             '[&quot;01/01/2026&quot;,99.0]]')
    s = parse_ccni_series(other)
    assert not any(s.values())


# ------------------------------------- oil bulletin resolver - live format

# Verbatim link shapes from the first-run log (URL-encoded filenames).
BULLETIN_SAMPLE = (
    '<a href="/document/download/264c2d0f-f161-4ea3-a777-78faae59bea0_en'
    '?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices%20with%20Taxes'
    '%20-%202024-02-19.xlsx">x</a>'
    '<a href="/document/download/78311f92-68f8-4b82-b5cf-1293beeaae77_en'
    '?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices%20without%20taxes'
    '%20-%202024-02-19.xlsx">y</a>'
    '<a href="/document/download/ccdc6e96_en'
    '?filename=Oil_Bulletin_Duties_and_taxes.xlsx">z</a>'
)


def test_bulletin_resolves_with_taxes_only():
    url = resolve_oil_bulletin_url(BULLETIN_SAMPLE)
    assert url is not None
    assert "264c2d0f" in url, url               # the with-taxes UUID
    assert url.startswith("https://energy.ec.europa.eu/")


def test_bulletin_rejects_pageful_of_wrong_files():
    page = ('<a href="/document/download/x?filename=prices%20without%20taxes'
            '.xlsx">a</a><a href="/doc.pdf">b</a>')
    assert resolve_oil_bulletin_url(page) is None


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass - {fn.__name__}")
    print(f"{len(fns)} synthetic tests passed")
