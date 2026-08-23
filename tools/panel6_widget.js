/* panel6_widget.js - the live-lever widget, injected by
 * scripts/build.py regenerate_panel6(). Do not edit in the page;
 * edit here and rerun the generator. Requires vfmLeverEval (injected
 * alongside, from tools/vfm_levers.js) and window.VFM_PAYLOAD.
 *
 * Currency: the evaluator runs in euro for both jurisdictions - the
 * rate cancels in the BCR - and the North DISPLAYS in sterling at the
 * published semester rate, per the panel's own-currency convention.
 */
(function(){
  // Outside a browser (the test harness evaluates every script
  // block) there is nothing to mount on and nothing to poll for.
  if (typeof window==="undefined" || typeof document==="undefined"){return;}
  // On docs/panel6.html the payload is inline and this runs at once.
  // On docs/index.html the payload arrives async with the daily data,
  // so poll briefly for it rather than assuming script order.
  var tries=0;
  (function wait(){
    var P=(window.VFM_PAYLOAD&&window.VFM_PAYLOAD.derived&&window.VFM_PAYLOAD.derived.vfm)||null;
    if(!P||!P.phased||!P.phased.levers){
      if(++tries<100){setTimeout(wait,200);}
      return;
    }
    init(P);
  })();
  function init(P){
  var LV=P.phased.levers, JUR=P.phased.jur, cur="roi";
  var state={ob:null,capm:null,a_sh:null,a_dp:null,lr:null,s:{},wh:{}};
  LV.headline.forEach(function(l){
    if(l.per_jur){["roi","ni"].forEach(function(j){state[l.id][j]=l.default[j];});}
    else{state[l.id]=l.default;}
  });
  LV.capital_fold.forEach(function(l){state[l.id]=l.default;});
  var rc=LV.hardwired.connection_relcost;

  function money(j){ // symbol + conversion for display only
    if(JUR[j].currency==="GBP"){
      return {sym:"\u00a3", f:JUR[j].coeffs.gbp_per_eur};
    }
    return {sym:"\u20ac", f:1.0};
  }
  function evalJur(j){
    var c=JUR[j].coeffs;
    return vfmLeverEval(c,{s:state.s[j],ob:state.ob,capm:state.capm,
      wh:state.wh[j],rc:rc,lr:state.lr,a_sh:state.a_sh,a_dp:state.a_dp});
  }
  function fmt(x,d){return x.toFixed(d===undefined?2:d);}

  var box=document.createElement("section");
  box.id="vfm-lever-widget";
  box.style.cssText="max-width:820px;margin:2.5rem auto;padding:1.2rem 1.4rem;border:1px solid #ccc;border-radius:8px;font:inherit";
  function slider(label,min,max,val,step,oninput,suffix){
    var w=document.createElement("label");
    w.style.cssText="display:block;margin:.55rem 0";
    var t=document.createElement("div");
    var b=document.createElement("b");
    t.appendChild(document.createTextNode(label+" "));t.appendChild(b);
    var r=document.createElement("input");
    r.type="range";r.min=min;r.max=max;r.step=step;r.value=val;
    r.style.cssText="width:100%";
    function show(v){b.textContent=suffix==="%"?Math.round(v*100)+"%":Math.round(v)+(suffix||"");}
    r.addEventListener("input",function(){oninput(parseFloat(r.value));show(parseFloat(r.value));render();});
    show(val);w.appendChild(t);w.appendChild(r);
    w._sync=function(v){r.value=v;show(v);};
    return w;
  }
  var h=document.createElement("h3");
  h.textContent="Try the levers";box.appendChild(h);
  var intro=document.createElement("p");
  intro.style.cssText="font-size:.92em;color:#444";
  intro.textContent="Four judgements the appraisal turns on. The shortfall is a programme mean, not a project number - it carries both attrition and underperformance of the commissioned fleet. Connection cost of waste-heat coupling is held at its stated default; cooling connections are held at 12%. The Republic is appraised in euro and the North in sterling, each at real 2025 prices.";
  box.appendChild(intro);
  var tog=document.createElement("div");tog.style.cssText="margin:.4rem 0 .8rem";
  ["roi","ni"].forEach(function(j){
    var btn=document.createElement("button");
    btn.textContent=j==="roi"?"Republic":"North";
    btn.style.cssText="margin-right:.5rem;padding:.25rem .8rem";
    btn.addEventListener("click",function(){cur=j;syncPerJur();render();});
    tog.appendChild(btn);
  });
  box.appendChild(tog);

  var sShort=slider("Subsurface shortfall, programme mean",0,0.45,state.s[cur],0.005,
    function(v){state.s[cur]=v;},"%");
  var sOb=slider("Optimism bias",0,0.66,state.ob,0.01,
    function(v){state.ob=v;},"%");
  var sCap=slider("Subsurface capital",0.75,1.25,state.capm,0.01,
    function(v){state.capm=v;},"x");
  var sWh=slider("Waste-heat coupling share",0,0.40,state.wh[cur],0.005,
    function(v){state.wh[cur]=v;},"%");
  [sShort,sOb,sCap,sWh].forEach(function(w){box.appendChild(w);});

  var det=document.createElement("details");
  var sm=document.createElement("summary");sm.textContent="Capital detail (euro anchors, both jurisdictions)";
  det.appendChild(sm);
  var sASh=slider("Shallow FOAK anchor, EUR/kW",1500,3300,state.a_sh,10,
    function(v){state.a_sh=v;},"");
  var sADp=slider("Deep FOAK anchor, EUR/kW",
    LV.capital_fold[1].range[0],LV.capital_fold[1].range[1],state.a_dp,10,
    function(v){state.a_dp=v;},"");
  var sLr=slider("Programme learning rate",0.25,0.40,state.lr,0.005,
    function(v){state.lr=v;},"%");
  [sASh,sADp,sLr].forEach(function(w){det.appendChild(w);});
  box.appendChild(det);

  var outEl=document.createElement("div");
  outEl.style.cssText="margin-top:1rem;padding:.8rem;border-top:1px solid #ddd";
  box.appendChild(outEl);
  var reset=document.createElement("button");
  reset.textContent="Reset to the panel's defaults";
  reset.style.cssText="margin-top:.6rem;padding:.25rem .8rem";
  reset.addEventListener("click",function(){
    LV.headline.forEach(function(l){
      if(l.per_jur){["roi","ni"].forEach(function(j){state[l.id][j]=l.default[j];});}
      else{state[l.id]=l.default;}});
    LV.capital_fold.forEach(function(l){state[l.id]=l.default;});
    syncAll();render();
  });
  box.appendChild(reset);

  function syncPerJur(){sShort._sync(state.s[cur]);sWh._sync(state.wh[cur]);}
  function syncAll(){
    syncPerJur();sOb._sync(state.ob);sCap._sync(state.capm);
    sASh._sync(state.a_sh);sADp._sync(state.a_dp);sLr._sync(state.lr);
  }
  function render(){
    var name=cur==="roi"?"Republic":"North";
    var r=evalJur(cur), hi=(LV.headline[0].range[cur]||[0,0.45])[1];
    var inside=r.breakeven<=hi;
    var d=JUR[cur], mny=money(cur);
    outEl.innerHTML=
      "<p style='margin:.2rem 0'><b>"+name+" BCR "+fmt(r.bcr)+"</b>"+
      " &nbsp;(published default "+fmt(d.bcr)+", before shortfall "+fmt(d.bcr_before_shortfall)+")</p>"+
      "<p style='margin:.2rem 0'>Benefits "+mny.sym+fmt(r.ben_pv*mny.f,0)+"m against capital "+
      mny.sym+fmt(r.cap_pv*mny.f,0)+"m, present value, real 2025.</p>"+
      "<p style='margin:.2rem 0'>At these settings the case stops passing at a programme shortfall of <b>"+
      Math.round(r.breakeven*1000)/10+"%</b> - "+
      (inside?"<b>inside</b> the declared range of 0-"+Math.round(hi*100)+"%, so the range contains failure":
       "outside the declared range of 0-"+Math.round(hi*100)+"%")+".</p>";
  }
  syncAll();render();
  var host=document.getElementById("vfm")||document.body;
  host.appendChild(box);
  }
})();
