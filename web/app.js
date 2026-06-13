/* World Cup probability dashboard — router + views over window.WC_DATA */
(function () {
  const D = window.WC_DATA;
  const $ = (s, r = document) => r.querySelector(s);
  if (!D) { document.body.innerHTML = "<p style='padding:40px'>data.js 未加载</p>"; return; }
  const pct = (x, d = 1) => (x == null ? "—" : (100 * x).toFixed(d) + "%");
  const esc = s => String(s == null ? "" : s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const bold = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const fo = p => (1 / Math.max(p, 1e-6)).toFixed(2);
  const INJ = D.injuries || {};
  const PALETTE = ["#22d3ee", "#3b82f6", "#a855f7", "#f472b6", "#34d399", "#fbbf24", "#fb7185", "#94a3b8", "#38bdf8", "#c084fc"];

  const NAV = [
    ["home", "🏠", "首页"], ["matches", "⚽", "比赛预测"], ["score", "🎯", "比分预测"],
    ["odds", "💱", "赔率比较"], ["picks", "⭐", "最佳选择"], ["groups", "📊", "小组形势"],
    ["analytics", "🔬", "数据分析"], ["mirror", "🔮", "照妖镜"],
  ];

  /* ---------- shell chrome ---------- */
  function chrome() {
    $("#topnav").innerHTML = NAV.map(([id, , l]) => `<a href="#${id}" data-v="${id}">${esc(l)}</a>`).join("");
    $("#sidenav").innerHTML = NAV.map(([id, ic, l]) => `<a href="#${id}" data-v="${id}"><span class="ic">${ic}</span>${esc(l)}</a>`).join("");
    $("#asof-chip").textContent = "数据更新 " + D.meta.asof;
    const lo = D.live_odds;
    $("#live-chip").textContent = lo ? `实时赔率 ${lo.asof || ""}` : "";
    if (!lo) $("#live-chip").style.display = "none";
    $("#side-update").innerHTML = `本届数据：${D.meta.asof}<br>实时赔率：${lo ? esc(lo.asof) : "—"}<br>模拟：${D.meta.n_sims.toLocaleString()} 次`;
    $("#foot-line").innerHTML += ` · 模型 b0=${D.meta.fit.b0} b1=${D.meta.fit.b1} ρ=${D.meta.fit.rho}`;
  }

  /* ---------- match card (shared) ---------- */
  function formDots(form) {
    return `<span class="form-dots">${(form || []).slice(-5).map(f => `<span class="fdot f${f.res}" title="${esc(f.date)} ${esc(f.opp)} ${f.gf}-${f.ga}">${f.res}</span>`).join("")}</span>`;
  }
  function matchCard(fx) {
    const ph = fx.p_home, pdr = fx.p_draw, pa = fx.p_away;
    const seg = (w, c, l) => `<span class="${c}" style="width:${100 * w}%">${100 * w >= 12 ? l : ""}</span>`;
    const facs = (fx.factors || []).filter(f => f.label !== "近期状态").map(f =>
      `<div class="fac lean-${f.lean}"><span class="dot"></span><span class="fl">${esc(f.label)}</span><span class="fd">${esc(f.detail)}</span></div>`).join("");
    const sl = (fx.top_scores || []).slice(0, 3).map(s => `<span class="sl">${esc(s.score)}<small>${esc(s.p)}</small></span>`).join("");
    const m = fx.markets;
    const mkts = m ? `<div class="mkts">
      <span class="mkt">大 2.5 <b>${pct(m.over_under["2.5"].over, 0)}</b></span>
      <span class="mkt">双方进球 <b>${pct(m.btts.yes, 0)}</b></span>
      <span class="mkt">主 -1.5 <b>${pct(m.ah["-1.5"].p_home, 0)}</b></span>
      <span class="mkt">公平赔率 <span class="fo">${fo(ph)}/${fo(pdr)}/${fo(pa)}</span></span></div>` : "";
    const oc = (fx.odds_compare || []).find(r => r.market === "胜平负");
    const mk = oc ? `<div class="mc-market"><span>实时赔率</span><div class="mm-bar">
        <i class="mm-h" style="width:${100 * (1 / fx.odds_compare[0].book)}%"></i></div>
        <span>书 ${fx.odds_compare.filter(r => r.market === "胜平负").map(r => r.book).join("/")}</span></div>` : "";
    const injLine = (t, fl) => { const it = INJ[t]; if (!it || !it.length) return "";
      return `<div class="inj"><span class="ic">🩹</span><span>${fl} ${esc(t)} 缺阵/存疑：${it.slice(0, 3).map(x => esc(x.player) + (x.status && x.status !== "out" ? `(${esc(x.status)})` : "")).join("、")}${it.length > 3 ? " 等" : ""}</span></div>`; };
    const badge = fx.stage === "group" ? "组 " + fx.group : String(fx.stage).toUpperCase();
    return `<div class="mc">
      <div class="mc-head"><span class="badge">${esc(badge)}</span><span class="mc-date">${esc(fx.date)}</span></div>
      <div class="mc-teams">
        <div class="mc-team home"><span class="fn">${fx.flagH} ${esc(fx.home)}</span><span class="elo">Elo ${fx.elo_h} ${formDots(fx.form_h)}</span></div>
        <div class="mc-xg">${fx.lambda_h.toFixed(1)}–${fx.lambda_a.toFixed(1)}<small>预期</small></div>
        <div class="mc-team away"><span class="fn">${esc(fx.away)} ${fx.flagA}</span><span class="elo">${formDots(fx.form_a)} Elo ${fx.elo_a}</span></div>
      </div>
      <div class="wdl">${seg(ph, "win", pct(ph, 0))}${seg(pdr, "draw", pct(pdr, 0))}${seg(pa, "loss", pct(pa, 0))}</div>
      <div class="wdl-leg"><span>胜 <b>${pct(ph)}</b></span><span>平 <b>${pct(pdr)}</b></span><span>负 <b>${pct(pa)}</b></span></div>
      <div class="scorelines">${sl}</div>
      <div class="narr">${bold(fx.narrative)}</div>
      <div class="factors">${facs}</div>
      ${mkts}${mk}${injLine(fx.home, fx.flagH)}${injLine(fx.away, fx.flagA)}</div>`;
  }
  const upcoming = () => D.fixtures.slice().sort((a, b) => a.date.localeCompare(b.date));

  /* ---------- HOME ---------- */
  function homeHTML() {
    const all = D.credibility.backtest.find(x => x.wc === "all") || {};
    const stats = [["🏳️", D.meta.tournament.teams, "参赛球队"], ["📅", "104", "比赛场次"],
      ["📈", (D.meta.n_sims / 1000) + "k+", "模拟次数"], ["🎯", (all.rps_model || 0).toFixed(3), "回测 RPS（越低越好）"]];
    const feats = [["🧬", "多维数据", "Elo·状态·市值·赛程·伤停"], ["🧠", "统计 + ML", "Dixon-Coles 双泊松 + Elo 回归"],
      ["🛡️", "大量模拟", "5 万次蒙特卡洛 + 多届回测"], ["⏱️", "实时更新", "the-odds-api 实时赔率对标"]];
    return `<section class="view" id="view-home">
      <div class="hero"><div class="tag">FIFA WORLD CUP 2026 · 🇺🇸 🇨🇦 🇲🇽</div>
        <h1>世界杯夺冠概率预测</h1>
        <p>基于大数据与统计/机器学习模型的专业预测分析。数据更新于 <b>${D.meta.asof}</b>，赛事 ${esc(D.meta.tournament.dates)}。</p></div>
      <div class="stats">${stats.map(([i, v, k]) => `<div class="stat"><div class="si">${i}</div><div><div class="sv">${v}</div><div class="sk">${esc(k)}</div></div></div>`).join("")}</div>
      <div class="home-grid">
        <div class="col">
          <div class="panel"><div class="p-title">夺冠概率 TOP 10 <span class="more" data-go="picks">完整排名 →</span></div>
            <div class="champ-flex"><div class="cbars" id="champ-bars"></div>
              <div class="donut-wrap"><div class="donut" id="donut"></div><div class="legend" id="donut-legend"></div></div></div></div>
          <div class="panel"><div class="p-title">实力评分（Elo）走势 · 头部球队近 16 个月</div>
            <svg class="trend-svg" id="trend-svg" viewBox="0 0 720 230"></svg><div class="trend-legend" id="trend-legend"></div></div>
        </div>
        <div class="col">
          <div class="panel"><div class="p-title">球队夺冠概率排行 <span class="more" data-go="picks">查看全部 →</span></div><table class="rank-t" id="rank-table"></table></div>
          <div class="panel"><div class="p-title">近期重点比赛 <span class="more" data-go="matches">查看全部 →</span></div><div id="recent-matches"></div></div>
          <div class="panel"><div class="p-title">预测模型优势</div><div class="feats">${feats.map(([i, t, d]) => `<div class="feat"><div class="fi">${i}</div><div class="ft">${esc(t)}</div><div class="fd">${esc(d)}</div></div>`).join("")}</div></div>
        </div></div></section>`;
  }
  function homePost() {
    const lb = [...D.leaderboard].sort((a, b) => b.p_champion - a.p_champion);
    const top = lb.slice(0, 10), mx = top[0].p_champion;
    $("#champ-bars").innerHTML = top.map((t, i) => `<div class="cbar"><span class="rk">${i + 1}</span><span class="fl">${t.flag}</span>
      <div><div class="nm">${esc(t.team)}</div><div class="track"><span class="fill" style="width:${100 * t.p_champion / mx}%"></span></div></div>
      <span class="pv">${pct(t.p_champion)}</span></div>`).join("");
    drawDonut($("#donut"), top.slice(0, 8), lb);
    drawTrend();
    // ranking table
    $("#rank-table").innerHTML = `<thead><tr><th class="l">排名 / 球队</th><th>夺冠概率</th><th>vs市场</th></tr></thead><tbody>` +
      lb.slice(0, 8).map((t, i) => {
        const d = t.diff;
        const tr = d == null ? `<span class="trend-eq">—</span>` : d > 0.003 ? `<span class="trend-up">▲${(100 * d).toFixed(1)}</span>` : d < -0.003 ? `<span class="trend-dn">▼${(100 * -d).toFixed(1)}</span>` : `<span class="trend-eq">—</span>`;
        return `<tr><td class="l tm"><span class="rkn">${i + 1}</span>${t.flag} ${esc(t.team)}</td><td><b>${pct(t.p_champion)}</b></td><td>${tr}</td></tr>`;
      }).join("") + `</tbody>`;
    // recent matches
    $("#recent-matches").innerHTML = upcoming().slice(0, 5).map(fx => {
      const pk = fx.p_home >= fx.p_away ? [fx.home, fx.p_home, "胜"] : [fx.away, fx.p_away, "胜"];
      return `<div class="rmatch"><span class="rm-d">${esc(fx.date)}</span>
        <span class="rm-t">${fx.flagH} ${esc(fx.home)} <span class="dim">vs</span> ${esc(fx.away)} ${fx.flagA}</span>
        <span class="rm-r">${esc(pk[0])} ${pct(pk[1], 0)}</span></div>`;
    }).join("");
  }
  function drawDonut(el, top, lb) {
    const others = Math.max(0, 1 - top.reduce((s, t) => s + t.p_champion, 0));
    const segs = top.map((t, i) => ({ name: t.team, flag: t.flag, v: t.p_champion, c: PALETTE[i % PALETTE.length] }));
    if (others > 0.001) segs.push({ name: "其他", v: others, c: "#3a425a", flag: "" });
    const R = 100, r = 64, cx = 115, cy = 115; let ang = -Math.PI / 2; const arcs = [];
    segs.forEach(s => {
      const a2 = ang + s.v * 2 * Math.PI;
      const x1 = cx + R * Math.cos(ang), y1 = cy + R * Math.sin(ang), x2 = cx + R * Math.cos(a2), y2 = cy + R * Math.sin(a2);
      const xi2 = cx + r * Math.cos(a2), yi2 = cy + r * Math.sin(a2), xi1 = cx + r * Math.cos(ang), yi1 = cy + r * Math.sin(ang);
      const lg = (a2 - ang) > Math.PI ? 1 : 0;
      arcs.push(`<path d="M${x1} ${y1} A${R} ${R} 0 ${lg} 1 ${x2} ${y2} L${xi2} ${yi2} A${r} ${r} 0 ${lg} 0 ${xi1} ${yi1} Z" fill="${s.c || "#3a425a"}"/>`);
      ang = a2;
    });
    const lead = segs[0];
    el.innerHTML = `<svg viewBox="0 0 230 230" width="230" height="230">${arcs.join("")}</svg>
      <div class="ctr"><div class="t">${lead.flag} ${esc(lead.name)}</div><div class="v">${pct(lead.v)}</div><div class="s">夺冠概率</div></div>`;
    $("#donut-legend").innerHTML = segs.map(s => `<span><i style="background:${s.c || "#3a425a"}"></i>${esc(s.name)}</span>`).join("");
  }
  function drawTrend() {
    const et = D.elo_trend; if (!et || !et.teams.length) return;
    const svg = $("#trend-svg"), W = 720, H = 230, pad = { l: 38, r: 12, t: 12, b: 22 };
    let allE = [], maxLen = 0;
    et.teams.forEach(t => { (et.series[t] || []).forEach(p => allE.push(p.elo)); maxLen = Math.max(maxLen, (et.series[t] || []).length); });
    const lo = Math.min(...allE) - 10, hi = Math.max(...allE) + 10;
    const sx = i => pad.l + (i / (maxLen - 1)) * (W - pad.l - pad.r);
    const sy = v => H - pad.b - (v - lo) / (hi - lo) * (H - pad.t - pad.b);
    let g = "";
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4, y = sy(v);
      g += `<line x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}" stroke="rgba(255,255,255,.05)"/><text x="4" y="${y + 3}" fill="#67728f" font-size="9">${Math.round(v)}</text>`; }
    et.teams.forEach((t, ti) => {
      const s = et.series[t] || []; if (!s.length) return;
      const pts = s.map((p, i) => `${sx(i)},${sy(p.elo)}`).join(" ");
      g += `<polyline points="${pts}" fill="none" stroke="${PALETTE[ti % PALETTE.length]}" stroke-width="2" opacity=".9"/>`;
      g += `<circle cx="${sx(s.length - 1)}" cy="${sy(s[s.length - 1].elo)}" r="3" fill="${PALETTE[ti % PALETTE.length]}"/>`;
    });
    svg.innerHTML = g;
    $("#trend-legend").innerHTML = et.teams.map((t, i) => `<span><i style="background:${PALETTE[i % PALETTE.length]}"></i>${et.flags[t] || ""} ${esc(t)}</span>`).join("");
  }

  /* ---------- MATCHES ---------- */
  function matchesHTML() {
    return `<section class="view" id="view-matches"><div class="vhead"><h1>比赛预测</h1><span class="sub">每场胜平负 / 比分 / 判断依据 / 全盘口 / 伤停</span></div>
      <div class="filters" id="match-filters"></div><div class="match-grid" id="match-grid"></div></section>`;
  }
  function matchesPost() {
    const dates = [...new Set(upcoming().map(f => f.date))].sort();
    let active = "all";
    const grid = $("#match-grid"), filt = $("#match-filters");
    filt.innerHTML = `<button class="fbtn active" data-d="all">全部 ${D.fixtures.length} 场</button>` + dates.map(d => `<button class="fbtn" data-d="${d}">${d.slice(5)}</button>`).join("");
    const draw = () => grid.innerHTML = upcoming().filter(f => active === "all" || f.date === active).map(matchCard).join("");
    filt.addEventListener("click", e => { const b = e.target.closest(".fbtn"); if (!b) return;
      filt.querySelectorAll(".fbtn").forEach(x => x.classList.remove("active")); b.classList.add("active"); active = b.dataset.d; draw(); });
    draw();
  }

  /* ---------- SCORE PREDICTION ---------- */
  function scoreHTML() {
    const cards = upcoming().map(fx => {
      const m = fx.markets; if (!m || !m.grid) return "";
      const grid = m.grid, mx = Math.max(...grid.flat());
      let heat = `<div class="heat"><div class="axh">客队进球 →</div>`;
      heat += `<div></div>` + grid[0].map((_, j) => `<div class="lbl">${j}</div>`).join("");
      grid.forEach((row, i) => { heat += `<div class="lbl">${i}</div>` + row.map((p, j) => {
        const a = Math.pow(p / mx, 0.6);
        return `<div class="hc" style="background:rgba(34,211,238,${(0.04 + 0.92 * a).toFixed(2)})" title="${i}-${j} ${pct(p)}">${p >= 0.03 ? Math.round(p * 100) : ""}</div>`; }).join(""); });
      heat += `</div>`;
      const sb = fx.score_breakdown || {}, br = sb.by_result || {};
      const bars = (sb.top || []).slice(0, 6).map(c => `<div class="cs-bar"><span>${esc(c.score)}</span><div class="track"><span class="fill" style="width:${100 * c.p / (sb.top[0].p)}%"></span></div><span>${pct(c.p)}</span></div>`).join("");
      const top1 = (sb.top || [{}])[0];
      const ou = m.over_under["2.5"];
      const an = `最可能比分 <strong>${esc(top1.score || "")}</strong>（${pct(top1.p)}）。` +
        `${esc(fx.home)}赢盘下最可能 ${br.home ? esc(br.home.score) : "—"}，${esc(fx.away)}赢盘下 ${br.away ? esc(br.away.score) : "—"}，平局多为 ${br.draw ? esc(br.draw.score) : "—"}。` +
        `预期进球 ${fx.lambda_h.toFixed(1)}–${fx.lambda_a.toFixed(1)}，${ou.over >= 0.5 ? "大球" : "小球"}略占优（大 2.5 ${pct(ou.over, 0)}）。`;
      return `<div class="mc"><div class="mc-head"><span class="badge">${fx.stage === "group" ? "组 " + fx.group : String(fx.stage).toUpperCase()}</span><span class="mc-date">${esc(fx.date)}</span></div>
        <div class="mc-teams"><div class="mc-team home"><span class="fn">${fx.flagH} ${esc(fx.home)}</span></div><div class="mc-xg">${fx.lambda_h.toFixed(1)}–${fx.lambda_a.toFixed(1)}<small>预期</small></div><div class="mc-team away"><span class="fn">${esc(fx.away)} ${fx.flagA}</span></div></div>
        ${heat}<div class="cs-bars">${bars}</div>
        <div class="byres"><div class="br"><div class="k">主胜比分</div><div class="v">${br.home ? esc(br.home.score) : "—"}</div></div><div class="br"><div class="k">平局比分</div><div class="v">${br.draw ? esc(br.draw.score) : "—"}</div></div><div class="br"><div class="k">客胜比分</div><div class="v">${br.away ? esc(br.away.score) : "—"}</div></div></div>
        <div class="narr">${an}</div></div>`;
    }).join("");
    return `<section class="view" id="view-score"><div class="vhead"><h1>比分预测</h1><span class="sub">Dixon-Coles 比分概率网格（热力图）+ 各结果最可能比分 + 分析</span></div>
      <div class="score-grid">${cards}</div></section>`;
  }

  /* ---------- ODDS COMPARISON ---------- */
  function oddsHTML() {
    const cards = upcoming().filter(f => (f.odds_compare || []).length).map(fx => {
      const rows = fx.odds_compare; let body = ""; let lastM = "";
      rows.forEach(r => {
        if (r.market !== lastM) { body += `<tr class="grp"><td class="l" colspan="5">${esc(r.market)}</td></tr>`; lastM = r.market; }
        const cls = r.edge > 0.03 ? "edge-pos" : r.edge < -0.03 ? "edge-neg" : "";
        body += `<tr><td class="l">${esc(r.sel)}</td><td>${pct(r.model_p, 0)}</td><td>${r.fair}</td><td>${r.book}</td><td class="${cls}">${r.edge > 0 ? "+" : ""}${(100 * r.edge).toFixed(0)}%</td></tr>`;
      });
      const big = rows.slice().sort((a, b) => b.edge - a.edge)[0];
      const an = `模型与市场最大分歧：<strong>${esc(big.sel)}</strong>（模型 ${pct(big.model_p, 0)} vs 实时赔率隐含 ${pct(big.book_imp, 0)}，名义 EV ${big.edge > 0 ? "+" : ""}${(100 * big.edge).toFixed(0)}%）。` +
        `<span class="dim"> 但回测证明这类高 EV 分歧多为噪声——别当真。</span>`;
      return `<div class="panel sec-block"><div class="p-title">${fx.flagH} ${esc(fx.home)} vs ${esc(fx.away)} ${fx.flagA} <span class="dim" style="font-weight:500">${esc(fx.date)}</span></div>
        <table class="oc-table"><thead><tr><th class="l">选项</th><th>模型概率</th><th>模型公平赔率</th><th>实时赔率</th><th>名义 EV</th></tr></thead><tbody>${body}</tbody></table>
        <div class="card-note">${an}</div></div>`;
    }).join("");
    return `<section class="view" id="view-odds"><div class="vhead"><h1>赔率比较</h1><span class="sub">模型公平赔率 vs the-odds-api 实时赔率（${D.live_odds ? esc(D.live_odds.source) : "—"}）</span></div>
      <p class="value-lead">EV = 模型概率 × 实时赔率 − 1。正 EV 看着像「价值」，但<b>「数据分析」页的下注回测证明：越高 EV 的分歧、ROI 反而越低 = 噪声不是优势</b>。此页供研究对照，不构成投注建议。</p>
      ${cards}</section>`;
  }

  /* ---------- BEST PICKS ---------- */
  function picksHTML() {
    const cards = (D.best_picks || []).map(p => {
      const lbl = { 主胜: p.home, 平局: "平局", 客胜: p.away }[p.pick];
      const edge = p.best_edge;
      const ep = edge == null ? "" : `<span class="pick-edge ${edge > 0.03 ? "edge-pos" : "edge-neg"}">最优盘口 EV ${edge > 0 ? "+" : ""}${(100 * edge).toFixed(0)}%</span>`;
      return `<div class="pick"><div class="conf" style="width:${100 * p.pick_p}%"></div>
        <div class="pick-top"><span class="pick-match">${p.flagH} ${esc(p.home)} <span class="dim">vs</span> ${esc(p.away)} ${p.flagA}</span>
          <span class="pick-call">${esc(p.pick === "平局" ? "平局" : lbl + "胜")} ${pct(p.pick_p, 0)}</span></div>
        <div class="pick-meta"><span>最可能比分 <b>${esc(p.score)}</b> ${pct(p.score_p, 0)}</span><span>预期 <b>${p.lambda_h.toFixed(1)}–${p.lambda_a.toFixed(1)}</b></span>${ep}</div>
        <div class="pick-an">${bold(p.narrative)}</div></div>`;
    }).join("");
    return `<section class="view" id="view-picks"><div class="vhead"><h1>最佳选择</h1><span class="sub">模型最有把握的方向，按概率从高到低排序</span></div>
      <p class="value-lead">⭐ 这里是「<b>最大概率</b>」——模型最确定的方向，<b>不等于最大赔率、更不等于稳赢</b>。高概率 ≠ 高价值（强队低赔，赢了也赚得少）；想看「价值」去「赔率比较」，想看「能否赚钱」去「数据分析」的下注回测。每一条都附模型依据。</p>
      <div class="picks-grid">${cards}</div></section>`;
  }

  /* ---------- GROUPS ---------- */
  function groupsHTML() {
    const order = Object.keys(D.groups).sort();
    const cards = order.map(g => {
      const st = {}; (D.standings[g] || []).forEach(s => st[s.team] = s);
      const rows = D.groups[g].map(t => { const s = st[t.team] || { pld: 0, pts: 0, gf: 0, ga: 0 }; return { ...t, pld: s.pld, pts: s.pts, gd: s.gf - s.ga, padv: t.p_advance || 0 }; }).sort((a, b) => b.padv - a.padv);
      const body = rows.map((r, i) => `<tr class="${i < 2 ? "q" : ""}"><td class="l tm">${r.flag} ${esc(r.team)}</td><td>${r.pld}</td><td>${r.pts}</td><td>${r.gd > 0 ? "+" : ""}${r.gd}</td><td><span class="adv-pill">${pct(r.padv, 0)}</span><div class="gbar"><i style="width:${100 * r.padv}%"></i></div></td></tr>`).join("");
      return `<div class="gcard"><h3><span class="gl">${g}</span> 小组 ${g}</h3><table class="gtable"><thead><tr><th class="l">球队</th><th>赛</th><th>分</th><th>净</th><th>出线</th></tr></thead><tbody>${body}</tbody></table></div>`;
    }).join("");
    return `<section class="view" id="view-groups"><div class="vhead"><h1>小组形势</h1><span class="sub">实时积分 + 出线概率（5 万次模拟，前二高亮）</span></div><div class="group-grid">${cards}</div></section>`;
  }

  /* ---------- ANALYTICS ---------- */
  function analyticsHTML() {
    const bt = D.credibility.backtest, mb = D.credibility.market_beat, bb = D.credibility.betting_backtest, vb = (D.betting && D.betting.value_bets) || [];
    const btTable = bt.length ? `<table class="ctable"><thead><tr><th class="l">届</th><th>场</th><th>RPS模型</th><th>RPS均匀</th><th>LogLoss</th><th>比分命中</th></tr></thead><tbody>${bt.map(r => `<tr class="${r.wc === "all" ? "hl" : ""}"><td class="l">${r.wc}</td><td>${r.n}</td><td>${r.rps_model.toFixed(3)}</td><td>${r.rps_uniform.toFixed(3)}</td><td>${r.logloss_model.toFixed(3)}</td><td>${pct(r.exact_hit_top1, 0)}</td></tr>`).join("")}</tbody></table>` : "";
    const mbRows = mb && mb.tournaments ? mb.tournaments.map(t => `<div class="mb-row"><span>${esc(t.wc)} · ${t.n} 场 <span class="dim">${esc(t.kind || "")}</span></span><span>模型 <b>${t.rps_model.toFixed(3)}</b> · 对手 <b>${t.rps_market.toFixed(3)}</b> <span class="cb-edge ${t.rps_model < t.rps_market ? "edge-pos" : "edge-neg"}">${t.rps_model < t.rps_market ? "模型更优" : "对手更优"}</span></span></div>`).join("") +
      (mb.overall ? `<div class="mb-row"><span class="mb-win">合计 ${mb.overall.n} 场</span><span class="mb-win" style="color:${mb.overall.model_better ? "#5ef2c4" : "#ffa1b4"}">${mb.overall.model_better ? "模型 ≤ 市场" : "市场 < 模型"}（Δ${(mb.overall.margin >= 0 ? "+" : "") + mb.overall.margin.toFixed(4)}）</span></div>` : "") : "<p class='dim'>—</p>";
    const valTable = vb.length ? `<table class="vt"><thead><tr><th class="l">比赛 · 选项</th><th>模型</th><th>赔率</th><th>EV</th></tr></thead><tbody>${vb.slice(0, 8).map(v => `<tr><td class="l">${esc(v.pick)}</td><td>${pct(v.model_p, 0)}</td><td>${v.odds}</td><td class="ev">+${v.ev_pct.toFixed(0)}%</td></tr>`).join("")}</tbody></table>` : "";
    const roiRows = bb && bb.strategies ? `<div class="trend">要求越高把握(EV 阈值↑),ROI <b>反而越低</b> ⇒ 分歧是噪声、不是信号：</div>` + bb.strategies.map(s => `<div class="roi-bar-row"><span class="nm">${esc(s.name)} <span class="dim">(${s.n_bets}注)</span></span><span class="rv ${s.roi >= 0 ? "roi-pos" : "roi-neg"}">${100 * s.roi >= 0 ? "+" : ""}${(100 * s.roi).toFixed(1)}%</span></div>`).join("") : "";
    const meth = `<div class="card method"><h3>方法与数据</h3><ul>
      <li><b>Elo</b>：eloratings.net 公式自算，全史单遍递推，只用赛前评分（无泄漏）。</li>
      <li><b>比分模型</b>：λ = exp(b0 ± b1·ΔElo/400 + 主场)，Dixon-Coles ρ 修正 + 指数时间衰减 MLE。</li>
      <li><b>市值融合</b>：横截面回归 elo ~ log(市值)，权重 0.25。</li>
      <li><b>模拟</b>：小组赛(已赛固定)→ FIFA tiebreakers → 12 组前二 + 8 best thirds → 淘汰赛(加时 1/3、点球 50/50) × ${D.meta.n_sims.toLocaleString()}。</li>
      <li><b>派生盘口</b>：大小球/双方进球/亚盘/正确比分均由比分网格解析得出。</li></ul></div>`;
    return `<section class="view" id="view-analytics"><div class="vhead"><h1>数据分析</h1><span class="sub">回测 · 概率校准 · 市场对标 · 下注回测（诚实版）</span></div>
      <div class="cred-grid">
        <div class="card"><div class="mini-title">历届世界杯回测</div>${btTable}<p class="card-note">RPS 越低越好；模型完胜均匀基线(0.242)。精确比分命中约 11.5%——国家队足球的理论上限附近。</p></div>
        <div class="card"><div class="mini-title">概率校准 <span class="badge-inline" id="ece-badge"></span></div><svg class="cal-svg" id="cal-svg" viewBox="0 0 320 200"></svg><p class="card-note">点越近对角线越校准。0.4–0.7 区间略偏保守，但留一届 CV 证明「锐化」不可泛化。</p></div>
        <div class="card"><div class="mini-title">市场对标（能否跑赢赔率）</div>${mbRows}<p class="card-note">对标真实 Betfair 闭线(2014+2018)。</p></div>
        <div class="card"><div class="mini-title">模型识别的「正 EV」边</div>${valTable}</div>
        <div class="card" style="grid-column:span 2"><div class="mini-title">⚠️ 这些边能赚钱吗？下注回测</div>${roiRows}<div class="verdict"><b>⚠️ 别被正收益骗了。</b> ${bb ? esc(bb.note) : ""}</div></div>
      </div>${meth}</section>`;
  }
  function analyticsPost() {
    const cal = D.credibility.calibration; if (!cal || !cal.length) return;
    $("#ece-badge").textContent = "ECE " + (D.credibility.calibration_ece || 0).toFixed(3);
    const W = 320, H = 200, pad = 28, sx = v => pad + v * (W - 2 * pad), sy = v => H - pad - v * (H - 2 * pad);
    const mxN = Math.max(...cal.map(c => c.n));
    const pts = cal.map(c => `<circle cx="${sx(c.pred_mean)}" cy="${sy(c.obs_freq)}" r="${3 + 7 * c.n / mxN}" fill="rgba(34,211,238,.5)" stroke="#22d3ee"/>`).join("");
    $("#cal-svg").innerHTML = `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" stroke="#566" stroke-dasharray="4 4" opacity=".6"/>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}" stroke="#334"/><line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#334"/>${pts}
      <text x="${W / 2}" y="${H - 4}" fill="#67728f" font-size="10" text-anchor="middle">模型预测概率 →</text>`;
  }

  /* ---------- MIRROR ---------- */
  function mirrorHTML() {
    const m = D.methodology; if (!m) return `<section class="view" id="view-mirror"></section>`;
    const sp = (D.leaderboard.find(t => t.team === "Spain") || {}).p_champion || 0;
    return `<section class="view" id="view-mirror"><div class="vhead"><h1>「经济学家预测世界杯全对」？照妖镜</h1><span class="sub">名人预测的真相与可借鉴之处</span></div>
      <p class="value-lead">${esc(m.key_lesson || "")}</p>
      <div class="mirror-grid">${(m.referents || []).map(r => `<div class="mr"><div class="mr-who">${esc(r.who)} <span class="mr-tag ${r.credible ? "mr-ok" : "mr-no"}">${r.credible ? "可信方法" : "运气/幸存者偏差"}</span></div><div class="mr-truth">${esc((r.truth || "").slice(0, 240))}</div>${r.borrowable ? `<div class="mr-borrow">💡 借鉴：${esc(r.borrowable.slice(0, 150))}</div>` : ""}</div>`).join("")}</div>
      <div class="card crosscheck"><b>独立方法的趋同 ＞ 任何单一「神预测」。</b> 三套独立方法——<span class="cc-pill">🎮 EA Sports</span><span class="cc-pill">🏦 Goldman ≈26%</span><span class="cc-pill">⚙️ 本模型 ${pct(sp, 0)}</span>——都把 <b>西班牙</b> 列为 2026 头号热门。共用配方(Poisson+Elo+蒙特卡洛+市场集成+正确评分+多届回测)正是本项目所搭。而「预测 64 场全对」概率约 3⁻⁶⁴ ≈ 10⁻³⁰——「预测世界杯」从来只是「猜中冠军」。</div></section>`;
  }

  /* ---------- router ---------- */
  const POST = { home: homePost, matches: matchesPost, analytics: analyticsPost };
  function setView(id) {
    if (!NAV.find(n => n[0] === id)) id = "home";
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + id));
    document.querySelectorAll("[data-v]").forEach(a => a.classList.toggle("active", a.dataset.v === id));
    window.scrollTo(0, 0);
  }
  function init() {
    chrome();
    $("#main").innerHTML = [homeHTML(), matchesHTML(), scoreHTML(), oddsHTML(), picksHTML(), groupsHTML(), analyticsHTML(), mirrorHTML()].join("");
    Object.values(POST).forEach(f => { try { f(); } catch (e) { console.error(e); } });
    document.addEventListener("click", e => { const g = e.target.closest("[data-go]"); if (g) { location.hash = g.dataset.go; } });
    window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
    setView(location.hash.slice(1) || "home");
  }
  init();
})();
