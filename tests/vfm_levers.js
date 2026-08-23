/* vfm_levers.js - the ONE evaluator for Panel 6's live levers.
 *
 * The browser never re-implements the appraisal. Python publishes
 * closed-form coefficients (derive_vfm_phased -> coeffs) and this
 * function evaluates them exactly. A test pins this file against the
 * Python appraisal at the corners of the lever space, so if the two
 * ever disagree, a build fails rather than a page drifting.
 *
 * c: coeffs for one jurisdiction, from the payload.
 * L: {s, ob, capm, wh, rc, lr, a_sh, a_dp}
 * returns {bcr, cap_pv, ben_pv, breakeven}
 */
function vfmLeverEval(c, L) {
  var m_wh = 1.0 - L.wh * (1.0 - L.rc);
  var s0 = (1 - c.deep_weight) * L.a_sh
             * ((1 - c.ss_shallow) + c.ss_shallow * m_wh)
           + c.deep_weight * L.a_dp;
  var s1 = (1 - c.deep_weight) * L.a_sh * c.ss_shallow * m_wh
           + c.deep_weight * L.a_dp * c.ss_deep;
  var sinc = c.d0 * (s0 * L.capm - c.asc_eur_kw)
             - L.lr * c.d1 * s1 * L.capm;
  var cap = ((c.mw / (1000.0 * c.build_years)) * sinc
             - (c.cool_capital_eur_m / c.build_years) * c.d0)
            * (1 + c.devex) * (1 + L.ob);
  var gross = c.flat_gross_pv_eur_m + c.carbon_gross_pv_eur_m;
  var ben = (1 - L.s) * gross;
  return {
    bcr: ben / Math.max(cap, 1e-9),
    cap_pv: cap,
    ben_pv: ben,
    breakeven: 1.0 - cap / Math.max(gross, 1e-9)
  };
}
if (typeof module !== "undefined") { module.exports = { vfmLeverEval: vfmLeverEval }; }
if (typeof window !== "undefined") { window.vfmLeverEval = vfmLeverEval; }
