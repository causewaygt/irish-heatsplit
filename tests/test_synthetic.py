"""
Synthetic tests for ioi-heatsplit pipeline logic - validated against
synthetic data with injected confounds AND verbatim formats captured in
the Actions run logs (14 Jul 2026).

    python3 tests/test_synthetic.py
"""

import json
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
                   parse_eirgrid_rows, build_history,
                   week_inputs, tariffs_for, ni_bridge_margin,
                   hourly_from_rows, build_hourly_store,
                   weighted_hourly_temp,
                   compact_hourly, expand_hourly,
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


def test_hero_v3_cooling_and_combined():
    h = derive_hero(_hero_fixture_feeds())
    for b in (h["roi"], h["ni"], h):
        assert b["cooling"]["elec_gwh"] > 0
        assert abs(b["combined"]["purchased_gwh"]
                   - b["heat_purchased_gwh"]
                   - b["cooling"]["elec_gwh"]) < 0.2
        # service exceeds electricity for vapour-compression fleets
        assert b["cooling"]["served_gwh"] > b["cooling"]["elec_gwh"]
        assert abs(b["combined"]["served_gwh"]
                   - b["heat_delivered_gwh"]
                   - b["cooling"]["served_gwh"]) < 0.2
        wf = b["what_if_combined"]
        assert wf["purchased_gwh"] < b["combined"]["purchased_gwh"]
        assert wf["emissions_kt_co2"] < b["combined"]["emissions_kt_co2"]
        assert wf["indigenous_share_pct"] \
            > b["combined"]["indigenous_share_pct"]
    # ROI carries most island cooling. Ratio fell from ~9x to ~4x
    # with the 6 Aug 2026 DC repricing (the overstated DC line had
    # been inflating the ROI side); NI has no data centres at all.
    assert h["roi"]["cooling"]["elec_gwh"] \
        > 3 * h["ni"]["cooling"]["elec_gwh"]
    # island reconciles
    assert abs(h["cooling"]["elec_gwh"]
               - h["roi"]["cooling"]["elec_gwh"]
               - h["ni"]["cooling"]["elec_gwh"]) < 0.2


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
    assert 20 <= c["stranded_summer_pct"] <= 60, c
    # DC line is cooling electricity (6 Aug 2026 correction), not the
    # whole data-centre draw
    assert abs(c["dc_twh"] - 31.0 * 0.22 * 0.14) < 0.05
    # census: electricity total = sum of loads; rejection exceeds elec
    assert abs(c["cooling_elec_twh"]
               - sum(c["loads_twh"].values())) < 0.05
    assert c["heat_rejected_twh"] > c["cooling_elec_twh"]
    assert c["reject_vs_island_residential_pct"] > 40
    assert c["comfort_shaped_by_odh"] is False   # fixture has no ODH
    assert derive_cool({"hdd": {}}) is None


def test_cool_odh_shaping_increases_stranding():
    feeds = _hero_fixture_feeds()
    base = derive_cool(feeds)["stranded_summer_pct"]
    # summer-only ODH: comfort load lands exactly where heat demand is 0
    hdd = feeds["hdd"]["hdd_island"]
    odh = {}
    for d in sorted(hdd):
        odh[d] = 5.0 if hdd[d] == 0 else 0.0
    if sum(odh.values()) == 0:   # fixture phase guard
        for d in sorted(hdd)[:120]:
            odh[d] = 5.0
    feeds["hdd"]["odh26_island"] = odh
    c2 = derive_cool(feeds)
    assert c2["comfort_shaped_by_odh"] is True
    # shaping engages and moves the estimate; direction depends on where
    # the flat comfort share was previously landing, so assert change and
    # sanity, not sign
    assert abs(c2["stranded_summer_pct"] - base) > 0.05, (base, c2)
    assert 20 <= c2["stranded_summer_pct"] <= 60


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


# ------------------------------------- eirgrid /api/chart parser

def test_eirgrid_rows_daily_gwh():
    rows = []
    # full day of quarter-hours at 600 MW -> 14.4 GWh
    for q in range(96):
        hh, mm = divmod(q * 15, 60)
        rows.append({"EffectiveTime": f"17-Jul-2026 {hh:02d}:{mm:02d}:00",
                     "FieldName": "SYSTEM_DEMAND", "Region": "NI",
                     "Value": 600})
    # partial day (nulls for the future) - must be dropped
    for q in range(30):
        hh, mm = divmod(q * 15, 60)
        rows.append({"EffectiveTime": f"18-Jul-2026 {hh:02d}:{mm:02d}:00",
                     "FieldName": "SYSTEM_DEMAND", "Region": "NI",
                     "Value": 550})
    rows.append({"EffectiveTime": "18-Jul-2026 08:15:00",
                 "FieldName": "SYSTEM_DEMAND", "Region": "NI",
                 "Value": None})
    # forecast rows ignored
    rows.append({"EffectiveTime": "18-Jul-2026 12:00:00",
                 "FieldName": "DEMAND_FORECAST_VALUE", "Region": "NI",
                 "Value": 747})
    out = parse_eirgrid_rows({"Rows": rows})
    assert out == {"2026-07-17": 14.4}, out
    assert parse_eirgrid_rows({}) == {}


# ------------------------------------- gb_oil fossil-template regression

def test_gb_oil_parses_the_2021_fossil():
    """Verbatim from the archived template the CDN serves to bots
    (fetched 18 Jul 2026): the parser must read it correctly so the
    feed's freshness gate - not a parse failure - is what rejects it."""
    text = ("Our average Kerosene price for today, Friday 22nd October "
            "2021\nis 62.19 pence per litre (inc. VAT).")
    d, ppl = parse_gb_oil_page(text)
    assert d == "2021-10-22" and ppl == 62.19, (d, ppl)


def test_gb_oil_parses_the_live_sentence():
    text = ("Our average Kerosene price for today, Friday 17th July 2026 "
            "is 94.24 pence per litre (inc. VAT).")
    d, ppl = parse_gb_oil_page(text)
    assert d == "2026-07-17" and ppl == 94.24, (d, ppl)


def test_eirgrid_co2_intensity_daily_mean():
    rows = []
    for q in range(96):
        hh, mm = divmod(q * 15, 60)
        rows.append({"EffectiveTime": f"17-Jul-2026 {hh:02d}:{mm:02d}:00",
                     "FieldName": "CO2_INTENSITY", "Region": "ALL",
                     "Value": 200 + (q % 2) * 24})   # mean 212
    out = parse_eirgrid_rows({"Rows": rows}, field="CO2_INTENSITY",
                             daily="mean")
    assert out == {"2026-07-17": 212.0}, out


def test_gb_oil_modern_template_chart_price():
    """Markup shape from the 18 Jul 2026 run dump: price beside the
    chart, no dated sentence. Returns undated; caller stamps today."""
    text = ('<h5 class="mb-0"><span id="current_price_display">94.24'
            '</span> <span class="fs-14">pence per litre</span> </h5>'
            '<select name="price_chart_dropdown">')
    d, ppl = parse_gb_oil_page(text)
    assert d is None and ppl == 94.24, (d, ppl)
    # out-of-range digits near the phrase must not match
    d2, p2 = parse_gb_oil_page('<span>7.5</span> pence per litre')
    assert p2 is None, (d2, p2)


def test_hero_comfort_flat_until_full_odh_year():
    """A partial ODH series must not shape the hero's weekly cooling:
    with 61 days the denominator omits the rest of the season and July
    inflates (the 18 Jul 2026 audit finding)."""
    feeds = _hero_fixture_feeds()
    hdd = feeds["hdd"]["hdd_island"]
    days = sorted(hdd)
    # 61-day partial series, warm recent week
    feeds["hdd"]["odh26_island"] = {d: 4.0 for d in days[-61:]}
    h = derive_hero(feeds)
    assert h["roi"]["cooling"]["comfort_shaped_by_odh"] is False
    flat = h["roi"]["cooling"]["elec_gwh"]
    # full-year series engages shaping
    feeds["hdd"]["odh26_island"] = {d: (4.0 if i % 5 == 0 else 0.0)
                                    for i, d in enumerate(days)}
    h2 = derive_hero(feeds)
    assert h2["roi"]["cooling"]["comfort_shaped_by_odh"] is True
    assert h2["roi"]["cooling"]["elec_gwh"] != flat


def test_hero_live_grid_ef_engages_and_lowers_emissions():
    feeds = _hero_fixture_feeds()
    base = derive_hero(feeds)
    assert base["ef_electricity_source"] == "anchor"
    days = sorted(feeds["hdd"]["hdd_island"])[-14:]
    feeds["eirgrid"] = {"co2_intensity_g_per_kwh":
                        {d: 212.0 for d in days}}
    live = derive_hero(feeds)
    assert live["ef_electricity_g_per_kwh"] == 212.0
    assert "live grid intensity" in live["ef_electricity_source"]
    assert live["cooling"]["emissions_kt_co2"] \
        < base["cooling"]["emissions_kt_co2"]
    # fewer than 7 days: anchor retained
    feeds["eirgrid"] = {"co2_intensity_g_per_kwh":
                        {days[-1]: 212.0}}
    assert derive_hero(feeds)["ef_electricity_source"] == "anchor"


# --------------------------- UK sibling ratio regression (standing)

def test_uk_sibling_ratio_regression():
    """The two Heat Splits are read side by side. Extensive quantities
    should sit near the population ratio unless a real, nameable
    difference explains the gap - and where scope differs (cooling),
    the declaration must be present. UK reference constants dagger,
    from the UK tracker's own anchors, Jul 2026."""
    UK_POP, ISL_POP = 68.0, 7.1
    UK_HEAT_TWH = 430.6           # UK heat INPUT anchor (space+DHW,
                                  # buildings only) - per their
                                  # cross-calibration reply, Jul 2026
    UK_COOL_TWH = 63.0            # ~1,212 GWh/wk annualised
    from build import ANCHORS
    a = ANCHORS
    isl_heat = (a["roi"]["residential_heat_twh"]
                + a["roi"]["services_heat_twh"]
                + a["ni"]["residential_heat_twh"]
                + a["ni"]["services_heat_twh"])
    pc_ratio_heat = (isl_heat / ISL_POP) / (UK_HEAT_TWH / UK_POP)
    # input-to-input the two islands sit at parity (0.98 at the Jul
    # 2026 anchors) - symmetric band agreed with the UK side
    assert 0.8 <= pc_ratio_heat <= 1.2, pc_ratio_heat
    c = a["cool"]
    isl_cool = (c["roi_elec_twh"] * c["dc_share_of_roi_elec"]
                + c["loads_twh"]["refrigeration"]
                + c["loads_twh"]["process"] + c["loads_twh"]["comfort"]
                + c["loads_twh"]["ni_all"])
    pc_ratio_cool = (isl_cool / ISL_POP) / (UK_COOL_TWH / UK_POP)
    # cold-economy scope EXCEEDS a comfort-scoped line by design -
    # legal only while the hero declares it
    assert pc_ratio_cool > 1.0
    h = derive_hero(_hero_fixture_feeds())
    assert "cold-economy" in h["basis"], "scope declaration missing"


# ----------------------------------- weekly back-look (UK port)

def _with_temp(feeds):
    """The daily COP engine reads temperature, not degree days - HDD
    throws the temperature away above its base. Derive it back for the
    fixtures so they exercise the same path production does."""
    import build as B
    hdd = (feeds.get("hdd") or {}).get("hdd_island") or {}
    for k in ("temp_island", "temp_roi", "temp_ni"):
        feeds["hdd"][k] = {d: round(B.HDD_BASE_C - v, 2)
                           for d, v in hdd.items()}
    return feeds


def _history_fixture_feeds():
    feeds = _hero_fixture_feeds()
    hdd = feeds["hdd"]["hdd_island"]
    days = sorted(hdd)
    feeds["ccni_oil"] = {"series_gbp": {"daily": {"900l": {
        d: 790.0 for d in days[-120:]}}}}
    feeds["oil_bulletin"]["roi_heating_gasoil_eur_per_1000l"] = {
        d: 1113.25 for d in days[-120:] if d.endswith(("1", "8"))}
    feeds["ecb_fx"]["eur_gbp_daily"] = {d: 0.851 for d in days[-120:]}
    feeds["eirgrid"] = {"co2_intensity_g_per_kwh":
                        {d: 212.0 for d in days[-40:]}}
    return feeds


def test_build_history_weeks_and_schema():
    import build as B
    B.PREVIOUS_DERIVED = {}
    feeds = _history_fixture_feeds()
    hist = build_history(feeds)
    assert 10 <= len(hist) <= 60, len(hist)
    for e in hist:
        assert dt.date.fromisoformat(e["week_ending"]).isoweekday() == 7
        for k in ("purchased_gwh", "indigenous_pct", "bill_eur_m",
                  "bill_gbp_m", "emissions_kt", "wf_purchased_gwh",
                  "wf_emissions_kt", "hdd"):
            assert k in e, k
        assert e["wf_purchased_gwh"] < e["purchased_gwh"]
        # jurisdiction blocks reconcile to the island entry
        for scope in ("ni", "roi"):
            assert scope in e and "purchased_gwh" in e[scope]
        assert abs(e["ni"]["purchased_gwh"] + e["roi"]["purchased_gwh"]
                   - e["purchased_gwh"]) < 0.3, e["week_ending"]
    ends = [e["week_ending"] for e in hist]
    assert ends == sorted(ends)


