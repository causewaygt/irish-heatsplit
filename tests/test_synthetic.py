"""
Synthetic tests for ioi-heatsplit pipeline logic - validated against
synthetic data with injected confounds AND verbatim formats captured in
the Actions run logs (14 Jul 2026).

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
                   resolve_oil_bulletin_url, parse_bulletin_rows,
                   parse_bulletin_history_rows,
                   parse_semopx_csv, parse_gni_series,
                   derive_hero, derive_heat_gap, derive_ashp_spf,
                   derive_cool, derive_geo_percap, WHY_HEAT,
                   derive_gas_calibration, odh26_from_hourly,
                   ANCHORS,
                   parse_gb_oil_page)


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
    assert r["method"].startswith("within-month centred")
    assert abs(r["slope_gwh_per_hdd"] - 3.0) < 0.1, r
    assert abs(r["baseload_gwh_per_day"] - 8.0) < 1.0, r
    assert r["r2_within_month"] > 0.9, r
    # residual SE close to the injected noise sigma
    assert 0.2 < r["residual_se_gwh_per_day"] < 1.2, r


def test_regression_with_holiday_confound():
    """Late-December demand drop at high HDD: the demeaned slope must hold
    tight where the naive slope may drift."""
    gas, hdd = synth_year(slope=3.0, baseload=8.0, noise=0.2)
    for i in range(20, 32):
        d = dt.date(2025, 12, i % 31 + 1).isoformat()
        if d in gas:
            gas[d] = round(gas[d] * 0.7, 2)
    r = space_heat_split(gas, hdd)
    assert r is not None
    assert abs(r["slope_gwh_per_hdd"] - 3.0) < 0.12, r
    assert r["naive_slope_gwh_per_hdd"] is not None


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


def test_ccni_series_parse():
    s = parse_ccni_series(CCNI_SAMPLE)
    assert s["300l"]["2026-02-26"] == 202.12
    assert s["500l"]["2026-03-02"] == 416.26
    assert s["900l"]["2026-03-03"] == 831.04


def test_ccni_ignores_non_litre_charts():
    other = ('&quot;data&quot;:[[&quot;&quot;,&quot;tariff&quot;],'
             '[&quot;01/01/2026&quot;,99.0]]')
    s = parse_ccni_series(other)
    assert not any(s.values())


# ------------------------------------- oil bulletin - live formats

BULLETIN_LINKS = (
    '<a href="/document/download/264c2d0f-f161-4ea3-a777-78faae59bea0_en'
    '?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices%20with%20Taxes'
    '%20-%202024-02-19.xlsx">x</a>'
    '<a href="/document/download/78311f92-68f8-4b82-b5cf-1293beeaae77_en'
    '?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices%20without%20taxes'
    '%20-%202024-02-19.xlsx">y</a>'
)


def test_bulletin_resolves_with_taxes_only():
    url = resolve_oil_bulletin_url(BULLETIN_LINKS)
    assert url is not None and "264c2d0f" in url, url
    assert url.startswith("https://energy.ec.europa.eu/")


def test_bulletin_resolves_without_taxes():
    url = resolve_oil_bulletin_url(BULLETIN_LINKS, with_tax=False)
    assert url is not None and "78311f92" in url, url


BULLETIN_ROWS = [
    ("Prices in force on 06/07/2026", None, None, None, None, None, None),
    ("in EUR", "Euro-super 95  (I)", "Gas oil automobile Automotive ",
     " Gas oil de chauffage Heating ", " Fuel oil - Schweres Heiz\u00f6l (I",
     " Fuel oil -Schweres Heiz\u00f6l (II", "GPL pour moteur LPG motor fuel"),
    ("Belgique", 1728.94, 1878.72, 1019.50, 453.39, None, None),
    ("Ireland", 1729.80, 1712.70, 1151.60, None, None, 892.16),
    ("Italia", 1810.00, 1887.18, 1300.00, None, None, 773.60),
]


def test_bulletin_snapshot_parse():
    d, v = parse_bulletin_rows(BULLETIN_ROWS)
    assert d == "2026-07-06", d
    assert v == 1151.60, v


def test_bulletin_datetime_cell():
    rows = [
        (dt.datetime(2026, 7, 6), None),
        ("x", "Heating gas oil"),
        ("Ireland", 1151.6),
    ]
    d, v = parse_bulletin_rows(rows)
    assert d == "2026-07-06" and v == 1151.6


def test_bulletin_no_ireland_returns_none():
    rows = [("in EUR", "Heating gas oil"), ("Italia", 1300.0)]
    d, v = parse_bulletin_rows(rows)
    assert v is None


# ------------------------------------- semopx CSV - live format

SEMOPX_CSV = """Auction;SEM-DA
Auction name;PWR-SEM-GB-D+1
Auction date time;2026-07-12T16:30:00Z
Publication date time;2026-07-12T17:00:00Z
FX rates
EUR;GBP;0,85506627
Market;NI-DA
Index prices;30;EUR
2026-07-12T22:00:00Z;2026-07-12T22:30:00Z;2026-07-12T23:00:00Z
95,50;88,25;102,00
Index prices;30;GBP
2026-07-12T22:00:00Z;2026-07-12T22:30:00Z;2026-07-12T23:00:00Z
81,66;75,46;87,22
Market;ROI-DA
Index prices;30;EUR
2026-07-12T22:00:00Z;2026-07-12T22:30:00Z;2026-07-12T23:00:00Z
96,10;89,00;101,40
"""


def test_semopx_csv_parse():
    p = parse_semopx_csv(SEMOPX_CSV)
    assert p["auction"] == "SEM-DA"
    assert p["fx_eur_gbp"] == 0.85506627
    assert p["day"] == "2026-07-12"
    assert p["markets"]["NI-DA"]["EUR"] == [95.5, 88.25, 102.0]
    assert p["markets"]["NI-DA"]["GBP"] == [81.66, 75.46, 87.22]
    assert p["markets"]["ROI-DA"]["EUR"] == [96.1, 89.0, 101.4]


def test_semopx_csv_tolerates_blank_and_unknown_lines():
    p = parse_semopx_csv("Auction;SEM-DA\n\nSomething;else\n"
                         "Market;ROI-DA\nIndex prices;30;EUR\n"
                         "2026-07-12T22:00:00Z\n100,0;200,0\n")
    assert p["markets"]["ROI-DA"]["EUR"] == [100.0, 200.0]


# ------------------------------------- gni_live parser - probed format

def test_gni_series_parse():
    ms = lambda iso: int(dt.datetime.fromisoformat(
        iso + "T00:00:00+00:00").timestamp() * 1000)
    sample = [
        {"name": "Non Daily Metered", "location": "NDM", "group": "demand",
         "color": "#123456", "showInLegend": True, "visible": True,
         "data": [[ms("2026-07-12"), 5.2e6], [ms("2026-07-13"), 4.9e6]]},
        {"name": "ROI Power Generation", "location": "ROI Power Gen",
         "data": [[ms("2026-07-12"), 8.8e7]]},
        {"name": "broken", "location": "DM",
         "data": [[None, 1], ["x", 2], [ms("2026-07-13"), 3.1e7]]},
        {"name": "no location", "data": [[ms("2026-07-13"), 1.0]]},
    ]
    p = parse_gni_series(sample)
    assert p["NDM"]["2026-07-12"] == 5.2e6
    assert p["NDM"]["2026-07-13"] == 4.9e6
    assert p["ROI Power Gen"]["2026-07-12"] == 8.8e7
    assert p["DM"] == {"2026-07-13": 3.1e7}
    assert "no location" not in str(p)


def test_gni_series_empty_and_malformed():
    assert parse_gni_series(None) == {}
    assert parse_gni_series([]) == {}
    assert parse_gni_series([{"location": "NDM", "data": []}]) == {}


# ------------------------------------- hero derivation

def _hero_fixture_feeds():
    hdd = {}
    d0 = dt.date.today() - dt.timedelta(days=365)
    for i in range(366):
        d = (d0 + dt.timedelta(days=i))
        hdd[d.isoformat()] = round(max(0.0, 8.0 + 7.0 * math.cos(
            2 * math.pi * (i / 365.0))), 2)
    return {
        "hdd": {"hdd_island": hdd},
        "ecb_fx": {"eur_gbp": 0.855},
        "oil_bulletin": {"latest_value": 1151.6},
        "ccni_oil": {"series_gbp": {"daily": {"900l": {"2026-07-10": 536.72},
                                              "500l": {}, "300l": {}}}},
    }


def test_hero_produces_sane_numbers():
    h = derive_hero(_hero_fixture_feeds())
    assert h is not None
    assert 100 < h["heat_purchased_gwh"] < 3000, h["heat_purchased_gwh"]
    assert 0 < h["indigenous_share_pct"] < 100
    assert h["bill_eur_m"] > 0 and h["bill_gbp_m"] > 0
    assert abs(h["bill_gbp_m"] / h["bill_eur_m"] - 0.855) < 0.01
    assert h["emissions_kt_co2"] > 0


def test_hero_what_if_moves_the_right_way():
    h = derive_hero(_hero_fixture_feeds())
    wf = h["what_if_20pct_geothermal"]
    assert wf["heat_purchased_gwh"] < h["heat_purchased_gwh"]
    assert wf["indigenous_share_pct"] > h["indigenous_share_pct"]
    assert wf["emissions_kt_co2"] < h["emissions_kt_co2"]


def test_hero_by_fuel_and_peak():
    h = derive_hero(_hero_fixture_feeds())
    for b in (h["roi"], h["ni"], h):
        bf = b["by_fuel"]
        assert abs(sum(v["in_gwh"] for v in bf.values())
                   - b["heat_purchased_gwh"]) < 0.5
        assert abs(sum(v["useful_gwh"] for v in bf.values())
                   - b["heat_delivered_gwh"]) < 0.5
    # fixture sinusoid peaks at the series edge, so peak == current week
    # there; real data peaks mid-winter. Peak can never be below current.
    assert h["peak_week"] and h["peak_week"]["heat_purchased_gwh"] \
        >= h["heat_purchased_gwh"] - 0.1
    assert h["roi"]["peak_week"]["hdd"] >= h["roi"]["hdd_week"]
    assert h["roi"]["by_fuel"]["oil"]["in_gwh"] > 0


def test_hero_jurisdiction_blocks_reconcile():
    h = derive_hero(_hero_fixture_feeds())
    assert "roi" in h and "ni" in h
    for k in ("heat_purchased_gwh", "bill_eur_m", "emissions_kt_co2"):
        assert abs(h["roi"][k] + h["ni"][k] - h[k]) < 0.2, k
    # ROI is the larger heat system
    assert h["roi"]["heat_purchased_gwh"] > h["ni"]["heat_purchased_gwh"]


def test_hero_weekly_sums_to_annual():
    feeds = _hero_fixture_feeds()
    h = derive_hero(feeds)
    a = ANCHORS
    heat_twh = sum(a[j]["residential_heat_twh"] + a[j]["services_heat_twh"]
                   for j in ("roi", "ni"))
    shf = a["space_heat_fraction"]
    expected = heat_twh * 1000 * ((1 - shf) / 52.0
                                  + shf * h["hdd_week"] / h["hdd_year"])
    assert abs(h["heat_purchased_gwh"] - expected) < expected * 0.02


# ------------------------------------- heat gap derivation

def test_heat_gap_sane_and_matches_hand_calc():
    feeds = _hero_fixture_feeds()
    feeds["hdd"]["hdd_ni"] = feeds["hdd"]["hdd_island"]
    feeds["hdd"]["hdd_roi"] = feeds["hdd"]["hdd_island"]
    hg = derive_heat_gap(feeds)
    assert hg is not None
    ni, roi = hg["ni"], hg["roi"]
    # hand calc: NI oil 536.72*100/900 = 59.64 p/L -> /10.35/0.82 = 7.03 p
    assert abs(ni["oil_boiler"] - 7.03) < 0.05, ni
    # NI breakeven = 32.5 / 7.03 = 4.62
    assert abs(ni["breakeven_spf_vs_oil"] - 4.62) < 0.05, ni
    # ROI oil 115.16 c/L -> 13.57 c useful; breakeven 36/13.57 = 2.65
    assert abs(roi["oil_boiler"] - 13.57) < 0.05, roi
    assert abs(roi["breakeven_spf_vs_oil"] - 2.65) < 0.05, roi
    # geothermal beats oil in ROI, loses in NI at these prices
    assert roi["geothermal_spf40"] < roi["oil_boiler"]
    assert ni["geothermal_spf40"] > ni["oil_boiler"]
    # climate ASHP lands in the field-trial band and under 3
    assert 2.4 <= ni["ashp_spf"] < 3.0, ni["ashp_spf"]
    assert 2.4 <= roi["ashp_spf"] < 3.0, roi["ashp_spf"]


def test_ashp_spf_model():
    import math as _m
    hdd = {}
    d0 = dt.date.today() - dt.timedelta(days=365)
    for i in range(366):
        d = (d0 + dt.timedelta(days=i)).isoformat()
        hdd[d] = round(max(0.0, 8.0 + 7.0 * _m.cos(2 * _m.pi * i / 365)), 2)
    r = derive_ashp_spf(hdd)
    assert r is not None and 2.4 <= r["spf"] < 3.0, r
    # colder climate (2C shift) must lower the SPF
    colder = {d: round(v + 2.0, 2) if v > 0 else v for d, v in hdd.items()}
    rc = derive_ashp_spf(colder)
    assert rc["spf"] < r["spf"], (r, rc)
    # insufficient season -> None
    assert derive_ashp_spf({k: hdd[k] for k in sorted(hdd)[-30:]}) is None


def test_heat_gap_missing_oil_returns_none():
    feeds = _hero_fixture_feeds()
    feeds["ccni_oil"] = {}
    assert derive_heat_gap(feeds) is None


# ------------------------------------- gb oil sentence - verbatim fixture

GB_SENTENCE = ("Our average heating oil price for today, Saturday 25th "
               "March 2017\nis 40.32 pence per litre (inc. VAT).")

# verbatim from the live /kerosene-prices/ template (fetched 15 Jul 2026)
GB_KERO_SENTENCE = ("Our average Kerosene price for today, Saturday 20th "
                    "June 2026  \nis 75.36 pence per litre (inc. VAT).")


def test_gb_oil_kerosene_wording():
    d, p = parse_gb_oil_page("junk " + GB_KERO_SENTENCE + " junk")
    assert d == "2026-06-20" and p == 75.36


def test_gb_oil_sentence_parse():
    d, p = parse_gb_oil_page("junk before " + GB_SENTENCE + " junk after")
    assert d == "2017-03-25" and p == 40.32


def test_gb_oil_sentence_no_date():
    d, p = parse_gb_oil_page(
        "average heating oil price for today is 82.99 pence per litre")
    assert d is None and p == 82.99


def test_gb_oil_sentence_absent():
    assert parse_gb_oil_page("no prices here") == (None, None)


# ------------------------------------- cool side

def test_cool_derivation():
    feeds = _hero_fixture_feeds()
    c = derive_cool(feeds)
    assert c is not None
    # sinusoidal HDD with a summer zero-floor strands a big minority
    assert 20 <= c["stranded_summer_pct"] <= 60, c
    assert abs(c["dc_twh"] - 31.0 * 0.22) < 0.1
    assert c["waste_vs_roi_residential_pct"] > 20
    # no HDD -> None
    assert derive_cool({"hdd": {}}) is None


# ------------------------------------- geo per-capita

def test_geo_percap():
    p = derive_geo_percap()
    # current: ROI ~42 W/person, NI a few W, island in between
    assert 38 <= p["roi"]["current_w_pp"] <= 46, p["roi"]
    assert 2 <= p["ni"]["current_w_pp"] <= 5, p["ni"]
    assert p["ni"]["current_w_pp"] < p["island"]["current_w_pp"] \
        < p["roi"]["current_w_pp"]
    # what-if requirement dwarfs current everywhere; NI worst per person
    for j in ("roi", "ni", "island"):
        assert p[j]["whatif_w_pp"] > 8 * p[j]["current_w_pp"], j
    assert p["ni"]["whatif_w_pp"] > p["roi"]["whatif_w_pp"]
    # hand check ROI: useful ~25.3 TWh -> 0.2*25.3e12/2000/5.3e6 ~ 477
    assert abs(p["roi"]["whatif_w_pp"] - 477) < 15, p["roi"]
    # MWth basis: requirement = useful_twh * 100 at 2000 h
    assert abs(p["roi"]["whatif_mwth"] - p["roi"]["useful_twh"] * 100) < 60
    assert p["roi"]["current_mwth"] == 225
    assert abs(p["island"]["current_mwth"] - 231.6) < 0.5


# ------------------------------------- bulletin history parser

def test_bulletin_history_collects_all_ireland_rows():
    rows = [
        ("preamble", None, None),
        ("Country", "Euro-super 95", "Heating gas oil"),
        ("Ireland", 1700.0, 1100.0, dt.datetime(2026, 6, 22)),
        ("France", 1800.0, 1200.0, dt.datetime(2026, 6, 22)),
        ("Ireland", 1710.0, 1120.5, dt.datetime(2026, 6, 29)),
        ("IE", 1720.0, 1151.6, dt.datetime(2026, 7, 6)),
        ("Ireland", 1720.0, "n/a", dt.datetime(2026, 7, 13)),
    ]
    s = parse_bulletin_history_rows(rows)
    assert s == {"2026-06-22": 1100.0, "2026-06-29": 1120.5,
                 "2026-07-06": 1151.6}, s


def test_bulletin_history_wide_layout_from_live_dump():
    header = ('Consumer prices of petroleum products inclusive of duties '
              'and taxes', 'CTR', 'EU_price_with_tax_euro95',
              'EU_price_with_tax_diesel', 'EU_price_with_tax_heating_oil',
              'CTR', 'IE_price_with_tax_euro95', 'IE_price_with_tax_diesel',
              'IE_price_with_tax_heating_oil', 'CTR',
              'FR_price_with_tax_heating_oil')
    units = ('Date', None, '1000 l', '1000 l', '1000 l', None, '1000 l',
             '1000 l', '1000 l', None, '1000 l')
    r1 = (dt.datetime(2026, 7, 13), 'EU_', 1851.02, 1823.02, 1309.08,
          'IE_', 1712.5, 1689.3, 1113.25, 'FR_', 1505.66)
    r2 = (dt.datetime(2026, 7, 6), 'EU_', 1814.32, 1766.15, 1229.85,
          'IE_', 1729.8, 1712.7, 1151.6, 'FR_', 1420.57)
    r3 = (None, None, None, None, None, None, None, None, 'n/a', None, None)
    s = parse_bulletin_history_rows(iter([header, units, r1, r2, r3]))
    assert s == {"2026-07-13": 1113.25, "2026-07-06": 1151.6}, s
    # ex-tax column selection
    h2 = ('x', 'IE_price_wo_tax_heating_oil')
    d2 = (dt.datetime(2026, 7, 13), 767.78)
    s2 = parse_bulletin_history_rows(iter([h2, d2]))
    assert s2 == {"2026-07-13": 767.78}, s2


def test_bulletin_history_block_layout():
    rows = [
        ("Country", "Euro-super 95", "Heating gas oil"),
        ("France", None, None),
        (dt.datetime(2026, 6, 22), 1800.0, 1200.0),
        ("Ireland", None, None),
        (dt.datetime(2026, 6, 22), 1700.0, 1100.0),
        (dt.datetime(2026, 6, 29), 1710.0, 1120.5),
        ("Italia... wait", None, None),   # unknown row - stays in block
        (dt.datetime(2026, 7, 6), 1720.0, 1151.6),
        ("Netherlands", None, None),
        (dt.datetime(2026, 7, 6), 1900.0, 1400.0),
    ]
    s = parse_bulletin_history_rows(rows)
    assert s == {"2026-06-22": 1100.0, "2026-06-29": 1120.5,
                 "2026-07-06": 1151.6}, s


def test_bulletin_history_rejects_out_of_range():
    rows = [("x", "Heating"), ("Ireland", 99.0, dt.datetime(2026, 1, 5))]
    assert parse_bulletin_history_rows(rows) == {}


# ------------------------------------- why heat panel anchors

def test_why_heat_anchors_reconcile():
    s = WHY_HEAT["services_twh"]
    total = sum(s.values())
    # services within 8% of stated TFC (non-energy uses absorb the rest)
    assert abs(total - WHY_HEAT["tfc_twh"]) / WHY_HEAT["tfc_twh"] < 0.08
    # the panel thesis: heat is NOT the biggest bill despite its scale
    sp = WHY_HEAT["spend_eur_bn"]
    assert sp["heat"] < sp["power"] < sp["transport"]
    # heat cheapest per unit delivered among the three
    unit = {k: sp[k] / s[k] for k in s}
    assert unit["heat"] < unit["power"] and unit["heat"] < unit["transport"]
    # imports never exceed the service itself
    for k, v in WHY_HEAT["imports_twh"].items():
        assert 0 < v <= s[k]
    assert all(v > 0 for v in WHY_HEAT["emissions_mt"].values())


# ------------------------------------- calibration + odh groundwork

def test_gas_calibration_consistent_slope_hits_gate():
    hdd = {}
    d0 = dt.date.today() - dt.timedelta(days=365)
    import math as _m
    for i in range(366):
        d = (d0 + dt.timedelta(days=i)).isoformat()
        hdd[d] = round(max(0.0, 8 + 7 * _m.cos(2 * _m.pi * i / 365)), 2)
    annual = sum(hdd[d] for d in sorted(hdd)[-365:])
    from build import ANCHORS
    j = ANCHORS["roi"]
    anchor = ((j["residential_heat_twh"] + j["services_heat_twh"])
              * j["fuel_shares"]["gas"] * ANCHORS["space_heat_fraction"]
              * 1000.0)
    reg = {"slope_gwh_per_hdd": anchor / annual}
    cal = derive_gas_calibration(reg, hdd)
    assert cal and cal["within_gate"] and abs(cal["ratio"] - 1.0) < 0.02
    # a slope 30% low must be disclosed as outside the gate
    cal2 = derive_gas_calibration(
        {"slope_gwh_per_hdd": 0.7 * anchor / annual}, hdd)
    assert cal2 and not cal2["within_gate"]


def test_odh26_aggregation():
    payload = [
        {"hourly": {"time": ["2026-07-01T12:00", "2026-07-01T13:00",
                             "2026-07-02T12:00"],
                    "temperature_2m": [28.0, 25.0, 30.0]}},
        {"hourly": {"time": ["2026-07-01T12:00", "2026-07-01T13:00",
                             "2026-07-02T12:00"],
                    "temperature_2m": [27.0, 29.0, None]}},
    ]
    out = odh26_from_hourly(payload, ["A", "B"], {"A": 0.6, "B": 0.4})
    # day1: A 0.6*2 + B 0.4*(1+3)=1.2+1.6=2.8 ; day2: A 0.6*4=2.4
    assert out == {"2026-07-01": 2.8, "2026-07-02": 2.4}, out


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass - {fn.__name__}")
    print(f"{len(fns)} synthetic tests passed")