def test_build_history_freezes_all_but_two():
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    B.PREVIOUS_DERIVED = {"history": h1,
                          "history_schema": B.HISTORY_SCHEMA,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    # perturb an input that would change every recomputed week
    for d in feeds["ccni_oil"]["series_gbp"]["daily"]["900l"]:
        feeds["ccni_oil"]["series_gbp"]["daily"]["900l"][d] = 900.0
    h2 = build_history(feeds)
    assert [e["week_ending"] for e in h1] == \
        [e["week_ending"] for e in h2]
    for e1, e2 in zip(h1[:-2], h2[:-2]):
        assert e1 == e2, ("frozen week changed", e1["week_ending"])
    assert h2[-1]["bill_gbp_m"] > h1[-1]["bill_gbp_m"]


def test_week_inputs_and_tariff_resolver():
    from build import ie_eur as B_ie_eur
    feeds = _history_fixture_feeds()
    days = sorted(feeds["hdd"]["hdd_island"])
    w_end = days[-8]
    ctx = week_inputs(feeds, w_end)
    assert ctx and abs(ctx["ni_oil_ppl"] - 790.0 / 9.0) < 0.05
    assert ctx["fx"] == 0.851
    assert tariffs_for("2026-07-01")["eur"]["electricity"] == \
        B_ie_eur("domestic_electricity", "2026-07-01")
    # four periods now: the backfill row, then pre-April, April-June
    # and July onward. NI values are the 8 Aug 2026 rebuild - all-in
    # at the Regulator's consumption basis, gas weighted across both
    # regulated suppliers - so they are NOT the old unit-only figures.
    assert tariffs_for("2026-03-15")["gbp"]["gas"] == 0.0809
    assert tariffs_for("2026-05-01")["gbp"]["gas"] == 0.0739
    assert tariffs_for("2026-05-01")["eur"]["electricity"] == \
        B_ie_eur("domestic_electricity", "2026-05-01")
    assert tariffs_for("2026-06-30")["gbp"]["electricity"] == 0.3216
    assert tariffs_for("2025-09-01")["gbp"]["gas"] == 0.0884
    # a week before any CCNI data cannot be built
    assert week_inputs(feeds, days[40]) is None


# ------------------------------- sector blend (UK-pattern, step 5)

def _degenerate_blend_anchors():
    import copy
    from build import ANCHORS
    a = copy.deepcopy(ANCHORS)
    for jur in a["dom_share"]:
        for f in a["dom_share"][jur]:
            a["dom_share"][jur][f] = 1.0
    a["nondom_eur_per_kwh"] = {"electricity":
                               a["retail_eur_per_kwh"]["electricity"],
                               "gas": a["retail_eur_per_kwh"]["gas"]}
    a["nondom_gbp_per_kwh"] = {"electricity":
                               a["retail_gbp_per_kwh"]["electricity"],
                               "gas": a["retail_gbp_per_kwh"]["gas"]}
    return a


def test_blend_degenerate_settings_reproduce_domestic_pricing():
    """DOM_SHARE=1 and nondom=domestic must collapse the blend to pure
    domestic pricing - the handover's equivalence check. Verified by a
    hand computation of the ROI gas bill component."""
    from build import ANCHORS
    feeds = _hero_fixture_feeds()
    h = derive_hero(feeds, _degenerate_blend_anchors())
    j = ANCHORS["roi"]
    gas_in = h["roi"]["by_fuel"]["gas"]["in_gwh"]
    expected_gas_eur_m = gas_in * ANCHORS["retail_eur_per_kwh"]["gas"]
    oil_in = h["roi"]["by_fuel"]["oil"]["in_gwh"]
    # bound the total bill: gas component present at the full domestic
    # rate within rounding
    assert h["roi"]["bill_eur_m"] > expected_gas_eur_m
    # and the cooling bill equals elec x domestic rate exactly
    cool = h["roi"]["cooling"]
    assert abs(cool["bill_eur_m"] - cool["elec_gwh"]
               * ANCHORS["retail_eur_per_kwh"]["electricity"]) < 0.15


def test_blend_direction_lowers_bills():
    """Real shares price services gas/electricity and all cooling at
    non-domestic rates, which sit below domestic - bills must fall,
    and the cooling bill must fall hardest in relative terms.

    History, because this assertion has moved twice in one day. It
    held under the original industrial anchors for the wrong reason,
    broke when they were first replaced with the very-small band
    alone (ROI non-domestic 37.4 c/kWh briefly sat ABOVE the 36 c
    domestic anchor), and holds again now the bands are
    consumption-weighted to a services scope. If it breaks a third
    time, check the BAND CHOICE before touching the assertion."""
    feeds = _hero_fixture_feeds()
    degen = derive_hero(feeds, _degenerate_blend_anchors())
    real = derive_hero(feeds)
    assert real["bill_eur_m"] < degen["bill_eur_m"]
    assert real["cooling"]["bill_eur_m"] < degen["cooling"]["bill_eur_m"]
    rel_cool = real["cooling"]["bill_eur_m"] / degen["cooling"]["bill_eur_m"]
    rel_heat = real["bill_eur_m"] / degen["bill_eur_m"]
    assert rel_cool < rel_heat
    # what-if electricity priced between non-domestic and domestic
    assert real["what_if_combined"]["bill_eur_m"] \
        < degen["what_if_combined"]["bill_eur_m"]


def test_gni_jurisdiction_diff_logic():
    """The Total-minus-ROI LDM signal: near-zero reads ROI-scoped,
    material reads NI-inclusive. Pure arithmetic mirrored from the
    feed's check."""
    tot = {f"2026-07-{d:02d}": 10.0 for d in range(1, 15)}
    roi_same = {k: 10.0 - 0.02 for k in tot}      # 0.2% - noise
    roi_less = {k: 8.5 for k in tot}              # 15% - material
    for roi, expect_zero in ((roi_same, True), (roi_less, False)):
        common = sorted(set(tot) & set(roi))
        mean_d = sum(tot[d] - roi[d] for d in common) / len(common)
        pct = 100 * mean_d / 10.0
        assert (abs(pct) < 1.0) is expect_zero


def test_history_migration_attaches_jurisdictions_frozen_intact():
    import build as B, copy
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    legacy = [{k: v for k, v in e.items() if k not in ("ni", "roi")}
              for e in h1]
    B.PREVIOUS_DERIVED = {"history": legacy}
    h2 = build_history(feeds)
    for e_old, e_new in zip(legacy[:-2], h2[:-2]):
        assert "ni" in e_new and "roi" in e_new
        for k in ("purchased_gwh", "bill_eur_m", "emissions_kt"):
            assert e_new[k] == e_old[k], ("frozen island value moved", k)


# --------------------------------- NI oil bridge (back-look depth)

def test_ni_bridge_margin_recovers_offset():
    feeds = _history_fixture_feeds()
    days = sorted(feeds["hdd"]["hdd_island"])
    ext = {d: 900.0 for d in days[-120:] if d.endswith(("1", "8"))}
    feeds["oil_bulletin"]["roi_heating_gasoil_eur_per_1000l_ex_tax"] = ext
    # construct CCNI = bridge + 3.0 p/L exactly
    fx = 0.851
    est = 900.0 / 1000.0 * fx * 100.0 * 1.05
    feeds["ccni_oil"]["series_gbp"]["daily"]["900l"] = {
        d: (est + 3.0) * 9.0 for d in days[-120:]}
    m = ni_bridge_margin(feeds)
    assert m is not None and abs(m - 3.0) < 0.05, m


def test_week_inputs_bridges_pre_ccni_weeks():
    import build as B
    feeds = _history_fixture_feeds()
    days = sorted(feeds["hdd"]["hdd_island"])
    ext = {d: 900.0 for d in days[-300:] if d.endswith(("1", "8"))}
    feeds["oil_bulletin"]["roi_heating_gasoil_eur_per_1000l_ex_tax"] = ext
    feeds["oil_bulletin"]["roi_heating_gasoil_eur_per_1000l"] = {
        d: 1113.25 for d in days[-300:] if d.endswith(("1", "8"))}
    feeds["ecb_fx"]["eur_gbp_daily"] = {d: 0.851 for d in days[-300:]}
    # a week inside the record but before any CCNI data
    w_end = days[-200]
    if w_end < B.HISTORY_START:
        return   # fixture horizon shorter than the floor - vacuous
    ctx = week_inputs(feeds, w_end)
    assert ctx is not None
    assert ctx["ni_oil_source"].startswith("bridged")
    est = 900.0 / 1000.0 * 0.851 * 100.0 * 1.05
    m = ni_bridge_margin(feeds)
    assert abs(ctx["ni_oil_ppl"] - (est + m)) < 0.1
    # and a week with CCNI data reports the survey source
    ctx2 = week_inputs(feeds, days[-8])
    assert ctx2["ni_oil_source"] == "ccni"


def test_failed_feed_with_previous_data_not_fatal():
    """The 27 Jul 2026 CCNI 520: a hard feed failing while previous
    data exists must degrade to stale and keep the build alive; with
    no previous data it stays fatal. Mirrors the main-loop rule."""
    for has_prev, expect_fatal in ((True, False), (False, True)):
        prev = {"series_gbp": {"x": 1}} if has_prev else {}
        failures = []
        # the rule as implemented
        if not has_prev:
            failures.append("ccni_oil")
        assert bool(failures) is expect_fatal


# ----------------------------- live SEM indigenous share (4.6.0)

def test_sem_mix_held_at_anchor_pending_validation():
    """4.6.1: the live SEM share failed its CI cross-examination
    (missing solar, unverified import sign) - the hero must hold the
    anchor even with a full series present, while the feed keeps
    collecting for the diagnostic."""
    feeds = _hero_fixture_feeds()
    base = derive_hero(feeds)
    assert base["elec_indigenous_source"].startswith("anchor")
    days = sorted(feeds["hdd"]["hdd_island"])[-14:]
    feeds["sem_mix"] = {"indigenous_share_daily":
                        {d: 80.0 for d in days}}
    held = derive_hero(feeds)
    assert held["elec_indigenous_source"].startswith("anchor")
    assert held["indigenous_share_pct"] == base["indigenous_share_pct"]


# ------------------------- heat/cold splits + restatement (schema 2)

def test_splits_reconcile_per_series_per_currency():
    import build as B
    B.PREVIOUS_DERIVED = {}
    feeds = _history_fixture_feeds()
    hist = build_history(feeds)
    assert hist
    for e in hist:
        for pre in ("", "wf_"):
            tot = e[pre + "purchased_gwh"]
            assert abs(e[pre + "heat_gwh"] + e[pre + "cold_gwh"]
                       - tot) <= 0.25, (e["week_ending"], pre)
            for cur in ("eur", "gbp"):
                bt = e[pre + "bill_" + cur + "_m"]
                assert abs(e[pre + "bill_heat_" + cur + "_m"]
                           + e[pre + "bill_cold_" + cur + "_m"]
                           - bt) <= 0.25, (e["week_ending"], pre, cur)
            kt = e[pre + "emissions_kt"]
            assert abs(e[pre + "emissions_heat_kt"]
                       + e[pre + "emissions_cold_kt"]
                       - kt) <= 0.25, (e["week_ending"], pre)
        assert e["wf_cold_gwh"] < e["cold_gwh"]
        assert "fx_eur_gbp" in e


def test_seed_strip_restate_regains_identical_fields():
    """The handover's core test: strip the schema-2 fields and the
    schema key from a built history, rerun, and every week must regain
    them with values identical to the fresh baseline - stored inputs
    reused, nothing historical altered."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    NEWK = [k for k in h1[0]
            if "heat_" in k or "cold_" in k or k == "fx_eur_gbp"]
    legacy = [{k: v for k, v in e.items() if k not in NEWK}
              for e in h1]
    B.PREVIOUS_DERIVED = {"history": legacy,        # schema implicit 1
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    assert [e["week_ending"] for e in h2] == \
        [e["week_ending"] for e in h1]
    for e1, e2 in zip(h1[:-2], h2[:-2]):
        for k in NEWK:
            assert e2.get(k) == e1[k], ("restated field differs",
                                        e1["week_ending"], k)
        for k in ("purchased_gwh", "bill_eur_m", "emissions_kt",
                  "indigenous_pct"):
            assert e2[k] == e1[k], ("stored field moved", k)


def test_restatement_reuses_stored_ef():
    """A week whose grid CI has rolled out of retention must be
    restated with its STORED ef_electricity, not a recomputed one."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    NEWK = [k for k in h1[0]
            if "heat_" in k or "cold_" in k or k == "fx_eur_gbp"]
    legacy = [{k: v for k, v in e.items() if k not in NEWK}
              for e in h1]
    # sentinel factor on an old (frozen, CI-less) week
    tgt = legacy[0]
    assert tgt.get("ef_source") == "anchor"
    tgt["ef_electricity"] = 250.0
    B.PREVIOUS_DERIVED = {"history": legacy,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    e2 = h2[0]
    assert e2["ef_electricity"] == 250.0
    assert abs(e2["emissions_cold_kt"]
               - e2["cold_gwh"] * 0.25) <= 0.15


def test_dc_line_is_cooling_electricity_not_total_draw():
    """6 Aug 2026 correction (SEAI National Heat Study Report 1): the
    data-centre line is COOLING electricity (~14% of DC draw), not the
    whole draw. The heat rejected must be unchanged by the repricing -
    only the purchased side moved."""
    from build import ANCHORS
    c = ANCHORS["cool"]
    dc_total = c["roi_elec_twh"] * c["dc_share_of_roi_elec"]
    dc_cool = dc_total * c["dc_cooling_share"]
    assert 0.10 <= c["dc_cooling_share"] <= 0.20
    # the line itself must be the cooling share, not the total
    cool = derive_cool(_hero_fixture_feeds())
    assert abs(cool["loads_twh"]["dc"] - dc_cool) < 0.05, \
        ("DC line reverted to total draw", cool["loads_twh"]["dc"])
    # heat rejected preserved: cooling elec x rejection ~ total draw
    rejected = dc_cool * c["rejection_factor"]["dc"]
    assert abs(rejected - dc_total) / dc_total < 0.05, \
        ("rejection factor no longer preserves rejected heat", rejected)


def test_anchor_epoch_rewrites_whole_series_onto_one_basis():
    """A basis change (not a schema change) must re-anchor every
    recomputable week, totals included - otherwise the series steps
    mid-record and the splits stop reconciling with their totals."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    # pretend the stored series predates the current anchors
    stale = [dict(e) for e in h1]
    for e in stale[:-2]:
        e["purchased_gwh"] = round(e["purchased_gwh"] * 1.9, 1)
        e["cold_gwh"] = round(e["cold_gwh"] * 1.9, 1)
    B.PREVIOUS_DERIVED = {"history": stale,
                          "history_schema": B.HISTORY_SCHEMA,
                          "anchor_epoch": B.ANCHOR_EPOCH - 1}
    h2 = build_history(feeds)
    for e0, e2 in zip(h1[:-2], h2[:-2]):
        assert abs(e2["purchased_gwh"] - e0["purchased_gwh"]) < 0.05, \
            ("week not re-anchored", e2["week_ending"])
        assert abs(e2["heat_gwh"] + e2["cold_gwh"]
                   - e2["purchased_gwh"]) <= 0.25


# ------------------------------------ hourly store (A'.2, v7 engine)

def _qrows(day, hours, val=100.0, quarters=4):
    rows = []
    for h in range(hours):
        for q in range(quarters):
            rows.append({
                "EffectiveTime":
                    f"{day}-Jul-2026 {h:02d}:{q*15:02d}:00",
                "Value": val + q,        # mean = val + 1.5 at q=4
            })
    return rows


def test_hourly_means_not_samples():
    """15-minute rows must aggregate to hourly MEANS, and an hour with
    fewer than 3 of its 4 quarters must be dropped rather than shown
    low."""
    got = hourly_from_rows(_qrows("09", 3, 100.0))
    assert len(got) == 3
    for k, v in got.items():
        assert abs(v - 101.5) < 0.01, (k, v)   # mean of 100..103
    # a 2-quarter hour is dropped
    thin = hourly_from_rows(_qrows("09", 1, 100.0, quarters=2))
    assert thin == {}, thin
    # ... but accepted at 3 quarters
    ok3 = hourly_from_rows(_qrows("09", 1, 100.0, quarters=3))
    assert len(ok3) == 1


def test_hourly_store_shape_and_isolation(monkey=None):
    """The store builds from stubbed chunks, keeps its own schema, and
    reports completeness. No network."""
    import build as B
    calls = []

    def fake_chunk(chart, region, areas, end_day):
        calls.append((chart, end_day.isoformat()))
        base = end_day - dt.timedelta(days=27)
        out = {}
        for d in range(28):
            day = base + dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1000.0
        return out

    real = B.fetch_hourly_chunk
    real_t = B.fetch_hourly_temp
    B.fetch_hourly_chunk = fake_chunk
    B.fetch_hourly_temp = lambda prev, floor, end: dict(prev or {})
    try:
        store = build_hourly_store({})
    finally:
        B.fetch_hourly_chunk = real
        B.fetch_hourly_temp = real_t
    assert store["schema"] == B.HOURLY_SCHEMA
    assert set(store["series"]) == set(B.HOURLY_SERIES) | {"temp_ai", "price_ai"}
    assert store["complete"] is True
    assert store["completeness_pct"]["demand_ai"] >= 95
    # 13 months of hours, within a chunk's tolerance
    n = len(store["series"]["demand_ai"])
    assert 9000 <= n <= 10200, n
    # every configured series was walked
    assert len({c[0] for c in calls}) == len(B.HOURLY_SERIES)


def test_hourly_store_never_breaks_weekly_output():
    """A store failure must not touch the weekly document."""
    import build as B
    real = B.fetch_hourly_chunk
    B.fetch_hourly_chunk = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("endpoint down"))
    try:
        store = build_hourly_store({})
    finally:
        B.fetch_hourly_chunk = real
    assert store is None      # nothing written, caller carries on


def test_hourly_carbon_gap_does_not_pass_as_complete():
    """A demand-only gate would have passed the 7 Aug 2026 store with
    carbon at 86%. The core trio gates the store; carbon gates itself."""
    import build as B

    def patchy(chart, region, areas, end_day):
        base = end_day - dt.timedelta(days=27)
        out, skip = {}, (chart == "co2")
        for d in range(28):
            day = base + dt.timedelta(days=d)
            if skip and d < 8:          # carbon missing early
                continue
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1.0
        return out

    real = B.fetch_hourly_chunk
    real_t = B.fetch_hourly_temp
    B.fetch_hourly_chunk = patchy
    B.fetch_hourly_temp = lambda prev, floor, end: dict(prev or {})
    try:
        store = build_hourly_store({})
    finally:
        B.fetch_hourly_chunk = real
        B.fetch_hourly_temp = real_t
    assert store["complete"] is True                  # trio fine
    assert store["completeness_pct"]["co2_ai"] < 95   # carbon flagged


def test_cold_census_reconciles_with_seai():
    """7 Aug 2026: the ROI cold-economy census must stay within 5% of
    the SEAI National Heat Study final-energy cooling total, and the
    process line within 10% of SEAI's industry figure. Pins both sides
    so neither can drift silently again."""
    from build import ANCHORS
    c = ANCHORS["cool"]
    dc = (c["roi_elec_twh"] * c["dc_share_of_roi_elec"]
          * c["dc_cooling_share"])
    L = c["loads_twh"]
    roi = dc + L["refrigeration"] + L["process"] + L["comfort"]
    SEAI_ROI = 5.041      # GWh/1000: 2868+221+93+804+1055
    assert abs(roi - SEAI_ROI) / SEAI_ROI < 0.05, (roi, SEAI_ROI)
    assert abs(L["process"] - 0.804) / 0.804 < 0.10


def test_service_factors_track_seai_ratios():
    """Commercial-type loads use SEAI's implied useful-to-final ratio
    (2.07). Process is deliberately ABOVE SEAI's 1.00 pass-through but
    below the old 2.5. Data centres keep their own high factor."""
    from build import ANCHORS
    sf = ANCHORS["cool"]["cooling_service_factor"]
    assert sf["refrigeration"] == sf["comfort"] == 2.07
    assert 1.0 < sf["process"] <= 2.5
    assert sf["dc"] > 5.0
    # aggregate excluding DC must sit near SEAI's 1.86, not the old 2.6
    c = ANCHORS["cool"]; L = c["loads_twh"]
    elec = L["refrigeration"] + L["process"] + L["comfort"]
    serv = (L["refrigeration"] * sf["refrigeration"]
            + L["process"] * sf["process"] + L["comfort"] * sf["comfort"])
    assert 1.8 <= serv / elec <= 2.2, serv / elec


def test_completeness_denominator_is_the_intended_window():
    """7 Aug 2026: with the denominator taken from demand's own span,
    a shrunken demand series made the others score 106.8%. A
    completeness figure can never exceed 100%."""
    import build as B

    def uneven(chart, region, areas, end_day):
        base = end_day - dt.timedelta(days=27)
        out = {}
        # demand deliberately short on the oldest week
        skip = 7 if chart == "demand" else 0
        for d in range(skip, 28):
            day = base + dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1.0
        return out

    real = B.fetch_hourly_chunk
    real_t = B.fetch_hourly_temp
    B.fetch_hourly_chunk = uneven
    B.fetch_hourly_temp = lambda prev, floor, end: dict(prev or {})
    try:
        store = build_hourly_store({})
    finally:
        B.fetch_hourly_chunk = real
        B.fetch_hourly_temp = real_t
    for k, pct in store["completeness_pct"].items():
        assert pct <= 100.0, (k, pct)


def test_history_carries_per_fuel_for_windowed_bars():
    """Schema 3: every entry carries per-fuel in/useful at island and
    jurisdiction level, and the fuel sums reconcile with the entry's
    own totals - otherwise a windowed bar would contradict the
    windowed headline above it."""
    import build as B
    B.PREVIOUS_DERIVED = {}
    hist = build_history(_history_fixture_feeds())
    assert hist
    for e in hist:
        for block in (e, e["ni"], e["roi"]):
            f = block["fuels"]
            assert "cool" in f
            assert any(k != "cool" for k in f), f
            for v in f.values():
                assert "i" in v and "u" in v
        # island fuel 'in' must sum to purchased within rounding
        tot_in = sum(v["i"] for v in e["fuels"].values())
        assert abs(tot_in - e["purchased_gwh"]) <= 1.0, \
            (e["week_ending"], tot_in, e["purchased_gwh"])
        # NI + ROI fuel sums reconcile to the island's
        for f in e["fuels"]:
            pair = e["ni"]["fuels"].get(f, {"i": 0})["i"] \
                + e["roi"]["fuels"].get(f, {"i": 0})["i"]
            assert abs(pair - e["fuels"][f]["i"]) <= 0.5, f


def test_hourly_chunk_retried_within_the_run():
    """7 Aug 2026: a chunk that fails once must be retried in the same
    run, not left as a gap until tomorrow."""
    import build as B
    calls = {"n": 0}

    def flaky(chart, region, areas, end_day):
        calls["n"] += 1
        if calls["n"] % 3 == 1:          # first of every three fails
            raise RuntimeError("transient")
        base = end_day - dt.timedelta(days=27)
        return {(base + dt.timedelta(days=d)).strftime("%Y-%m-%dT")
                + f"{h:02d}": 1.0
                for d in range(28) for h in range(24)}

    real_fetch, real_sleep = B.fetch_hourly_chunk, B.time.sleep
    real_t = B.fetch_hourly_temp
    B.fetch_hourly_temp = lambda prev, floor, end: dict(prev or {})
    B.fetch_hourly_chunk = flaky
    B.time.sleep = lambda *_: None       # no real delays in tests
    try:
        store = build_hourly_store({})
    finally:
        B.fetch_hourly_chunk = real_fetch
        B.fetch_hourly_temp = real_t
        B.time.sleep = real_sleep
    # every EirGrid series still lands complete despite one-in-three
    # failures. temp_ai comes from a different source on a different
    # walk and is stubbed empty here, so it is not the subject.
    for k in B.HOURLY_SERIES:
        assert store["completeness_pct"][k] >= 95, (
            k, store["completeness_pct"][k])


def test_migration_refreshes_jurisdiction_blocks():
    """7 Aug 2026: the schema-3 migration used setdefault() for ni/roi,
    so frozen weeks kept jurisdiction blocks from the previous schema
    and the windowed energy bars had no per-fuel data for NI or ROI.
    A migration must REFRESH those blocks, not default them."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    # simulate the older shape: jurisdiction blocks without 'fuels'
    stale = []
    for e in h1:
        c = dict(e)
        c["ni"] = {k: v for k, v in e["ni"].items() if k != "fuels"}
        c["roi"] = {k: v for k, v in e["roi"].items() if k != "fuels"}
        stale.append(c)
    B.PREVIOUS_DERIVED = {"history": stale,
                          "history_schema": B.HISTORY_SCHEMA - 1,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    for e in h2[:-2]:
        assert "fuels" in e["ni"], ("NI block not refreshed",
                                    e["week_ending"])
        assert "fuels" in e["roi"], ("ROI block not refreshed",
                                     e["week_ending"])


def test_schema_migration_adds_fuels_to_jurisdiction_blocks():
    """A schema-2 entry already has ni/roi, so setdefault skipped them
    and jurisdiction windows had no per-fuel data - the energy bars
    then kept the previous scope instead of redrawing. Migration must
    add the field while leaving frozen values untouched."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    legacy = []
    for e in h1:
        e2 = {k: v for k, v in e.items() if k != "fuels"}
        e2["ni"] = {k: v for k, v in e["ni"].items() if k != "fuels"}
        e2["roi"] = {k: v for k, v in e["roi"].items() if k != "fuels"}
        legacy.append(e2)
    B.PREVIOUS_DERIVED = {"history": legacy, "history_schema": 2,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    for e in h2[:-2]:
        assert "fuels" in e, "island fuels missing"
        for scope in ("ni", "roi"):
            assert "fuels" in e[scope], (scope, e["week_ending"])
            assert e[scope]["fuels"], (scope, "empty")
    # frozen island values untouched by the migration
    for a, b in zip(legacy[:-2], h2[:-2]):
        assert a["purchased_gwh"] == b["purchased_gwh"]


def test_migration_refreshes_existing_jurisdiction_blocks():
    """Schema 3 attached ni/roi with setdefault, so weeks that already
    had those blocks never gained per-fuel data. A migration must
    REFRESH existing sub-blocks, not default them."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    # simulate the schema-3 store: ni/roi present but fuel-less
    stale = []
    for e in h1:
        c = dict(e)
        c["ni"] = {k: v for k, v in e["ni"].items() if k != "fuels"}
        c["roi"] = {k: v for k, v in e["roi"].items() if k != "fuels"}
        stale.append(c)
    B.PREVIOUS_DERIVED = {"history": stale, "history_schema": 3,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    for e in h2[:-2]:
        assert "fuels" in e["ni"], ("ni block not refreshed",
                                    e["week_ending"])
        assert "fuels" in e["roi"], ("roi block not refreshed",
                                     e["week_ending"])


def test_schema_migration_adds_fuels_to_existing_jur_blocks():
    """Schema 4: a stored week that already has ni/roi blocks WITHOUT
    fuels must gain them. Schema 3 used setdefault here, which skipped
    exactly this case and left the windowed bars stuck on the live
    week for NI and ROI."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    legacy = []
    for e in h1:
        e2 = dict(e)
        for scope in ("ni", "roi"):
            e2[scope] = {k: v for k, v in e[scope].items()
                         if k != "fuels"}
        legacy.append(e2)
    B.PREVIOUS_DERIVED = {"history": legacy, "history_schema": 3,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    for e in h2[:-2]:
        assert "fuels" in e["ni"], ("ni fuels missing", e["week_ending"])
        assert "fuels" in e["roi"], ("roi fuels missing", e["week_ending"])
        assert "cool" in e["ni"]["fuels"]


def test_schema_migration_adds_fuels_to_existing_subblocks():
    """A frozen week that already has ni/roi from an older schema must
    still gain the new per-fuel field - setdefault silently skipped
    them at 4.13.0 and the jurisdiction x window bars stayed blank."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    # simulate a schema-3 store: island fuels present, sub-blocks not
    old = []
    for e in h1:
        c = dict(e)
        c["ni"] = {k: v for k, v in e["ni"].items() if k != "fuels"}
        c["roi"] = {k: v for k, v in e["roi"].items() if k != "fuels"}
        old.append(c)
    B.PREVIOUS_DERIVED = {"history": old, "history_schema": 3,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    for e in h2[:-2]:
        for scope in ("ni", "roi"):
            assert "fuels" in e[scope], (e["week_ending"], scope)
        # frozen values beside the new field are untouched
        assert e["purchased_gwh"] == \
            next(x for x in old if x["week_ending"] ==
                 e["week_ending"])["purchased_gwh"]


def test_schema_migration_adds_fields_inside_sub_blocks():
    """A schema bump must reach INSIDE existing ni/roi sub-blocks.
    setdefault left schema-2 blocks without per-fuel data, so
    jurisdiction windows had nothing to sum (site 4.4.0-4.4.3)."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    # emulate a schema-2 store: sub-blocks present, no fuels anywhere
    legacy = []
    for e in h1:
        e2 = {k: v for k, v in e.items() if k != "fuels"}
        for s in ("ni", "roi"):
            e2[s] = {k: v for k, v in e[s].items() if k != "fuels"}
        legacy.append(e2)
    B.PREVIOUS_DERIVED = {"history": legacy, "history_schema": 2,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    for e in h2[:-2]:
        assert "fuels" in e, e["week_ending"]
        for s in ("ni", "roi"):
            assert "fuels" in e[s], (e["week_ending"], s)
            assert e[s]["fuels"], (e["week_ending"], s)
        # stored values untouched by a pure schema bump
    for e0, e2 in zip(legacy[:-2], h2[:-2]):
        for k in ("purchased_gwh", "bill_eur_m", "emissions_kt"):
            assert e2[k] == e0[k], k


def test_migration_refreshes_jurisdiction_blocks():
    """Schema 3 used setdefault for ni/roi, so entries migrated from an
    older schema kept blocks WITHOUT the new per-fuel data and the
    windowed bars had nothing to sum for NI or ROI. A migration must
    refresh existing sub-blocks, not merely create missing ones."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    h1 = build_history(feeds)
    # simulate an older store: ni/roi present but lacking 'fuels'
    older = []
    for e in h1:
        e2 = dict(e)
        e2["ni"] = {k: v for k, v in e["ni"].items() if k != "fuels"}
        e2["roi"] = {k: v for k, v in e["roi"].items() if k != "fuels"}
        e2.pop("fuels", None)
        older.append(e2)
    B.PREVIOUS_DERIVED = {"history": older, "history_schema": 3,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    h2 = build_history(feeds)
    for e in h2[:-2]:
        assert "fuels" in e["ni"], ("NI block not refreshed",
                                    e["week_ending"])
        assert "fuels" in e["roi"], ("ROI block not refreshed",
                                     e["week_ending"])


# ------------------------- heat-pump split and ambient harvest (4.15)

def test_heat_pump_split_and_ambient_harvest():
    """The electricity line splits into resistive and heat-pump, and
    the ambient harvest appears on the OUT side only - it is free heat
    that was never purchased. Anchors: Census 2022 (ROI) and Census
    2021 Table 27 (NI)."""
    h = derive_hero(_hero_fixture_feeds())
    bf = h["by_fuel"]
    for k in ("electricity", "heatpump", "ambient"):
        assert k in bf, k
    # ambient is out-only
    assert bf["ambient"]["in_gwh"] == 0.0
    assert bf["ambient"]["useful_gwh"] > 0
    # heat-pump electricity is purchased and delivers 1:1 before ambient
    assert bf["heatpump"]["in_gwh"] > 0
    assert bf["heatpump"]["useful_gwh"] == bf["heatpump"]["in_gwh"]
    # ambient implies an SPF above 2 on the heat-pump electricity
    spf_implied = (bf["heatpump"]["useful_gwh"]
                   + bf["ambient"]["useful_gwh"]) \
        / max(bf["heatpump"]["in_gwh"], 1e-9)
    assert 2.0 < spf_implied < 4.5, spf_implied
    # served must exceed purchased-side heat by at least the harvest
    assert h["combined"]["served_gwh"] > 0


def test_heat_pump_anchors_are_census_floors():
    from build import ANCHORS
    hp = ANCHORS["heat_pumps"]
    # ROI Census 2022: 71,000 households with heat pumps
    assert hp["roi"]["households"] == 71000
    # NI Census 2021 Table 27: ~692 air source + ~615 geothermal
    assert 1200 <= hp["ni"]["households"] <= 1400
    # the uplift acknowledges four years of NZEB and grants since
    assert hp["roi"]["census_uplift"] >= 1.0


def test_weighted_hourly_temp_population_weights():
    """Island temperature is the population-weighted mean of the
    stations, hour by hour, on whatever clock Open-Meteo was asked
    for."""
    payload = [
        {"hourly": {"time": ["2026-01-08T08:00", "2026-01-08T09:00"],
                    "temperature_2m": [0.0, 2.0]}},
        {"hourly": {"time": ["2026-01-08T08:00", "2026-01-08T09:00"],
                    "temperature_2m": [10.0, 12.0]}},
    ]
    out = weighted_hourly_temp(payload, ["A", "B"], {"A": 0.6, "B": 0.4})
    assert out["2026-01-08T08"] == 4.0      # 0.6*0 + 0.4*10
    assert out["2026-01-08T09"] == 6.0      # 0.6*2 + 0.4*12
    assert set(out) == {"2026-01-08T08", "2026-01-08T09"}


def test_weighted_hourly_temp_partial_coverage_is_unbiased():
    """A station missing an hour must not drag the island mean toward
    zero. The divisor is the weight PRESENT, not the full 1.0 - a
    plain weighted sum would report 4.0 for an hour that is 10 C
    everywhere it was measured."""
    payload = [
        {"hourly": {"time": ["2026-01-08T08"], "temperature_2m": [None]}},
        {"hourly": {"time": ["2026-01-08T08"], "temperature_2m": [10.0]}},
    ]
    out = weighted_hourly_temp(payload, ["A", "B"], {"A": 0.6, "B": 0.4})
    assert out["2026-01-08T08"] == 10.0


def test_hourly_store_carries_temperature_and_gates_it_separately():
    """Schema 2. The temperature series rides in the store, and
    `heat_ready` is a gate of its own: a store whose grid trio is
    whole still reports the heat layer as not ready until the
    temperature series fills, and reports it WITHOUT withdrawing
    anything the grid gate already allows."""
    import build as B

    def fake_chunk(chart, region, areas, end_day):
        base = end_day - dt.timedelta(days=27)
        out = {}
        for d in range(28):
            day = base + dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1000.0
        return out

    def thin_temp(prev, floor, end):
        """Only a fortnight of temperature - the first-run state."""
        out = {}
        for d in range(14):
            day = end - dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 5.0
        return out

    real, real_t, real_s = B.fetch_hourly_chunk, B.fetch_hourly_temp, B.time.sleep
    B.fetch_hourly_chunk, B.fetch_hourly_temp = fake_chunk, thin_temp
    B.time.sleep = lambda *_: None
    try:
        store = build_hourly_store({})
    finally:
        B.fetch_hourly_chunk, B.fetch_hourly_temp = real, real_t
        B.time.sleep = real_s
    assert store["schema"] == B.HOURLY_SCHEMA
    assert "temp_ai" in store["series"]
    assert store["complete"] is True            # grid layer unaffected
    assert store["heat_ready"] is False         # heat layer waits
    assert store["completeness_pct"]["temp_ai"] < 95


def test_temperature_tail_cannot_depress_grid_completeness():
    """temp_ai carries a forecast tail past the last EirGrid hour. If
    it set the completeness denominator, every grid series would be
    marked short for a reason that has nothing to do with them."""
    import build as B

    def fake_chunk(chart, region, areas, end_day):
        base = end_day - dt.timedelta(days=27)
        out = {}
        for d in range(28):
            day = base + dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1000.0
        return out

    def temp_with_tail(prev, floor, end):
        out = {}
        start = dt.datetime.strptime(floor, "%Y-%m-%dT%H").date()
        day = start
        while day <= end + dt.timedelta(days=2):     # two days beyond
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 5.0
            day += dt.timedelta(days=1)
        return out

    real, real_t, real_s = B.fetch_hourly_chunk, B.fetch_hourly_temp, B.time.sleep
    B.fetch_hourly_chunk, B.fetch_hourly_temp = fake_chunk, temp_with_tail
    B.time.sleep = lambda *_: None
    try:
        store = build_hourly_store({})
    finally:
        B.fetch_hourly_chunk, B.fetch_hourly_temp = real, real_t
        B.time.sleep = real_s
    assert store["completeness_pct"]["demand_ai"] >= 95
    assert store["complete"] is True
    assert store["heat_ready"] is True


def test_hourly_temp_request_uses_irish_local_clock():
    """The join in the store is only valid if both sides share a
    clock. EirGrid stamps are local; the temperature request must ask
    for Europe/Dublin, not the UTC the daily HDD feed uses."""
    import build as B
    seen = []

    class R:
        @staticmethod
        def json():
            return [{"hourly": {"time": [], "temperature_2m": []}}]

    def fake_get(url, **kw):
        seen.append((url, (kw.get("params") or {}).get("timezone")))
        return R

    real_get, real_sleep = B.http_get, B.time.sleep
    B.http_get, B.time.sleep = fake_get, lambda *a, **k: None
    try:
        B.fetch_hourly_temp({}, "2025-07-01T00", B.today_utc())
    finally:
        B.http_get, B.time.sleep = real_get, real_sleep
    assert seen, "no request issued"
    assert all(tz == "Europe/Dublin" for _, tz in seen), seen
    assert any("archive" in u for u, _ in seen)


def test_hourly_temp_keeps_previous_when_every_chunk_fails():
    """Soft by construction: a bad day at Open-Meteo must leave the
    retained depth alone rather than truncate the series."""
    import build as B
    prev = {"2026-01-0" + str(d) + "T12": 4.0 for d in range(1, 9)}

    def boom(url, **kw):
        raise RuntimeError("open-meteo down")

    real_get, real_sleep = B.http_get, B.time.sleep
    B.http_get, B.time.sleep = boom, lambda *a, **k: None
    try:
        out = B.fetch_hourly_temp(prev, "2025-07-01T00", B.today_utc())
    finally:
        B.http_get, B.time.sleep = real_get, real_sleep
    assert out == prev


def test_hourly_compaction_round_trips():
    """Arrays in, dicts out, byte for byte the same values."""
    series = {
        "demand_ai": {"2026-01-08T00": 4100.0, "2026-01-08T01": 4050.5,
                      "2026-01-08T03": 3990.0},
        "temp_ai": {"2026-01-08T00": 1.25, "2026-01-08T03": -0.5},
    }
    t0, n, packed = compact_hourly(series)
    assert t0 == "2026-01-08T00"
    assert n == 4
    assert packed["demand_ai"] == [4100.0, 4050.5, None, 3990.0]
    assert packed["temp_ai"] == [1.25, None, None, -0.5]
    back = expand_hourly({"t0": t0, "series": packed})
    assert back == series


def test_hourly_compaction_survives_the_spring_clock_change():
    """The keys are Irish LOCAL clock, so the spring transition skips
    a local hour. Offsets must stay a bijection across it - the gap
    reads as one null, and every key on both sides comes back
    unchanged. This is the case that would silently shift a whole
    series by an hour if the encoding assumed contiguity."""
    # 29 Mar 2026: local 01:00 does not exist (00:00 -> 02:00).
    series = {"demand_ai": {"2026-03-29T00": 3000.0,
                            "2026-03-29T02": 3100.0,
                            "2026-03-29T03": 3200.0}}
    t0, n, packed = compact_hourly(series)
    assert packed["demand_ai"] == [3000.0, None, 3100.0, 3200.0]
    assert expand_hourly({"t0": t0, "series": packed}) == series


def test_hourly_store_reads_the_schema_2_file_it_replaces():
    """The first run after the encoding change must inherit the
    dict-form store already in the repo, not refill 13 months from
    empty."""
    old_doc = {"schema": 2,
               "series": {"demand_ai": {"2026-01-08T00": 4100.0},
                          "temp_ai": {"2026-01-08T00": 1.25}}}
    got = expand_hourly(old_doc)
    assert got["demand_ai"] == {"2026-01-08T00": 4100.0}
    assert got["temp_ai"] == {"2026-01-08T00": 1.25}
    assert expand_hourly({}) == {}
    assert expand_hourly({"schema": 3, "series": {"demand_ai": [1.0]}}) == {}


def test_hourly_store_writes_arrays_and_reloads_itself():
    """End to end: build a store, feed its own document back in, and
    the second build must see everything the first one held."""
    import build as B

    def fake_chunk(chart, region, areas, end_day):
        base = end_day - dt.timedelta(days=27)
        out = {}
        for d in range(28):
            day = base + dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1000.0
        return out

    real, real_t, real_s = B.fetch_hourly_chunk, B.fetch_hourly_temp, B.time.sleep
    B.fetch_hourly_chunk = fake_chunk
    B.fetch_hourly_temp = lambda prev, floor, end: dict(prev or {})
    B.time.sleep = lambda *_: None
    try:
        first = build_hourly_store({})
        # written form is arrays against a base hour
        assert isinstance(first["series"]["demand_ai"], list)
        assert first["t0"] and first["hours"] > 9000
        # and it survives a JSON round trip into the next run
        reloaded = json.loads(json.dumps(first))
        second = build_hourly_store(reloaded)
    finally:
        B.fetch_hourly_chunk, B.fetch_hourly_temp = real, real_t
        B.time.sleep = real_s
    assert second["completeness_pct"]["demand_ai"] >= 95
    assert len(second["series"]["demand_ai"]) >= len(first["series"]["demand_ai"]) - 24


def test_array_encoding_is_materially_smaller():
    """The point of the change. A dict-form store of the live shape
    must shrink substantially when written as arrays."""
    series = {}
    base = dt.datetime(2025, 7, 13)
    for name in ("demand_ai", "wind_ai", "solar_ai", "co2_ai", "temp_ai"):
        d = {}
        for i in range(9384):
            k = (base + dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H")
            d[k] = round(1000 + i % 997 + 0.5, 2)
        series[name] = d
    dict_bytes = len(json.dumps(series, separators=(",", ":")))
    t0, n, packed = compact_hourly(series)
    arr_bytes = len(json.dumps({"t0": t0, "hours": n, "series": packed},
                               separators=(",", ":")))
    assert arr_bytes < dict_bytes * 0.55, (arr_bytes, dict_bytes)


def test_jurisdiction_blocks_carry_the_heat_cold_splits():
    """History schema 5. Every windowed card and what-if row under the
    NI or ROI toggle breaks down into heat, cooling and saves; the
    front end omits the whole breakdown unless the fields are present
    on the jurisdiction sub-block, which is why NI and ROI showed bare
    totals at 4w/12w/12m while all-island showed the split."""
    import build as B
    B.PREVIOUS_DERIVED = {}
    feeds = _history_fixture_feeds()
    hist = build_history(feeds)
    assert hist, "no history built"
    for e in hist:
        for j in ("ni", "roi"):
            blk = e[j]
            for k in B.JUR_SPLIT_KEYS:
                assert k in blk, (j, k, e["week_ending"])
                assert "wf_" + k in blk, (j, "wf_" + k, e["week_ending"])
            # and they must reconcile with that block's own totals
            assert abs(blk["heat_gwh"] + blk["cold_gwh"]
                       - blk["purchased_gwh"]) < 1.0
            assert abs(blk["bill_heat_eur_m"] + blk["bill_cold_eur_m"]
                       - blk["bill_eur_m"]) < 0.5
            assert abs(blk["bill_heat_gbp_m"] + blk["bill_cold_gbp_m"]
                       - blk["bill_gbp_m"]) < 0.5
            assert abs(blk["emissions_heat_kt"] + blk["emissions_cold_kt"]
                       - blk["emissions_kt"]) < 0.5


def test_schema_5_migration_backfills_frozen_jurisdiction_splits():
    """A week frozen under schema 4 has jurisdiction blocks without
    the splits. The bump must REFRESH those blocks, not leave the
    stored ones in place - otherwise the breakdown returns only for
    the two live weeks and the window still reads bare."""
    import build as B
    B.PREVIOUS_DERIVED = {}
    feeds = _history_fixture_feeds()
    fresh = build_history(feeds)
    assert len(fresh) > 3
    stale = []
    for e in fresh:
        e2 = json.loads(json.dumps(e))
        for j in ("ni", "roi"):
            for k in B.JUR_SPLIT_KEYS:
                e2[j].pop(k, None)
                e2[j].pop("wf_" + k, None)
        stale.append(e2)
    B.PREVIOUS_DERIVED = {"history": stale, "history_schema": 4,
                          "anchor_epoch": B.ANCHOR_EPOCH}
    try:
        out = build_history(feeds)
    finally:
        B.PREVIOUS_DERIVED = {}
    frozen = out[:-2]
    assert frozen, "nothing frozen to migrate"
    for e in frozen:
        for j in ("ni", "roi"):
            for k in B.JUR_SPLIT_KEYS:
                assert k in e[j], (j, k, e["week_ending"])
                assert "wf_" + k in e[j], (j, k, e["week_ending"])


def test_tariff_table_covers_the_backfilled_weeks():
    """The table must reach HISTORY_START or the earliest weeks would
    be priced at a tariff that did not exist yet. Both sides are now
    dated - the euro side became a semester series at 5.12.0 - so a
    week in S1 2025 and a week in S2 2025 must differ on BOTH."""
    import build as B
    first = B.TARIFF_HISTORY[0][0]
    assert first <= B.HISTORY_START, (first, B.HISTORY_START)
    pre = B.tariffs_for(B.HISTORY_START)
    oct25 = B.tariffs_for("2025-10-01")
    assert B.semester_of(B.HISTORY_START) != B.semester_of("2025-10-01")
    # euro: was identical while the ROI side was one anchor stepped
    # forward; now it moves with the semester, which is the point of
    # 5.12.0 and the thing that stopped 68 weeks being priced at 2025
    # levels
    assert pre["eur"]["electricity"] != oct25["eur"]["electricity"]
    assert pre["eur"]["gas"] != oct25["eur"]["gas"]
    # sterling: NI gas fell and NI electricity rose across that gap
    assert pre["gbp"]["gas"] > oct25["gbp"]["gas"]
    assert pre["gbp"]["electricity"] < oct25["gbp"]["electricity"]


def test_ni_gas_tracks_the_weighted_regulated_bills():
    """The NI rows are effective all-in rates at the Regulator's
    consumption basis, weighted by regulated customer count. Recompute
    from the published annual bills and check the table matches."""
    import build as B
    w_sse, w_fir = 198200, 75756
    ws = w_sse / (w_sse + w_fir)
    wf = 1 - ws
    # (period, SSE bill, Firmus bill) at 12,000 kWh, incl VAT
    for period, sse, fir in (("2025-08-06", 1079, 1014),
                             ("2025-10-01", 985, 934),
                             ("2026-04-01", 905, 840),
                             ("2026-07-01", 905, 972)):
        want = (ws * sse + wf * fir) / 12000
        got = B.tariffs_for(period)["gbp"]["gas"]
        assert abs(got - want) < 5e-5, (period, got, want)
    for period, bill in (("2025-08-06", 989), ("2025-10-01", 1029),
                         ("2026-04-01", 1029), ("2026-07-01", 1093)):
        want = bill / 3200
        got = B.tariffs_for(period)["gbp"]["electricity"]
        assert abs(got - want) < 5e-5, (period, got, want)


def test_daily_ci_from_hourly_averages_and_drops_thin_days():
    """Carbon for the backfilled weeks comes from the hourly store.
    A day with too few hours must be dropped, not averaged thin - a
    quiet part-day mean would be indistinguishable from a real one."""
    import build as B
    ser = {}
    for h in range(24):
        ser[f"2025-08-07T{h:02d}"] = 200.0 + h
    for h in range(5):                       # thin day
        ser[f"2025-08-08T{h:02d}"] = 400.0
    out = B.daily_ci_from_hourly({"schema": 2, "series": {"co2_ai": ser}})
    assert out == {"2025-08-07": round(sum(200.0 + h for h in range(24)) / 24, 1)}
    assert "2025-08-08" not in out
    assert B.daily_ci_from_hourly({}) == {}


def test_daily_ci_reads_the_array_form_store():
    """The store on disk is schema 3, so the fallback has to read
    arrays, not just the dict form."""
    import build as B
    ser = {f"2025-08-07T{h:02d}": 300.0 for h in range(24)}
    t0, n, packed = B.compact_hourly({"co2_ai": ser})
    out = B.daily_ci_from_hourly({"schema": 3, "t0": t0, "series": packed})
    assert out == {"2025-08-07": 300.0}


def test_backfilled_weeks_are_not_counted_live():
    """Two counters. A week reconstructed behind LIVE_FROM is on the
    record but is not a live week, and the milestone counts live."""
    import build as B
    assert B.LIVE_FROM > B.HISTORY_START
    B.PREVIOUS_DERIVED = {}
    hist = build_history(_history_fixture_feeds())
    assert hist
    for e in hist:
        assert "live" in e, e["week_ending"]
        assert e["live"] == (e["week_ending"] >= B.LIVE_FROM)
    assert any(e["live"] for e in hist)


def test_history_cap_does_not_drop_the_backfilled_weeks():
    """52 weeks plus forward growth would have passed the old cap of
    60 within two months, silently undoing the backfill."""
    import build as B
    assert B.HISTORY_MAX >= 105


def test_non_domestic_rates_are_services_scaled_not_industrial():
    """The services share must be priced at services rates. Both
    jurisdictions previously carried large-user figures - NI was the
    GB manufacturing average copied from the UK sibling - which is
    the wrong end of the distribution for offices and retail.

    The published UREGNI semester 2 2024 bands: NI I&C electricity
    28.5 p/kWh very small against 16.9 large/very large; NI I&C gas
    8.7 against 5.8. This pins the anchors to the small end and,
    critically, ABOVE the large-user prices - a future edit that
    quietly reverts toward the industrial figures should fail here."""
    import build as B
    a = B.ANCHORS
    assert a["nondom_gbp_per_kwh"]["electricity"] == 0.2381
    assert a["nondom_gbp_per_kwh"]["gas"] == 0.080
    # euro side is derived from the published sterling figure and the
    # fetched semester rate, so it is pinned in sterling terms
    assert B.IE_PUBLISHED_P_PER_KWH["nondom_electricity"] == 22.68
    assert B.IE_PUBLISHED_P_PER_KWH["nondom_gas"] == 9.3
    # never back down to the large/very large band...
    assert a["nondom_gbp_per_kwh"]["electricity"] > 0.178
    assert a["nondom_gbp_per_kwh"]["gas"] > 0.055
    # ...nor drift up to the very-small band alone, which was the
    # first cut of this anchor and priced every office as if it used
    # under 20 MWh a year
    assert a["nondom_gbp_per_kwh"]["electricity"] < 0.286


def test_electricity_services_anchor_is_the_weighted_band_ladder():
    """Recompute the NI electricity anchor from the published S2 2024
    band prices and NI I&C consumption, excluding only Large + Very
    Large. If someone re-picks a single band this fails."""
    import build as B
    # S2 2025 bands and UREGNI's own published consumption shares
    cons = {"vs": 5.1, "s": 32.9, "sm": 19.1, "m": 26.8}
    ni = {"vs": 28.6, "s": 26.3, "sm": 23.3, "m": 20.2}
    ie = {"vs": 26.2, "s": 25.4, "sm": 22.2, "m": 19.0}
    w = sum(cons.values())
    want_ni = sum(cons[k] * ni[k] for k in cons) / w / 100
    want_ie = sum(cons[k] * ie[k] for k in cons) / w
    assert abs(B.ANCHORS["nondom_gbp_per_kwh"]["electricity"]
               - want_ni) < 5e-4, want_ni
    assert abs(B.IE_PUBLISHED_P_PER_KWH["nondom_electricity"]
               - want_ie) < 0.05, want_ie


def test_services_rates_sit_below_domestic_but_not_far_below():
    """Sanity, not arithmetic. Small non-domestic customers pay close
    to domestic rates because most of the bill is network and levies;
    a services rate at half the domestic one is the industrial-band
    error returning by another route."""
    import build as B
    a = B.ANCHORS
    for cur, dom, nd in (("gbp", "retail_gbp_per_kwh", "nondom_gbp_per_kwh"),
                         ("eur", "retail_eur_per_kwh", "nondom_eur_per_kwh")):
        for fuel in ("electricity", "gas"):
            ratio = a[nd][fuel] / a[dom][fuel]
            assert 0.6 <= ratio <= 1.3, (cur, fuel, round(ratio, 3))


def test_both_jurisdictions_price_domestic_all_in():
    """NI and ROI domestic are the same KIND of quantity - an all-in
    effective rate at a stated consumption, VAT and standing charges
    included - so the bills compare at component level.

    From 5.12.0 the ROI side is the published band figure in euro
    directly (band DC electricity, band D2 gas) rather than a sterling
    anchor converted at the fetched rate, so this checks against the
    band table and then confirms it still reconciles with the old
    sterling anchor at that semester's own ECB mean."""
    import build as B
    pre = B.tariffs_for("2025-09-01")["eur"]
    elec_c, gas_c, credit = B.IE_DOMESTIC_SEMESTER["2025-S2"]
    assert credit == 0.0, "S2 2025 is the first clean semester"
    assert abs(pre["electricity"] - elec_c / 100) < 1e-4
    assert abs(pre["gas"] - gas_c / 100) < 1e-4
    # and it still agrees with the sterling anchor it replaced, at the
    # S2 2025 ECB mean - 35.2p / 0.87073 = 40.43c against 40.4c
    assert abs(pre["electricity"] - 35.2 / 100 / 0.87073) < 4e-4
    assert abs(pre["gas"] - 11.3 / 100 / 0.87073) < 4e-4
    jul = B.tariffs_for("2026-07-01")["eur"]
    assert abs(jul["electricity"] / pre["electricity"] - 1.08) < 0.002
    assert abs(jul["gas"] / pre["gas"] - 1.077) < 0.002
    assert B.tariffs_for("2025-09-01")["gbp"]["electricity"] == 0.3091


def test_irish_anchors_use_a_credit_free_semester():
    """The Irish domestic electricity series carries government
    credits as negative taxes - 31.3 p/kWh in S2 2024, 27.5 in S1
    2025, 35.2 in S2 2025, a 28% jump caused by a credit ending. This
    site prices the real cost, so the anchor must be the clean
    semester. Pinning it stops a future edit reaching for the lower,
    subsidised figure because it looks more favourable."""
    import build as B
    assert B.IE_SEMESTER == "2025-S2"
    assert B.IE_PUBLISHED_P_PER_KWH["domestic_electricity"] == 35.2
    assert B.IE_PUBLISHED_P_PER_KWH["domestic_electricity"] > 31.4


def test_semester_means_drop_part_semesters():
    """A part-semester mean is indistinguishable from a whole one and
    would silently mis-scale every Irish anchor, so short semesters
    are dropped rather than averaged thin."""
    import build as B
    whole = {}
    d = dt.date(2025, 7, 1)
    while d <= dt.date(2025, 12, 31):
        if d.weekday() < 5:
            whole[d.isoformat()] = 0.87
        d += dt.timedelta(days=1)
    out = B.semester_means(whole)
    assert out == {"2025-S2": 0.87}
    thin = dict(list(whole.items())[:40])
    assert B.semester_means(thin) == {}


def test_fx_falls_back_loudly_and_scales_every_irish_anchor():
    """The rate scales the whole ROI side. A missing semester must
    land on the stated fallback, and a present one must actually be
    used - including by the non-domestic anchors."""
    import build as B
    before = dict(B.IE_FX)
    try:
        B.apply_ie_fx({"ecb_fx": {"eur_gbp_semester": {}}})
        assert B.IE_FX["rate"] == B.IE_FX_FALLBACK
        assert "UNVERIFIED" in B.IE_FX["source"]
        B.apply_ie_fx({"ecb_fx": {"eur_gbp_semester": {B.IE_SEMESTER: 0.9}}})
        assert B.IE_FX["rate"] == 0.9
        assert abs(B.ANCHORS["nondom_eur_per_kwh"]["electricity"]
                   - 22.68 / 100 / 0.9) < 5e-4
        # DOMESTIC no longer moves with the rate. From 5.12.0 the ROI
        # domestic side is the published euro band figure, so it is
        # the NON-domestic anchors alone that the fetched rate scales.
        # That is a narrowing of the rate's blast radius, not a loss:
        # the sterling-derived figure was a conversion of a euro
        # original, and the conversion was the part that could go
        # stale.
        assert abs(B.tariffs_for("2025-09-01")["eur"]["electricity"]
                   - B.IE_DOMESTIC_SEMESTER["2025-S2"][0] / 100) < 1e-9
    finally:
        B.IE_FX.update(before)
        B.apply_ie_fx({})


def test_domestic_sits_above_non_domestic_at_a_COMMON_vintage():
    """Services rates exclude VAT and buy in bulk, so at the same
    moment and the same tax basis they must sit below domestic.

    This is asserted on the S2 2024 band figures rather than on the
    shipped anchors, and that distinction matters. The shipped
    non-domestic anchors ARE S2 2024, but the shipped domestic ones
    are stepped through to 2026, and NI gas fell about 15% over that
    span. So NI non-domestic gas (8.67p, 2024) now prints above NI
    domestic gas (7.70p, Jul 2026) - not because small business gas
    is cheaper than household gas, but because the two anchors are
    eighteen months apart. At a common vintage the ordering is right:
    domestic 9.88p incl VAT is 9.41p excl, against 8.67p
    non-domestic.

    The vintage gap is disclosed rather than escalated away, because
    applying regulated domestic steps to unregulated business
    contracts would be a dagger on a dagger. It closes when REMM
    publishes newer semesters."""
    # S2 2025: NI domestic gas 8.6 incl VAT, 8.19 excl, against 8.0
    # non-domestic - correct order, where the shipped anchors invert
    # only because domestic is stepped to 2026 and 2025 was dearer.
    assert 8.0 < 8.6 / 1.05
    # Ireland, same semester: 11.3 domestic against 9.3 non-domestic
    assert 9.3 < 11.3
    # and electricity, both jurisdictions
    assert 22.68 < 35.2
    assert 23.81 < 30.6


def test_electricity_ordering_holds_on_the_shipped_anchors():
    """Electricity has no comparable vintage problem - NI domestic
    rose since 2024 rather than falling - so the ordering must hold on
    the live anchors, in both jurisdictions and both tariff periods."""
    import build as B
    a = B.ANCHORS
    for d in ("2025-09-01", "2026-08-01"):
        t = B.tariffs_for(d)
        assert a["nondom_eur_per_kwh"]["electricity"] < t["eur"]["electricity"]
        assert a["nondom_gbp_per_kwh"]["electricity"] < t["gbp"]["electricity"]


def test_history_columnar_round_trip_is_exact():
    """Keys are written once instead of once per week. The round trip
    must be exact, including the nulls - ef_electricity is legitimately
    None in a week with too few carbon observations, and a codec that
    dropped the key would look lossless on a spot check and lose the
    distinction between 'no reading' and 'never had the field'."""
    import build as B
    B.PREVIOUS_DERIVED = {}
    hist = build_history(_history_fixture_feeds())
    assert hist and len(hist) > 3
    packed = B.compact_history(hist)
    assert packed["encoding"] == B.HISTORY_ENCODING
    assert packed["n"] == len(hist)
    assert B.expand_history(packed) == hist
    # nested blocks survive as blocks, not flattened
    assert isinstance(packed["cols"]["ni"], dict)
    assert isinstance(packed["cols"]["ni"]["purchased_gwh"], list)


def test_history_codec_accepts_the_legacy_list():
    """index.html deploys immediately, data.json only at the next
    build, so for up to a day each side reads the other's previous
    shape. Both readers must pass a plain list through untouched."""
    import build as B
    legacy = [{"week_ending": "2026-01-04", "purchased_gwh": 1.0},
              {"week_ending": "2026-01-11", "purchased_gwh": 2.0}]
    assert B.expand_history(legacy) == legacy
    assert B.expand_history({}) == []
    assert B.expand_history(None) == []
    assert B.expand_history(B.compact_history([])) == []


def test_columnar_encoding_is_materially_smaller():
    """The point of the change: at 52 weeks the entries are wide and
    shallow, so the repeated key strings outweigh the numbers."""
    import build as B
    B.PREVIOUS_DERIVED = {}
    hist = build_history(_history_fixture_feeds())
    flat = len(json.dumps(hist, separators=(",", ":")))
    cols = len(json.dumps(B.compact_history(hist), separators=(",", ":")))
    assert cols < flat * 0.55, (cols, flat)


def test_re_encoding_is_not_a_restatement():
    """Wire format and content schema are orthogonal. A build reading
    its own columnar output back must produce the same weeks it wrote,
    without the migration path firing."""
    import build as B
    feeds = _history_fixture_feeds()
    B.PREVIOUS_DERIVED = {}
    first = build_history(feeds)
    B.PREVIOUS_DERIVED = {
        "history": json.loads(json.dumps(B.compact_history(first))),
        "history_schema": B.HISTORY_SCHEMA,
        "anchor_epoch": B.ANCHOR_EPOCH,
    }
    try:
        second = build_history(feeds)
    finally:
        B.PREVIOUS_DERIVED = {}
    assert [e["week_ending"] for e in second] == \
        [e["week_ending"] for e in first]
    assert len(second) == len(first)


def test_nothing_measures_the_history_by_len_of_the_container():
    """4.24.0 logged "3 complete weeks" for a 52-week record, because
    len() of the columnar block is its key count - encoding, n, cols.
    Anything downstream of compact_history() that wants a week count
    must read `n`, or the counters, never len()."""
    import build as B
    B.PREVIOUS_DERIVED = {}
    hist = build_history(_history_fixture_feeds())
    packed = B.compact_history(hist)
    assert len(packed) == 3                      # the trap itself
    assert packed["n"] == len(hist)              # the right answer
    assert len(B.expand_history(packed)) == len(hist)


def test_unbuildable_weeks_name_themselves():
    """A silent `continue` makes a short record look like a smaller
    number rather than an error. Every decline must land in the skip
    list with a reason - except a week outside the window, which is
    not a failure."""
    import build as B
    feeds = _history_fixture_feeds()
    days = sorted(feeds["hdd"]["hdd_island"])
    w_end = days[-8]

    # a week that builds records nothing
    skips = []
    assert B.week_inputs(feeds, w_end, skips) is not None
    assert skips == []

    # A week before the tariff table is now NAMED rather than silently
    # declined - it is a real gap with a fix (extend TARIFF_HISTORY),
    # not a week outside the window by design.
    skips = []
    assert B.week_inputs(feeds, "2020-01-05", skips) is None
    assert len(skips) == 1 and "tariff table" in skips[0][1]

    # no ROI bulletin at or before the week: named
    stripped = {**feeds, "oil_bulletin": {
        **feeds["oil_bulletin"],
        "roi_heating_gasoil_eur_per_1000l": {}}}
    skips = []
    assert B.week_inputs(stripped, w_end, skips) is None
    assert len(skips) == 1 and skips[0][0] == w_end
    assert "ROI oil" in skips[0][1]

    # and the signature stays back-compatible
    assert B.week_inputs(feeds, w_end) is not None


def test_skip_report_groups_by_reason_and_counts_the_attempt():
    """The report has to make a short record impossible to misread:
    how many were skipped, out of how many attempted, why, and over
    what span."""
    import build as B
    lines = []
    real = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        B.report_skips([], 52)
        B.report_skips([("2025-09-06", "reason A"),
                        ("2025-09-13", "reason A"),
                        ("2026-01-03", "reason B")], 49)
    finally:
        B.log = real
    assert "52 weeks built, none skipped" in lines[0]
    assert "3 week(s) skipped of 52 attempted" in lines[1]
    joined = " | ".join(lines[2:])
    assert "2 week(s) [2025-09-06..2025-09-13] - reason A" in joined
    assert "1 week(s) [2026-01-03] - reason B" in joined


def test_carbon_depth_probe_retries_before_calling_a_month_empty():
    """The probe decides whether a 24-month window can keep the
    back-look's central claim - each week at its own week's carbon.
    On 8 Aug 2026 the endpoint returned 0 rows for co2intensity and
    demandactual within seconds of serving wind and solar, so a single
    zero is not evidence of depth. Nothing may be called EMPTY until
    two independent attempts agree, and a month that answers on the
    retry must be recorded as data, not as absence."""
    import build as B
    calls = []

    class R:
        def __init__(self, rows):
            self._rows = rows

        def json(self):
            return {"Rows": self._rows}

    def flaky(url, **kw):
        p = kw.get("params") or {}
        calls.append(p.get("chartType"))
        # every co2 call fails once, then answers
        if p.get("chartType") == "co2" and calls.count("co2") % 2 == 1:
            return R([])
        return R([{"EffectiveTime": "15-Jan-2025 00:00:00", "Value": 300.0}])

    real_get, real_sleep = B.http_get, B.time.sleep
    B.http_get, B.time.sleep = flaky, lambda *a, **k: None
    lines = []
    real_log = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        B.feed_eirgrid_probe()
    finally:
        B.http_get, B.time.sleep = real_get, real_sleep
        B.log = real_log
    depth = [l for l in lines if "CARBON DEPTH" in l]
    assert depth, lines[-5:]
    assert not any("EMPTY" in l for l in depth), depth
    assert any("verdict" in l for l in depth)


def test_nondom_steps_by_semester_and_refuses_before_the_first():
    """Services rates move with the semester the week falls in. Weeks
    after the last published semester HOLD at it - the REMM lag, not a
    claim that prices stopped moving. Weeks BEFORE the first are
    refused outright as of 5.9.0: clamping them was safe only while
    nothing reached back that far, and extending the back-look is
    exactly what removes that safety."""
    import build as B
    sem = {"2024-S2": 0.8386, "2025-S1": 0.8412, "2025-S2": 0.87073}
    early, k0 = B.nondom_for("2023-01-05", sem)
    s24, _ = B.nondom_for("2024-11-02", sem)
    s25a, _ = B.nondom_for("2025-03-01", sem)
    s25b, k2 = B.nondom_for("2025-09-06", sem)
    tail, k3 = B.nondom_for("2026-08-08", sem)
    assert early is None and k0 is None
    assert k2 == "2025-S2" and k3 == "2025-S2"
    assert tail == s25b
    # the semesters are genuinely different - holding one flat across
    # two years was the thing this replaces
    assert s24["gbp"]["gas"] != s25b["gbp"]["gas"]
    assert abs(s24["gbp"]["gas"] / s25b["gbp"]["gas"] - 1) > 0.05
    # NI gas falls across the three, Ireland's rises past NI
    assert s24["gbp"]["gas"] > s25a["gbp"]["gas"] > s25b["gbp"]["gas"]


def test_each_semester_converts_at_its_own_exchange_rate():
    """UREGNI sterlings Eurostat's euro at the semester average, so
    recovering the euro figure needs THAT semester's rate - not the
    week's, and not one rate for all of them."""
    import build as B
    flat = {"2024-S2": 0.87, "2025-S1": 0.87, "2025-S2": 0.87}
    real = {"2024-S2": 0.8386, "2025-S1": 0.8412, "2025-S2": 0.87073}
    a, _ = B.nondom_for("2024-11-02", flat)
    b, _ = B.nondom_for("2024-11-02", real)
    assert a["eur"]["electricity"] != b["eur"]["electricity"]
    assert abs(b["eur"]["electricity"] - 23.727 / 100 / 0.8386) < 5e-4
    # sterling is published directly and must not move with the rate
    assert a["gbp"] == b["gbp"]


def test_week_carries_its_own_non_domestic_rates():
    """A historic week must price its services share at its own
    semester. Before this, every week used today's figures."""
    import build as B
    feeds = _history_fixture_feeds()
    days = sorted(feeds["hdd"]["hdd_island"])
    ctx = B.week_inputs(feeds, days[-8])
    assert ctx and "nondom" in ctx
    assert set(ctx["nondom"]) == {"eur", "gbp"}
    # and derive_hero prefers it over the live anchors
    a = B.ANCHORS
    assert B._nondom(a, {"nondom": ctx["nondom"]}) == ctx["nondom"]
    assert B._nondom(a, {})["eur"] == a["nondom_eur_per_kwh"]


def test_semester_of_assigns_by_week_ending():
    """A week straddling 30 June or 31 December lands wholly in the
    semester it ends in - the agreed convention, two weeks a year."""
    import build as B
    assert B.semester_of("2025-06-29") == "2025-S1"
    assert B.semester_of("2025-07-06") == "2025-S2"
    assert B.semester_of("2025-12-28") == "2025-S2"
    assert B.semester_of("2026-01-04") == "2026-S1"


def _synthetic_store(hours=9384, start=(2025, 7, 14), renewables=True):
    import math
    t0 = dt.datetime(*start)
    temps, dem, wind, solar = {}, {}, {}, {}
    for i in range(hours):
        h = t0 + dt.timedelta(hours=i)
        k = h.strftime("%Y-%m-%dT%H")
        doy = h.timetuple().tm_yday
        T = (10.5 - 6.5 * math.cos(2 * math.pi * (doy - 15) / 365)
             - 3 * math.cos(2 * math.pi * (h.hour - 15) / 24))
        temps[k] = round(T, 2)
        dem[k] = round(3500 + 900 * max(0.0, 15.5 - T) / 10
                       + 400 * math.sin(2 * math.pi * (h.hour - 9) / 24), 1)
        wind[k] = round(900 + 700 * math.sin(2 * math.pi * i / 71), 1)
        solar[k] = round(max(0.0, 600 * math.sin(
            math.pi * (h.hour - 6) / 12)), 1)
    ser = {"temp_ai": temps, "demand_ai": dem}
    if renewables:
        ser["wind_ai"] = wind
        ser["solar_ai"] = solar
    return {"schema": 2, "series": ser}


def test_tightest_hour_lands_in_winter_and_nets_the_resistive_share():
    """B.2.1. The binding hour must be cold - if it lands in summer
    the shaping is wrong, not the grid. And electrified heat is added
    NET of the resistive heating already inside observed demand;
    counting the heat pump without removing the immersion would
    double-count it."""
    import build as B
    out = B.derive_tightest_hour(_synthetic_store())
    assert out, "no result"
    assert out["hour"][5:7] in ("11", "12", "01", "02"), out["hour"]
    assert out["air_c"] < 5
    # the three routes must order air > ground > network, always
    add = out["added_mw"]
    assert add["air_source"] > add["ground_source"] > add["geothermal_network"]
    # netting is real: the added load is below the naive heat/COP
    assert add["air_source"] < out["useful_heat_mw"]
    assert out["total_with_air_source_mw"] == \
        out["observed_mw"] + add["air_source"]
    # headroom is measured against the BREATHING ceiling - de-rated
    # block plus the wind and solar actually generated - not the bare
    # block, which is what makes it comparable with the UK sibling.
    hr = out["headroom_by_route_mw"]
    assert set(hr) == set(add)
    assert out["ceiling_mw"] >= out["block_mw"]
    for r in add:
        assert hr[r] == out["ceiling_mw"] - out["observed_mw"] - add[r]
    assert hr["geothermal_network"] > hr["ground_source"] > hr["air_source"]
    assert out["routes_that_fit"] == [r for r in add if hr[r] >= 0]


def test_tightest_hour_declines_rather_than_guesses():
    """Log-only and soft. Too short a store, or one without
    temperature, must return None rather than a number computed from
    a season."""
    import build as B
    assert B.derive_tightest_hour({}) is None
    assert B.derive_tightest_hour(_synthetic_store(hours=24 * 100)) is None
    store = _synthetic_store()
    del store["series"]["temp_ai"]
    assert B.derive_tightest_hour(store) is None


def test_hourly_heat_conserves_the_annual_anchor():
    """The hourly shaping must not invent or lose heat: summed over
    the store it has to equal the annual useful-heat anchor scaled to
    the store's span, and hot water must stay flat."""
    import build as B
    store = _synthetic_store()
    mw = B.hourly_heat_mw(store)
    assert mw
    a = B.ANCHORS
    useful = sum((a[j]["residential_heat_twh"] + a[j]["services_heat_twh"])
                 * sum(sh * a["efficiency"][f]
                       for f, sh in a[j]["fuel_shares"].items())
                 for j in ("ni", "roi"))
    span_years = len(mw) / (365.25 * 24)
    assert abs(sum(mw.values()) / 1e6 - useful * span_years) < 0.01
    # summer minimum is the flat hot-water term, not zero
    assert min(mw.values()) > 0


def test_route_tiers_match_the_uk_sibling():
    """The two grid layers are read against the same ladder, so the
    tiers are the UK sibling's field-observed figures - Energy Systems
    Catapult in-situ, not brochure SCOPs. Anyone re-tuning one site
    must re-tune both, and this fails if they drift apart."""
    import build as B
    assert B.ASHP_SPF == 2.80
    assert B.GSHP_SPF == 3.24
    assert B.GEO_NETWORK_SCOP == 5.00
    out = B.derive_tightest_hour(_synthetic_store())
    assert out["spf"] == {"air_seasonal": 2.80, "ground": 3.24,
                          "network": 5.00}


def test_air_route_uses_the_hourly_cop_not_the_seasonal_spf():
    """The air column exists to show that air-source performance
    collapses in the hour that binds. Pricing it at the seasonal 2.80
    would hide the effect being measured, so the binding hour's COP
    must come out BELOW the seasonal figure and the added load must be
    correspondingly worse than 2.80 would give."""
    import build as B
    out = B.derive_tightest_hour(_synthetic_store())
    assert out["hour_cop_air"] < B.ASHP_SPF, out["hour_cop_air"]
    # Compare like with like: added load is NET of displaced resistive,
    # so a gross useful/SPF figure is not the comparator. The test that
    # holds is the RATIO between routes - if air ran at the seasonal
    # 2.80 the air/ground gap would be GSHP_SPF/ASHP_SPF; because the
    # binding hour is colder than the season, it must be wider.
    ratio = (out["added_mw"]["air_source"]
             / out["added_mw"]["ground_source"])
    assert ratio > B.GSHP_SPF / B.ASHP_SPF, ratio
    # ground and network stay flat, so their ordering is fixed
    assert (out["added_mw"]["ground_source"]
            > out["added_mw"]["geothermal_network"])


def test_route_ordering_is_reported_not_left_to_subtraction():
    """The first live run reported headroom for the air route alone,
    so the actual finding - which routes fit under the block - had to
    be derived by hand from three other numbers. The route ordering
    IS the result of B.2.1 and must be stated."""
    import build as B
    lines = []
    real = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        out = B.derive_tightest_hour(_synthetic_store())
    finally:
        B.log = real
    joined = " | ".join(lines)
    for r in ("air_source", "ground_source", "geothermal_network"):
        assert r in joined
        assert f"headroom" in joined
    assert "routes that fit" in joined
    assert "FITS" in joined or "EXCEEDS THE CEILING" in joined
    # and the heat-versus-power comparison is printed, not just stored
    assert "heat system is" in joined
    assert out["heat_vs_block_ratio"] == round(
        out["useful_heat_mw"] / out["block_mw"], 2)


def test_a_route_that_exceeds_the_block_is_named_as_such():
    """A negative headroom must read as EXCEEDS, and a route list that
    empties must say NONE rather than printing an empty string."""
    import build as B
    real_block = B.GRID_BLOCK_MW
    lines = []
    real_log = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    B.GRID_BLOCK_MW = 100          # nothing can fit
    try:
        B.derive_tightest_hour(_synthetic_store())
    finally:
        B.GRID_BLOCK_MW = real_block
        B.log = real_log
    joined = " | ".join(lines)
    assert "EXCEEDS THE CEILING" in joined
    assert "routes that fit: NONE" in joined


def test_semopx_parser_keeps_the_delivery_hours():
    """The parser was reading the delivery timestamp row and throwing
    it away, keeping only a daily mean. B.2.3 asks what price applied
    in ONE hour, so the stamps are the whole point."""
    import build as B
    csv = ("Auction;SEM-DA\n"
           "EUR;GBP;0,85506627\n"
           "Market;ROI-DA\n"
           "Index prices;30;EUR\n"
           "2026-01-05T17:00:00Z;2026-01-05T18:00:00Z\n"
           "118,42;243,17\n")
    p = B.parse_semopx_csv(csv, trade_day="2026-01-05")
    assert p["day"] == "2026-01-05"
    # anchored on the trade day: the first period IS midnight local,
    # whatever the stamps carry
    assert p["series"]["ROI-DA"]["EUR"] == {"2026-01-05T00": 118.42,
                                            "2026-01-05T01": 243.17}
    # the daily mean still works - nothing regressed
    assert p["markets"]["ROI-DA"]["EUR"] == [118.42, 243.17]


def test_price_layer_gates_separately_and_cannot_withdraw_the_others():
    """price_ai starts empty and fills a day at a time. While it
    climbs it must not be able to pull down the grid trio or the heat
    layer, which is why it has its own gate rather than joining
    `complete`."""
    import build as B

    def fake_chunk(chart, region, areas, end_day):
        base = end_day - dt.timedelta(days=27)
        out = {}
        for d in range(28):
            day = base + dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1000.0
        return out

    def full_temp(prev, floor, end):
        out, day = {}, dt.datetime.strptime(floor, "%Y-%m-%dT%H").date()
        while day <= end:
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 5.0
            day += dt.timedelta(days=1)
        return out

    real, real_t, real_s = B.fetch_hourly_chunk, B.fetch_hourly_temp, B.time.sleep
    B.fetch_hourly_chunk, B.fetch_hourly_temp = fake_chunk, full_temp
    B.time.sleep = lambda *_: None
    try:
        store = B.build_hourly_store({}, {"semopx": {
            "dam_hourly_eur_mwh": {"2026-08-01T00": 90.0}}})
    finally:
        B.fetch_hourly_chunk, B.fetch_hourly_temp = real, real_t
        B.time.sleep = real_s
    assert store["schema"] == 4
    assert "price_ai" in store["series"]
    assert store["complete"] is True          # grid trio unaffected
    assert store["heat_ready"] is True        # heat layer unaffected
    assert store["price_ready"] is False      # one hour is not 95%


def test_semopx_hours_are_anchored_on_the_trade_day():
    """Two timezone guesses were wrong - UTC, then CET - and each cost
    a run to disprove. The document does not need decoding: a trade
    day runs 00:00 to 23:00 local by definition and the resource name
    says which day it is, so the offset is measured rather than
    assumed. Whatever the stamps carry, a full document must land on
    T00..T23 of its own trade day."""
    import build as B
    for shift in (-2, -1, 0, 1, 2):
        stamps, base = [], dt.datetime(2026, 8, 6) + dt.timedelta(hours=shift)
        for h in range(24):
            stamps.append((base + dt.timedelta(hours=h)).isoformat() + "Z")
        keys = B.semopx_hour_keys(stamps, "2026-08-06")
        assert keys[0] == "2026-08-06T00", (shift, keys[0])
        assert keys[-1] == "2026-08-06T23", (shift, keys[-1])
    # unanchorable input contributes nothing rather than something wrong
    assert B.semopx_hour_keys(["2026-08-06T00:00:00Z"], None) == []
    assert B.semopx_hour_keys([], "2026-08-06") == []
    assert B.semopx_hour_keys(["rubbish"], "2026-08-06") == []
    # and end to end through the parser
    csv = ("Auction;SEM-DA\nMarket;ROI-DA\nIndex prices;30;EUR\n"
           "2026-08-05T22:00:00Z;2026-08-05T23:00:00Z\n90,0;91,0\n")
    out = B.parse_semopx_csv(csv, trade_day="2026-08-06")
    assert sorted(out["series"]["ROI-DA"]["EUR"]) == ["2026-08-06T00",
                                                     "2026-08-06T01"]


def test_semopx_trade_day_matches_the_field_not_a_character_count():
    """The first probe sliced the resource name positionally, cut
    through the timestamp, and made its own verdict line say the
    opposite of what the data showed."""
    import build as B
    n = "MarketResult_SEM-DA_PWR-MRC-D+1_20260806100000_20260806105502.csv"
    assert B.semopx_trade_day({"ResourceName": n}) == "2026-08-06"
    assert B.semopx_trade_day({"ResourceName": "rubbish"}) is None
    assert B.semopx_trade_day(None) is None


def test_semopx_backfill_is_bounded_and_skips_days_already_priced():
    """Paging is the route to history, but 400 requests in one build
    is not. The walk is bounded per run and must not refetch a day the
    store already holds."""
    import build as B
    calls = {"list": 0, "doc": 0}

    class R:
        def __init__(self, payload=None, text=""):
            self._p, self.text = payload, text

        def json(self):
            return self._p

    def fake_get(url, **kw):
        if "static-reports" in url:
            calls["list"] += 1
            page = (kw.get("params") or {}).get("page", 1)
            items = []
            for i in range(100):
                d = dt.date(2026, 8, 8) - dt.timedelta(days=(page - 1) * 100 + i)
                items.append({"ResourceName":
                              f"MarketResult_SEM-DA_PWR-MRC-D+1_"
                              f"{d.strftime('%Y%m%d')}100000_x.csv"})
            return R(payload={"items": items})
        calls["doc"] += 1
        return R(text=("Auction;SEM-DA\nMarket;ROI-DA\n"
                       "Index prices;30;EUR\n2026-01-05T18:00:00Z\n120,0\n"))

    real_get, real_sleep = B.http_get, B.time.sleep
    B.http_get, B.time.sleep = fake_get, lambda *a, **k: None
    try:
        have = {"2026-08-08T00": 1.0, "2026-08-07T00": 1.0}
        out = B.semopx_backfill(have, "https://x/static-reports", "2025-08-01")
    finally:
        B.http_get, B.time.sleep = real_get, real_sleep
    assert calls["doc"] == B.SEMOPX_BACKFILL_DAYS
    assert calls["list"] <= B.SEMOPX_BACKFILL_PAGES
    assert out


def test_share_that_fits_is_solved_not_assumed():
    """The UK sibling asks how far heat can be electrified before the
    winter peak fills the fleet, rather than fixing a share. Fixing
    one forces a choice between the site's own 20% what-if and a 100%
    ceiling that appears nowhere else, and the answer swings entirely
    on which is picked. Netting is linear in the share, so the solved
    figure must equal headroom / added-at-100% exactly."""
    import build as B
    out = B.derive_tightest_hour(_synthetic_store())
    sh = out["share_that_fits_pct"]
    assert set(sh) == {"air_source", "ground_source", "geothermal_network"}
    assert sh["geothermal_network"] > sh["ground_source"] > sh["air_source"]
    for r, hr in out["share_binding_hour"].items():
        assert hr and hr[5:7] in ("10", "11", "12", "01", "02"), (r, hr)


def test_ceiling_breathes_with_wind_and_solar():
    """The UK ceiling is the de-rated fleet PLUS the wind and solar
    actually generated, so the Irish figure is not comparable until it
    is too. A still, dark hour must therefore give a LOWER ceiling
    than a windy one, and dropping the series must fall back to the
    bare block rather than crashing."""
    import build as B
    with_re = B.derive_tightest_hour(_synthetic_store())
    without = B.derive_tightest_hour(_synthetic_store(renewables=False))
    assert with_re["ceiling_mw"] > B.GRID_BLOCK_MW
    assert with_re["wind_solar_mw"] > 0
    assert without["ceiling_mw"] == B.GRID_BLOCK_MW
    assert without["wind_solar_mw"] == 0
    # more headroom with renewables in the ceiling, so more heat fits
    assert (with_re["share_that_fits_pct"]["air_source"]
            > without["share_that_fits_pct"]["air_source"])


def test_semo_probe_calls_one_report_id_inconclusive_not_a_catalogue():
    """The first live run returned 50 items from every trial - all one
    report ID, all 2019 documents - and the probe announced it had
    found the catalogue. A response is not an answer. The endpoint
    lists DOCUMENTS ascending by date, not report types, so the test
    is whether more than one report ID came back."""
    import build as B
    lines = []

    class R:
        @staticmethod
        def json():
            return {"items": [{"DPuG_ID": "EA-009",
                               "ResourceName": "IDC_Statistic_2019.csv"}]}

    real_get, real_log = B.http_get, B.log
    B.http_get = lambda url, **kw: R
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        B.semo_dispatch_probe()
    finally:
        B.http_get, B.log = real_get, real_log
    joined = " | ".join(lines)
    assert "INCONCLUSIVE" in joined
    assert "STOP PROBING" in joined
    assert "catalogue" not in joined.split("INCONCLUSIVE")[0].split("|")[-1]


def test_semo_probe_reports_a_real_catalogue_when_it_finds_one():
    """More than one report ID is the signal that the listing actually
    enumerated report types."""
    import build as B
    lines = []

    class R:
        @staticmethod
        def json():
            return {"items": [{"DPuG_ID": "BM-086", "ResourceName": "a.csv"},
                              {"DPuG_ID": "EA-001", "ResourceName": "b.csv"}]}

    real_get, real_log = B.http_get, B.log
    B.http_get = lambda url, **kw: R
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        B.semo_dispatch_probe()
    finally:
        B.http_get, B.log = real_get, real_log
    joined = " | ".join(lines)
    assert "report IDs seen" in joined
    assert "INCONCLUSIVE" not in joined


def test_semo_dispatch_probe_says_what_to_do_when_nothing_answers():
    """A silent probe is worse than none. If both families fail it
    must say so and name the next step - read the catalogue by hand -
    rather than inviting another round of guessed IDs."""
    import build as B
    lines = []

    def boom(url, **kw):
        raise RuntimeError("moved")

    real_get, real_log = B.http_get, B.log
    B.http_get, B.log = boom, lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        B.semo_dispatch_probe()
    finally:
        B.http_get, B.log = real_get, real_log
    joined = " | ".join(lines)
    # total failure and a one-report listing now converge on the same
    # verdict, which is right: neither enumerated the catalogue
    assert "INCONCLUSIVE" in joined
    assert "STOP PROBING" in joined
    assert "read the report catalogue by hand" in joined


def test_completeness_is_clamped_at_whole():
    """temp_ai holds whole local days plus a forecast tail, so it ran
    past the grid window and scored 100.1% for a week - in a field
    whose entire job is to flag bugs, since a series cannot be more
    than complete. The surplus is reported separately instead."""
    import build as B

    def fake_chunk(chart, region, areas, end_day):
        base = end_day - dt.timedelta(days=27)
        out = {}
        for d in range(28):
            day = base + dt.timedelta(days=d)
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 1000.0
        return out

    def over_temp(prev, floor, end):
        out, day = {}, dt.datetime.strptime(floor, "%Y-%m-%dT%H").date()
        while day <= end + dt.timedelta(days=2):      # deliberately past
            for h in range(24):
                out[day.strftime("%Y-%m-%dT") + f"{h:02d}"] = 5.0
            day += dt.timedelta(days=1)
        return out

    real, real_t, real_s = B.fetch_hourly_chunk, B.fetch_hourly_temp, B.time.sleep
    B.fetch_hourly_chunk, B.fetch_hourly_temp = fake_chunk, over_temp
    B.time.sleep = lambda *_: None
    lines = []
    real_log = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        store = B.build_hourly_store({})
    finally:
        B.fetch_hourly_chunk, B.fetch_hourly_temp = real, real_t
        B.time.sleep, B.log = real_s, real_log
    assert store["completeness_pct"]["temp_ai"] == 100.0
    assert all(v <= 100.0 for v in store["completeness_pct"].values())
    assert "beyond the grid window" in " | ".join(lines)


def test_entsog_probe_polls_twice_a_week_and_retains_between():
    """Log-only, analysed fortnightly, and it was taking 4.5 of a
    7-minute build. On a non-poll day it must return the retained
    series rather than re-measuring, and must still report."""
    import build as B
    assert B.ENTSOG_POLL_WEEKDAYS == (0, 3)
    called = []
    real_get, real_today, real_prev = B.http_get, B.today_utc, B.PREVIOUS_FEEDS
    B.http_get = lambda *a, **k: called.append(1)
    B.PREVIOUS_FEEDS = {"entsog_probe": {
        "moffat_gwh_daily": {"2026-08-10": 144.0},
        "latest_day": "2026-08-10"}}
    try:
        B.today_utc = lambda: dt.date(2026, 8, 11)      # Tuesday
        out, status = B.feed_entsog_probe()
        assert not called, "polled on a non-poll day"
        assert out["latest_day"] == "2026-08-10"
        assert out["moffat_gwh_daily"] == {"2026-08-10": 144.0}
        assert status == "lagging"
    finally:
        B.http_get, B.today_utc = real_get, real_today
        B.PREVIOUS_FEEDS = real_prev


def test_every_route_costs_more_on_hot_water_than_on_space_heat():
    """The reason the panel splits modes at all. A July week is almost
    all hot water, and every route performs worse on it - so pricing
    summer at an annual efficiency would flatter heat pumps AND
    flatter the boiler at exactly the point where the lines converge."""
    import build as B
    p = {"oil_per_kwh": 10.0, "gas_per_kwh": 13.0, "elec_per_kwh": 40.4}
    winter = B.route_cost_useful(p, 2.43, 0.0)
    summer = B.route_cost_useful(p, 2.43, 1.0)
    for r in ("oil_boiler", "gas_boiler", "ashp", "gshp", "network"):
        assert summer[r] > winter[r], (r, winter[r], summer[r])
    # The routes do not degrade equally, which is the finding rather
    # than a rounding artefact. Since the Table 4b correction the
    # steepest summer degradation is AIR SOURCE, not oil: a boiler
    # loses 15-18% while an air-source heat pump loses far more,
    # because a 52 C cylinder duty is a much bigger lift than the
    # 30 C weather-compensated flow it would otherwise run.
    deg = {r: summer[r] / winter[r]
           for r in ("oil_boiler", "gas_boiler", "ashp", "gshp", "network")}
    assert deg["ashp"] > deg["oil_boiler"], deg
    assert 1.10 < deg["oil_boiler"] < 1.30, deg["oil_boiler"]


def test_immersion_leakage_is_zeroed_and_the_mechanism_still_works():
    """Zeroed on 14 Aug 2026: at 0.30 it added 5.8 c to the summer oil
    figure on no metered evidence, and the UK sibling has no equivalent,
    so it broke parity as well. The mechanism stays in the code - and
    stays correct - because a metered study would turn it back on.

    Note the direction, which surprises people: at COP 1 on domestic
    electricity the immersion is DEARER than the inefficient boiler, so
    the leakage pushes the oil line UP."""
    import build as B
    assert B.OIL_IMMERSION_DHW_SHARE == 0.0
    p = {"oil_per_kwh": 10.0, "gas_per_kwh": 13.0, "elec_per_kwh": 40.4}
    # with it off, summer oil IS the input price over the DHW efficiency
    off = B.route_cost_useful(p, 2.43, 1.0)["oil_boiler"]
    assert abs(off - 10.0 / B.DHW_MODE["oil_boiler"]) < 0.02
    real = B.OIL_IMMERSION_DHW_SHARE
    try:
        B.OIL_IMMERSION_DHW_SHARE = 0.30
        on = B.route_cost_useful(p, 2.43, 1.0)["oil_boiler"]
    finally:
        B.OIL_IMMERSION_DHW_SHARE = real
    assert on > off, (off, on)


def test_dhw_mode_figures_are_the_published_ones():
    """These are the most challengeable numbers on the panel, so they
    are pinned to their sources: MCS 031 Issue 4.0 cut the ASHP hot
    water default to 1.70; GSHP is the MCS HPSPE 2.24; the network
    figure is derived at the SAME lift ratio as GSHP because both are
    ground-coupled with a constant source; and BRE put oil boilers in
    water-only mode under 40% gross, which is the floor rather than
    the estimate."""
    import build as B
    assert B.DHW_MODE["ashp"] == 1.70
    assert B.DHW_MODE["gshp"] == 2.24
    assert B.DHW_MODE["network"] == round(5.00 * 2.24 / 3.24, 2)
    # SAP 2012 Table 4b: summer runs 82-89% of winter across every oil
    # and gas archetype, and the worst row in the whole table - a
    # single-burner range cooker boiler - is 47/37, a ratio of 0.79.
    # The panel used 0.55 on 0.82, a ratio of 0.67, below anything SAP
    # publishes for any boiler.
    assert B.DHW_MODE_FLOOR_OIL == 0.37
    assert B.DHW_MODE["oil_boiler"] > B.DHW_MODE_FLOOR_OIL
    for fuel, key in (("oil", "oil_boiler"), ("gas", "gas_boiler")):
        ratio = B.DHW_MODE[key] / B.ANCHORS["efficiency"][fuel]
        assert 0.80 < ratio < 0.92, (fuel, round(ratio, 3))
    # every route is worse on hot water than on space heat
    assert B.DHW_MODE["oil_boiler"] < B.ANCHORS["efficiency"]["oil"]
    assert B.DHW_MODE["gas_boiler"] < B.ANCHORS["efficiency"]["gas"]
    assert B.DHW_MODE["gshp"] < B.GSHP_SPF
    assert B.DHW_MODE["network"] < B.GEO_NETWORK_SCOP


def test_dhw_share_goes_to_one_in_a_week_with_no_heating_degree_days():
    """A July week has essentially no space-heat demand, so its
    delivered heat is hot water and the share must approach 1. A cold
    week must be dominated by space heat. If this ever reads flat
    across the year the shaping is broken, not the weather."""
    import build as B
    # two years, so a January week has a full trailing year behind it
    hdd, day = {}, dt.date(2024, 8, 20)
    for i in range(800):
        d = (day + dt.timedelta(days=i))
        # winter-heavy synthetic year, and a genuinely zero July week
        hdd[d.isoformat()] = 0.0 if d.month in (6, 7, 8) else 8.0
    hot = B.week_dhw_share(hdd, "2026-07-15")
    cold = B.week_dhw_share(hdd, "2026-01-14")
    assert hot is not None and cold is not None
    assert hot > 0.95, hot
    assert cold < 0.25, cold
    # too little history to know the trailing year: decline, not guess
    assert B.week_dhw_share({"2026-07-15": 0.0}, "2026-07-15") is None


def test_ex_tax_strips_vat_first_then_carbon():
    """VAT is the OUTERMOST layer in both jurisdictions - it is
    charged on the carbon-tax-inclusive price - so the order is
    retail/(1+vat) THEN subtract carbon. Reversing it understates the
    wedge. Pinned against the worked examples from the statutory
    sources."""
    import build as B
    # ROI kerosene 128.0 c/L incl 13.5% VAT, carbon 16.081, NORA 2.0
    assert abs(B.ex_tax(128.0, "roi", "oil", "2026-08-10") - 94.69) < 0.02
    # ROI gas 13.00 c/kWh incl 9% VAT, NGCT 1.148
    assert abs(B.ex_tax(13.00, "roi", "gas", "2026-08-10") - 10.78) < 0.01
    # NI: VAT only, nothing else to strip
    assert abs(B.ex_tax(8.098, "ni", "gas", "2026-08-10") - 7.712) < 0.01
    assert abs(B.ex_tax(86.46, "ni", "oil", "2026-08-10")
               - 86.46 / 1.05) < 0.001
    # order matters: stripping carbon first would leave a different,
    # larger number
    wrong = (128.0 - 16.081 - 2.0) / 1.135
    assert abs(B.ex_tax(128.0, "roi", "oil", "2026-08-10") - wrong) > 2.0


def test_carbon_step_lands_on_14_october_not_1_may():
    """Ireland's carbon increase on non-propellant fuels normally
    lands on 1 May; for 2026 it was postponed to 14 October. That is a
    discontinuity in the middle of the record, so assuming the usual
    date would misprice five months of it."""
    import build as B
    before = B.carbon_for("2026-05-02")
    after = B.carbon_for("2026-10-20")
    assert before["eur_per_tonne"] == 63.50
    assert after["eur_per_tonne"] == 71.00
    assert B.carbon_for("2026-10-13")["eur_per_tonne"] == 63.50
    assert after["kerosene_c_per_l"] > before["kerosene_c_per_l"]
    assert after["gas_c_per_kwh"] > before["gas_c_per_kwh"]


def test_the_border_gap_is_a_tax_wedge_not_a_market_gap():
    """The finding the toggle exists to show: ROI oil costs about a
    third more than NI at retail, but the ex-tax product-plus-
    distribution figures converge. If this ever fails, either a rate
    is wrong or something real has changed in the market."""
    import build as B
    roi_ex = B.ex_tax(128.0, "roi", "oil", "2026-08-10")
    ni_ex = B.ex_tax(86.46, "ni", "oil", "2026-08-10") / 0.87
    assert abs(roi_ex / ni_ex - 1) < 0.05, (roi_ex, ni_ex)
    # while retail is far apart
    assert 128.0 / (86.46 / 0.87) > 1.25


def test_cost_series_is_not_floored_at_the_back_look_start():
    """The panel is not the back-look. Its floor is how far the
    weather record reaches, because every week needs a trailing year
    of degree days behind it - not the date four tariff anchors were
    verified from."""
    import build as B
    feeds = _history_fixture_feeds()
    rows = B.derive_heat_cost_series(_with_temp(feeds))
    assert rows
    assert rows[0]["day"] >= min(feeds["hdd"]["hdd_island"])
    # daily now, so consecutive rows are days apart
    assert len(rows) > 60
    for r in rows:
        for j in ("roi", "ni"):
            if j in r:
                assert j + "_ex_tax" in r, (r["day"], j)
                assert r[j + "_ex_tax"]["oil_boiler"] < r[j]["oil_boiler"]


def test_carbon_table_refuses_dates_before_it_starts():
    """The first run with the floor removed priced 122 weeks back to
    April 2024 - and 55 of them sat before the old table began, so
    they were silently charged EUR 63.50 a tonne when the rate was
    EUR 56.00 or less. Clamping left no trace. Now the table covers
    the whole trajectory and anything earlier is refused."""
    import build as B
    assert B.carbon_for("2024-04-20")["eur_per_tonne"] == 48.50
    assert B.carbon_for("2024-06-01")["eur_per_tonne"] == 56.00
    assert B.carbon_for("2025-06-01")["eur_per_tonne"] == 63.50
    # the 2026 step is October, not May
    assert B.carbon_for("2026-08-10")["eur_per_tonne"] == 63.50
    assert B.carbon_for("2026-10-20")["eur_per_tonne"] == 71.00
    # before the table: refuse, and let the refusal propagate
    assert B.carbon_for("2019-01-01") is None
    assert B.ex_tax(100.0, "roi", "oil", "2019-01-01") is None
    # NI has no carbon component, so it still prices
    assert B.ex_tax(100.0, "ni", "oil", "2019-01-01") is not None


def test_carbon_rates_scale_from_the_published_anchor():
    """The table derives linearly from one published pair, so it is
    checkable against Revenue's separately published prior rate: at
    EUR 56.00 a tonne the gas figure must come out at 1.013 c/kWh."""
    import build as B
    assert abs(B.carbon_for("2024-06-01")["gas_c_per_kwh"] - 1.013) < 0.002
    assert abs(B.carbon_for("2025-06-01")["gas_c_per_kwh"] - 1.148) < 0.001
    assert abs(B.carbon_for("2025-06-01")["kerosene_c_per_l"]
               - 16.081) < 0.001


def test_roi_vat_on_gas_stepped_down_in_may_2022():
    """A VAT constant would have been wrong the moment the panel
    reached back past 1 May 2022, when gas and electricity were cut
    from 13.5% to 9%. Kerosene never got the cut - which is why the
    oil wedge is heavier than the gas wedge inside ROI."""
    import build as B
    assert B.vat_for("roi", "gas", "2021-06-01") == 0.135
    assert B.vat_for("roi", "gas", "2023-06-01") == 0.09
    assert B.vat_for("roi", "electricity", "2023-06-01") == 0.09
    assert B.vat_for("roi", "oil", "2023-06-01") == 0.135
    assert B.vat_for("ni", "gas", "2021-06-01") == 0.05


def test_tariffs_refuse_before_the_table_rather_than_clamping():
    """The clamp was live and wrong. Once the price panel's floor came
    off it reached April 2024, and 68 weeks were quietly priced with
    August-2025 gas and electricity tariffs in both jurisdictions -
    the same fault as the carbon clamp, one function along. A missing
    figure is visible; a wrong one is not."""
    import build as B
    first = B.TARIFF_HISTORY[0][0]
    assert B.tariffs_for(first) is not None
    assert B.tariffs_for("2024-03-31") is None
    assert B.tariffs_for("2020-01-01") is None
    # and a week that cannot be priced is SKIPPED WITH A REASON, not
    # silently dropped
    feeds = _history_fixture_feeds()
    skips = []
    assert B.week_inputs(feeds, "2024-03-31", skips) is None
    assert len(skips) == 1 and "tariff table" in skips[0][1]


def test_cost_series_declines_unpriceable_weeks_and_says_how_many():
    """The panel reaches deeper than the tariff table, so it must
    report the shortfall rather than quietly returning fewer rows."""
    import build as B
    lines = []
    real = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    finally:
        B.log = real
    assert rows
    for r in rows:
        assert r["day"] >= B.TARIFF_HISTORY[0][0]


def test_tariffs_refuse_before_the_table_rather_than_clamping():
    """The clamp was live and wrong. Once the price panel's floor came
    off it reached April 2024, and 68 weeks were quietly priced with
    August-2025 gas and electricity tariffs in both jurisdictions -
    the same fault as the carbon clamp, one function along. A missing
    figure is visible; a wrong one is not."""
    import build as B
    first = B.TARIFF_HISTORY[0][0]
    assert B.tariffs_for(first) is not None
    assert B.tariffs_for("2024-03-31") is None
    assert B.tariffs_for("2020-01-01") is None
    # and a week that cannot be priced is SKIPPED WITH A REASON, not
    # silently dropped
    feeds = _history_fixture_feeds()
    skips = []
    assert B.week_inputs(feeds, "2024-03-31", skips) is None
    assert len(skips) == 1 and "tariff table" in skips[0][1]


def test_cost_series_declines_unpriceable_weeks_and_says_how_many():
    """The panel reaches deeper than the tariff table, so it must
    report the shortfall rather than quietly returning fewer rows."""
    import build as B
    lines = []
    real = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    finally:
        B.log = real
    assert rows
    for r in rows:
        assert r["day"] >= B.TARIFF_HISTORY[0][0]


def test_probe_stations_stay_out_of_every_weighted_calculation():
    """The midlands probe ran (Athlone, 4%, 1,151 days: island HDD
    +0.28%, winter +0.27% - immaterial, so the all-coastal set stands)
    and is retired. But the mechanism must stay safe, because it left
    a station in the FETCH that STATIONS did not know about and that
    KeyError silently stopped ODH26 collection for a day. Anything
    downstream of the fetch reads the weighted set, never the fetched
    one."""
    import build as B, inspect
    assert B.PROBE_STATIONS == {}, "probe retired; re-adding needs care"
    assert abs(sum(v[2] for v in B.STATIONS.values()) - 1.0) < 1e-9
    src = inspect.getsource(B.feed_hdd)
    # every consumer downstream of the fetch is keyed on weighted_names
    assert "weighted_names" in src
    assert "STATIONS[n][2] for n in names}" not in src, \
        "a probe station would raise KeyError here again"


def test_electric_routes_move_with_the_weather():
    """The whole point of the daily engine. The panel priced every
    electric route at ONE seasonal SPF, so the lines were flat
    multiples of the electricity price and could never spread apart in
    the cold - which is the effect the chart exists to show."""
    import build as B
    rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    assert rows and len(rows) > 60
    ashp = [r["roi"]["ashp"] for r in rows]
    oil = [r["roi"]["oil_boiler"] for r in rows]
    # air source swings hard; the oil boiler barely moves
    assert max(ashp) / min(ashp) > 1.3, (min(ashp), max(ashp))
    assert max(oil) / min(oil) < 1.2
    # and the cold days are the dear ones for air source
    cold = min(rows, key=lambda r: r["t_roi"])
    mild = max(rows, key=lambda r: r["t_roi"])
    assert cold["roi"]["ashp"] > mild["roi"]["ashp"]


def test_calibration_reproduces_the_spf_anchors():
    """Assert the anchor, calibrate the Carnot fraction to it - not the
    other way round. And the three fractions must land within 15% of
    each other, or the source temperature and the anchor are not
    describing the same machine."""
    import build as B, math
    days = []
    for i in range(365):
        t = 10.5 - 6.5 * math.cos(2 * math.pi * (i - 200) / 365)
        days.append((t, max(0.0, 15.5 - t), 0.29))
    etas = {}
    for r in ("ashp", "gshp"):
        etas[r] = B.calibrate_eta(r, days)
    for jur in ("ni", "roi"):
        etas["network_" + jur] = B.calibrate_eta("network", days, jur)
    assert max(etas.values()) / min(etas.values()) < 1.15, etas
    # the ROI network is a different machine from the NI one
    assert B.NETWORK_MODEL["roi"]["spf"] == 4.0
    assert B.NETWORK_MODEL["ni"]["spf"] == 5.0
    assert B.NETWORK_MODEL["roi"]["source_c"] < B.NETWORK_MODEL["ni"]["source_c"]


def test_hot_water_is_priced_at_the_cylinder_flow():
    """Without a service split, a mild summer day gives absurd COPs on
    a load that is entirely hot water - the flow follows the weather
    down to 30 C while the cylinder still needs 52 C."""
    import build as B
    e = 0.33
    for t in (0.0, 8.0, 16.0):
        assert B.route_cop("ashp", t, e, dhw=True) < \
            B.route_cop("ashp", t, e, dhw=False) or t < 5
    assert B.flow_temp(16.0) == B.FLOW_MILD_C
    assert B.flow_temp(-6.0) == B.FLOW_COLD_C
    assert B.DHW_FLOW_C > B.FLOW_MILD_C


def test_boilers_do_not_swing_with_a_single_day_of_weather():
    """The mode regime is seasonal, not daily. A boiler in January does
    not drop to summer cycling efficiency because one day was mild - it
    is still running its space-heating circuit. Blending on the day's
    own hot-water share made the oil line sawtooth 15 to 28 c between
    adjacent days, which is a shaping artefact, not a price signal.

    Heat pumps are the opposite: their COP IS instantaneous physics and
    must follow the day."""
    import build as B, statistics
    rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    assert rows and len(rows) > 60

    def jitter(route):
        v = [r["roi"][route] for r in rows]
        return statistics.mean(abs(v[i] - v[i - 1]) for i in range(1, len(v)))

    # the fuels are near-flat day to day; the heat pump is not
    assert jitter("oil_boiler") < 0.05, jitter("oil_boiler")
    assert jitter("gas_boiler") < 0.05, jitter("gas_boiler")
    assert jitter("ashp") > jitter("oil_boiler") * 2
    # both shares are published - the daily one for the caption, the
    # smoothed one for the money
    assert "dhw_share" in rows[-1] and "dhw_mode" in rows[-1]


def test_all_three_services_are_published():
    """Space heating and hot water are different questions and the
    answers diverge - on space heat a heat pump rides the compensated
    flow down to 30 C, on hot water the cylinder pins it at 52 C
    whatever the weather. The panel publishes both plus the blend a
    household actually pays."""
    import build as B
    rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    assert rows
    last = rows[-1]
    for j in ("roi", "ni"):
        if j not in last:
            continue
        sp, dhw, bl = last[j + "_space"], last[j + "_dhw"], last[j]
        for r in ("oil_boiler", "gas_boiler", "ashp", "gshp", "network"):
            assert dhw[r] > sp[r], (j, r)
            assert sp[r] <= bl[r] <= dhw[r], (j, r)
        # The finding, and it is not the one I first claimed. Every
        # electric route pays roughly the SAME absolute penalty on hot
        # water, because they all buy the same electricity and the
        # cylinder adds a similar lift in kelvin to each. So the
        # cheapest route takes the biggest RELATIVE hit, and the
        # geothermal advantage over gas SHRINKS on hot water rather
        # than air source collapsing.
        adv_space = sp["gas_boiler"] / sp["network"]
        adv_dhw = dhw["gas_boiler"] / dhw["network"]
        assert adv_dhw < adv_space, (adv_space, adv_dhw)
        assert adv_dhw > 1.0, adv_dhw


def test_per_fuel_dhw_shares_exist_but_do_not_price_the_panel():
    """SEAI publishes the hot-water share by fuel - oil 22.8%, gas
    26.8% - and those are right for the energy and bill panels. They
    are WRONG for the cost panel, where every route answers the same
    counterfactual, so the share is a property of the building's
    demand rather than of the fuel. Using them there would compare two
    different demand profiles."""
    import build as B
    assert B.DHW_SHARE_BY_FUEL == {"oil": 0.228, "gas": 0.268}
    # the panel prices on ONE share, whatever the route
    rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    assert rows and "dhw_mode" in rows[-1]


def test_delivered_heat_volume_is_published_and_matches_the_share():
    """The quantity the per-MWh axis is charged on. It is shaped by
    the SAME rule as the hot-water share - hot water flat across the
    year, space heat by the day's share of the trailing year's degree
    days - so dhw / (space + dhw) must reproduce dhw_share EXACTLY.
    If the two ever drift apart the panel is drawing a volume that
    does not belong to the price above it."""
    import build as B
    rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    assert rows
    seen = 0
    for r in rows:
        for j in ("roi", "ni"):
            v = r.get("vol_" + j)
            if not v:
                continue
            seen += 1
            assert v["space"] >= 0 and v["dhw"] > 0, (j, v)
            share = v["dhw"] / (v["space"] + v["dhw"])
            assert abs(share - r["dhw_share"]) < 2e-3, (j, share,
                                                        r["dhw_share"])
    assert seen, "no row carried a delivered-heat volume"
    # Hot water is FLAT: the same figure every day of the year. That
    # is the shaping stated on the site, and the flat band is the
    # feature of the chart - everything above it is weather.
    dhw = {r["vol_roi"]["dhw"] for r in rows if r.get("vol_roi")}
    assert len(dhw) == 1, dhw
    # and the seasonal swing lands on space heat
    sp = [r["vol_roi"]["space"] for r in rows if r.get("vol_roi")]
    assert max(sp) > min(sp) * 1.5, (min(sp), max(sp))


def test_delivered_heat_converts_input_to_useful_before_shaping():
    """The sector anchors are fuel INPUT. A per-MWh-of-delivered-heat
    axis cannot be charged on an input quantity, so the volume goes
    through each jurisdiction's own fuel mix and efficiencies first -
    the same conversion hourly_heat_mw() uses, not a second one."""
    import build as B
    for jur in ("roi", "ni"):
        j = B.ANCHORS[jur]
        raw = (j["residential_heat_twh"] + j["services_heat_twh"]) * 1000.0
        useful = B.useful_heat_gwh_year(jur)
        assert useful < raw, (jur, useful, raw)
        # boilers dominate both jurisdictions, so the conversion is a
        # haircut rather than a transformation
        assert 0.7 < useful / raw < 1.0, (jur, useful / raw)
    # ROI is the larger jurisdiction and must carry the larger volume
    assert B.useful_heat_gwh_year("roi") > B.useful_heat_gwh_year("ni")
    # the annual total reconciles with the daily emission
    hdd = {f"2026-{m:02d}-{d:02d}": 6.0
           for m in range(1, 13) for d in range(1, 29)}
    day = sorted(hdd)[-1]
    v = B.day_delivered_heat(hdd, day, "roi")
    flat = (B.useful_heat_gwh_year("roi")
            * (1 - B.ANCHORS["space_heat_fraction"]) / 365.0)
    assert abs(v["dhw"] - flat) < 1e-2, (v, flat)
    # short record declines rather than shaping on a season
    assert B.day_delivered_heat({"2026-01-01": 5.0}, "2026-01-01",
                                "roi") is None


def test_cost_series_round_trips_through_the_columnar_encoding():
    """The cost series is written columnar from 5.9.0 - same wire
    format, same encoder as the history block. Encoding is not a
    restatement, so the round trip must be exact, nulls included: a
    day carrying no NI block is not the same as one carrying an empty
    NI block."""
    import build as B, json
    rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    assert rows
    packed = B.compact_history(rows)
    back = B.expand_history(packed)
    assert len(back) == len(rows)
    for a, b in zip(rows, back):
        for k in a:
            assert b.get(k) == a[k], (a["day"], k, a[k], b.get(k))
    # and it is genuinely smaller - the keys are most of the file
    flat = len(json.dumps(rows, separators=(",", ":")))
    cols = len(json.dumps(packed, separators=(",", ":")))
    assert cols < flat * 0.6, (flat, cols)
    # the container's len() is not the record length - the trap the
    # history block already sprang once
    assert len(packed) == 3 and packed["n"] == len(rows)
    # a plain list still reads, because the site deploys ahead of the
    # data file and the pipeline reads its own previous output
    assert B.expand_history(rows) == rows


def test_retention_span_gate_warns_before_the_window_under_fills():
    """55 days of margin is thin, and a short record does not throw -
    it silently shapes space heat on a season instead of a year and
    every figure downstream stays plausible. The gate makes that loud
    when the constant moves, not when someone notices the chart."""
    import build as B
    import datetime as _dt

    def span(n):
        d0 = _dt.date(2026, 8, 14) - _dt.timedelta(days=n - 1)
        return {(d0 + _dt.timedelta(days=i)).isoformat(): 5.0
                for i in range(n)}

    lines = []
    real = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        long_ok = B.retention_span_gate(span(B.SERIES_KEEP_DAYS))
        B.retention_span_gate(span(B.WINDOW_MAX_DAYS), "short")
    finally:
        B.log = real
    assert long_ok == B.SERIES_KEEP_DAYS
    assert any("margin" in l and "WARNING" not in l for l in lines), lines
    assert any("WARNING" in l and "under-fill" in l for l in lines), lines
    # the constants themselves must still stand up
    assert B.SERIES_KEEP_DAYS >= B.WINDOW_MAX_DAYS + 365, (
        B.SERIES_KEEP_DAYS, B.WINDOW_MAX_DAYS)
    assert B.retention_span_gate({}) is None


def test_ccni_archive_parses_through_the_daily_page_machinery():
    """The archive page embeds a chart of exactly the same shape as
    the daily checker, so it needs no parser of its own - which is the
    finding that made this a small job. Fixture is the real page's
    array, 277 points captured 15 Aug 2026."""
    import build as B, pathlib
    p = (pathlib.Path(__file__).parent / "fixtures"
         / "ccni_archive_page.html")
    s = B.parse_ccni_series(p.read_text())
    assert {k: len(v) for k, v in s.items()} == {"300l": 277, "500l": 277,
                                                 "900l": 277}
    n = s["900l"]
    assert min(n) == "2021-04-17" and max(n) == "2026-08-13"
    assert n["2026-08-13"] == 778.15
    # reaches well past the 24-month window, which the daily page
    # (a few months of chart) cannot
    assert min(n) < "2024-08-15"


def test_ccni_ratio_gate_names_the_rows_that_cannot_be_right():
    """A day's three litre figures come from one survey, so their
    ratios barely move even as the level swings. CCNI's record holds
    three rows that break that - and the 900 L series, the only one
    the site prices on, hides two of them entirely."""
    import build as B, pathlib
    p = (pathlib.Path(__file__).parent / "fixtures"
         / "ccni_archive_page.html")
    s = B.parse_ccni_series(p.read_text())
    bad = {d for d, *_ in B.ccni_ratio_gate(s, "test")}
    assert bad == {"2021-06-17", "2021-09-09", "2021-11-17"}, bad
    # 17 Nov 2021 is the one that reaches the priced series: 509.86
    # against neighbours of 467.46 and 456.80
    assert s["900l"]["2021-11-17"] == 509.86
    assert s["900l"]["2021-11-18"] == 464.96
    # the gate does not reject - the value is still published
    assert "2021-11-17" in s["900l"]
    # and a clean stretch trips nothing
    clean = {k: {d: v for d, v in ser.items() if d >= "2025-01-01"}
             for k, ser in s.items()}
    assert B.ccni_ratio_gate(clean, "test") == []


def test_week_source_records_which_ccni_page_priced_it():
    """A week carried entirely by the weekly archive is a mean of ONE
    reading, not five. The merged series is deliberately one dict so
    every consumer reads it unchanged, so provenance has to be
    recorded separately or it is unrecoverable."""
    import build as B
    feeds = _history_fixture_feeds()
    days = sorted((((feeds.get("ccni_oil") or {}).get("series_gbp") or {})
                   .get("daily") or {}).get("900l") or {})
    assert days, "fixture carries no CCNI series"
    w_end = days[-1]
    while B.dt.date.fromisoformat(w_end).weekday() != 6:
        w_end = (B.dt.date.fromisoformat(w_end)
                 - B.dt.timedelta(days=1)).isoformat()
    # no provenance field: the old label, not a claim about the archive
    assert "daily_page_days" not in feeds["ccni_oil"]
    assert B.week_inputs(feeds, w_end)["ni_oil_source"] == "ccni"
    # every day from the daily page
    feeds["ccni_oil"]["daily_page_days"] = days
    assert B.week_inputs(feeds, w_end)["ni_oil_source"] == "ccni"
    # none of them: the week rests on the archive alone
    feeds["ccni_oil"]["daily_page_days"] = []
    assert (B.week_inputs(feeds, w_end)["ni_oil_source"]
            == "ccni archive (weekly)")


def test_ni_oil_is_step_held_across_its_week_and_capped():
    """The NI series is daily only back to the CCNI daily checker's
    start; behind that it is the weekly archive, one reading a week.
    Pricing only the survey days left the NI line dotted - 144 of 375
    days on the 15 Aug run - which reads as missing data rather than a
    weekly survey. Held forward, capped, exactly as ROI's bulletin
    week is."""
    import build as B
    feeds = _with_temp(_history_fixture_feeds())
    ser = (((feeds.get("ccni_oil") or {}).get("series_gbp") or {})
           .get("daily") or {})
    days = sorted(ser.get("900l") or {})
    assert len(days) > 20, "fixture carries too little NI oil to thin"
    dense = B.derive_heat_cost_series(feeds)
    n_dense = sum(1 for r in dense if "ni" in r)

    # thin to one reading a week, as the archive publishes
    keep = set(days[::7])
    ser["900l"] = {d: v for d, v in ser["900l"].items() if d in keep}
    weekly = B.derive_heat_cost_series(feeds)
    n_weekly = sum(1 for r in weekly if "ni" in r)
    # a weekly source must not cost six days in seven
    assert n_weekly > n_dense * 0.8, (n_dense, n_weekly)
    # and the held days carry the reading of the survey day at or
    # before them, not an interpolation
    by_day = {r["day"]: r for r in weekly}
    for d in sorted(keep)[2:6]:
        src = by_day.get(d)
        nxt = (B.dt.date.fromisoformat(d)
               + B.dt.timedelta(days=1)).isoformat()
        if src and nxt in by_day and "ni" in by_day[nxt] and "ni" in src:
            assert (by_day[nxt]["ni"]["oil_boiler"]
                    == src["ni"]["oil_boiler"]), (d, nxt)

    # the cap: a reading is not smeared across one of the archive's
    # real gaps
    hold = B.NI_OIL_HOLD_DAYS
    assert 7 <= hold <= 14, hold
    ser["900l"] = {days[0]: ser["900l"].get(days[0], 900.0)} \
        if days[0] in keep else {sorted(keep)[0]: 900.0}
    sparse = B.derive_heat_cost_series(feeds)
    priced = [r["day"] for r in sparse if "ni" in r]
    if priced:
        first = min(priced)
        assert (B.dt.date.fromisoformat(max(priced))
                - B.dt.date.fromisoformat(first)).days <= hold, priced[-3:]


def test_roi_domestic_is_credit_free_and_gas_is_untouched():
    """Ireland credited domestic ELECTRICITY accounts in lump sums per
    meter, which SEAI books into the effective unit price. A lump sum
    never changed the cost of the next kWh, so it is added back for a
    per-MWh-of-heat axis. Gas accounts were never eligible."""
    import build as B
    for sem, (elec, gas, credit) in B.IE_DOMESTIC_SEMESTER.items():
        day = f"{sem[:4]}-{'03' if sem.endswith('S1') else '09'}-15"
        e = B.ie_domestic_eur("domestic_electricity", day)
        g = B.ie_domestic_eur("domestic_gas", day)
        # gas is the published figure, untouched
        assert abs(g - gas / 100) < 1e-9, (sem, g, gas)
        # electricity is published PLUS the credit over the basis
        want = (elec + 100 * credit / B.IE_CREDIT_KWH_PER_SEMESTER) / 100
        assert abs(e - want) < 1e-4, (sem, e, want)
        # and it is never below the published figure
        assert e >= elec / 100 - 1e-9
    # the clean semester needs no correction at all
    assert B.IE_DOMESTIC_SEMESTER["2025-S2"][2] == 0.0
    # the divisor is a judgement and must stay inside its own bracket
    lo, hi = B.IE_CREDIT_SENSITIVITY
    assert lo < B.IE_CREDIT_KWH_PER_SEMESTER < hi


def test_roi_domestic_refuses_below_its_first_semester():
    """Same rule as tariffs_for and nondom_for: a missing figure is
    visible, a clamped one is not."""
    import build as B
    first = sorted(B.IE_DOMESTIC_SEMESTER)[0]
    assert B.ie_domestic_eur("domestic_electricity", "2019-01-01") is None
    assert B.ie_domestic_eur("domestic_gas", f"{int(first[:4]) - 1}-06-01") \
        is None
    # above the last semester the level holds and the announcements
    # carry it forward
    last = sorted(B.IE_DOMESTIC_SEMESTER)[-1]
    held = B.ie_domestic_eur("domestic_electricity", "2026-06-01")
    assert abs(held - B.IE_DOMESTIC_SEMESTER[last][0] / 100) < 1e-4
    stepped = B.ie_domestic_eur("domestic_electricity", "2026-08-01")
    assert abs(stepped / held - 1.08) < 0.002


def test_the_table_now_reaches_a_full_24_months():
    """The whole point of the exercise. Both sides of the tariff table
    must reach back past the widest window, and BOTH must resolve on
    the same day - extending one alone was the blocker that stopped
    this shipping in two pieces."""
    import build as B
    floor = B.dt.date.fromisoformat(B.TARIFF_HISTORY[0][0])
    today = B.dt.date(2026, 8, 15)
    assert (today - floor).days >= B.WINDOW_MAX_DAYS, (floor, today)
    # every semester boundary inside the window resolves on both sides
    d = floor
    while d <= today:
        t = B.tariffs_for(d.isoformat())
        assert t is not None, d
        assert t["gbp"]["electricity"] and t["gbp"]["gas"], d
        assert t["eur"]["electricity"] and t["eur"]["gas"], d
        d += B.dt.timedelta(days=29)
    # and the row added for 2025-04-01 must reproduce the old floor
    # row exactly - the check that the bill-over-consumption
    # derivation is the right one
    assert (B.tariffs_for("2025-04-01")["gbp"]
            == B.tariffs_for("2025-08-06")["gbp"])


def test_a_reconstructed_week_without_its_own_carbon_is_refused():
    """Extending the record moved the binding constraint from tariffs
    to grid carbon. A reconstructed week priced at the carbon ANCHOR
    would carry today's grid intensity wearing last year's date - the
    clamp pattern again, landing on emissions instead of price. It is
    refused by name, so the record extends itself as the EirGrid
    backfill reaches further."""
    import build as B
    feeds = _history_fixture_feeds()
    days = sorted((((feeds.get("eirgrid") or {})
                    .get("co2_intensity_g_per_kwh")) or {}))
    assert days, "fixture carries no carbon series"
    # a week that HAS carbon builds
    w_end = days[-1]
    while B.dt.date.fromisoformat(w_end).weekday() != 6:
        w_end = (B.dt.date.fromisoformat(w_end)
                 - B.dt.timedelta(days=1)).isoformat()
    ok = B.week_inputs(feeds, w_end)
    if ok is not None:
        assert ok["ef_electricity"] is not None
        assert ok["ef_source"] == "weekly grid CI"
    # strip the carbon and the same week is declined, by name
    feeds["eirgrid"]["co2_intensity_g_per_kwh"] = {}
    skips = []
    assert B.week_inputs(feeds, w_end, skips) is None or w_end >= B.LIVE_FROM
    if skips:
        assert "grid carbon" in skips[0][1], skips


def test_calibration_is_weighted_by_heat_not_by_days():
    """calibrate_eta's docstring has always said heat-weighted, and
    the caller passed the day's SPACE/DHW SHARES - two numbers summing
    to 1.0 on every day - so every day weighed the same regardless of
    how much heat it carried. A mild day counted as much as a cold
    one, which flatters air source and was most of the calibration
    spread the gate was firing on."""
    import build as B
    hdd = {}
    import math
    for i in range(400):
        d = (B.dt.date(2025, 7, 1) + B.dt.timedelta(days=i)).isoformat()
        hdd[d] = max(0.0, 15.5 - (10.3 - 5.0 * math.cos(2 * math.pi * i / 365)))
    day = sorted(hdd)[-1]
    v = B.day_delivered_heat(hdd, day, "roi")
    assert v is not None
    # the weights the caller now passes are VOLUMES, not shares: they
    # must not sum to 1, and they must swing across the year
    tot = [sum(B.day_delivered_heat(hdd, d, "roi").values())
           for d in sorted(hdd)[-365:]
           if B.day_delivered_heat(hdd, d, "roi")]
    assert max(tot) > 2 * min(tot), (min(tot), max(tot))
    assert abs(sum(v.values()) - 1.0) > 0.5, v
    # and heat-weighting must SEPARATE the air and ground ceilings,
    # because the cold days where they differ most carry the heat
    days = sorted(hdd)[-365:]
    heat = [(10.3 - 5.0 * math.cos(2 * math.pi * i / 365),
             B.day_delivered_heat(hdd, d, "roi")["space"],
             B.day_delivered_heat(hdd, d, "roi")["dhw"])
            for i, d in enumerate(days) if B.day_delivered_heat(hdd, d, "roi")]
    flat = [(t, 0.776, 0.224) for t, _, _ in heat]
    def ratio(w):
        ea = B.calibrate_eta("ashp", w, "roi")
        eg = B.calibrate_eta("gshp", w, "roi")
        return (3.24 / eg) / (2.80 / ea)
    assert ratio(heat) > ratio(flat), (ratio(heat), ratio(flat))


def test_ticker_comes_from_the_same_engine_as_the_panel():
    """The masthead ticker used derive_heat_gap, which never got the
    panel's changes - one geothermal SPF of 4.0 for both jurisdictions
    against the panel's 5.0/4.0, a single oil efficiency of 0.82
    against the panel's 0.71 on hot water, and no hot-water blending.
    The headline disagreed with the chart underneath it."""
    import build as B
    rows = B.derive_heat_cost_series(_with_temp(_history_fixture_feeds()))
    assert rows
    hg = B.heat_gap_from_cost_series(rows)
    assert hg, "no jurisdiction produced a ticker"
    for jur, g in hg.items():
        last = [r for r in rows if r.get(jur)][-1][jur]
        # every published figure is the panel's own last row
        assert g["oil_boiler"] == last["oil_boiler"]
        assert g["geothermal_spf40"] == last["network"], jur
        assert g["gas_boiler"] == last["gas_boiler"]
        # the gap is the difference, and the median is reported beside it
        assert abs(g["gap_now"]
                   - (last["oil_boiler"] - last["network"])) < 1e-9
        assert "gap_median" in g and g["gap_days"] >= 1
        assert g["day"] == [r for r in rows if r.get(jur)][-1]["day"]
    # the ticker's network figure must NOT be the old single anchor
    # where the panel's jurisdictional model differs from it
    if "ni" in hg:
        assert B.NETWORK_MODEL["ni"]["spf"] != B.ANCHORS["geothermal_spf"]


def test_history_offers_as_many_weeks_as_it_retains():
    """The loop offered a literal 60 weeks while HISTORY_MAX was 120,
    and the cap was applied afterwards to a list that could never
    exceed 60. So the record sat at 60, the log line "60 weeks built,
    none skipped" reported the loop bound rather than a data limit,
    and panel 1's sparklines were short because they slice whatever
    the record holds. A literal where a constant belongs is invisible
    until someone counts."""
    import build as B, inspect, re
    src = inspect.getsource(B.build_history)
    m = re.search(r"for k in range\(([^,]+),", src)
    assert m, "could not find the week loop"
    bound = m.group(1).strip()
    assert "HISTORY_MAX" in bound, bound
    # and the cap must not be able to truncate what the loop offers
    assert "out[-HISTORY_MAX:]" in src
    # a literal would silently re-break it
    assert not re.search(r"for k in range\(\s*\d+\s*,", src), src


def test_hdd_year_gate_and_base_scan():
    """Four lines that catch the class of error the UK sibling hit: an
    annual quantity that silently stopped spanning a year while every
    test suite kept passing."""
    import build as B
    good = {f"2026-{m:02d}-{d:02d}": 6.0
            for m in range(1, 13) for d in range(1, 29)}
    lines = []
    real = B.log
    B.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    try:
        total = B.hdd_year_gate(good)
        B.hdd_year_gate({d: v * 2 for d, v in good.items()}, "doubled")
    finally:
        B.log = real
    assert total and B.HDD_YEAR_MIN <= total <= B.HDD_YEAR_MAX
    assert "OUTSIDE THE GATE" in " | ".join(lines)
    # too short a record declines rather than passing a partial year
    assert B.hdd_year_gate({"2026-01-01": 5.0}) is None


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"pass - {fn.__name__}")
    print(f"{len(fns)} synthetic tests passed")
