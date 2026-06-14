/* World Cup probability dashboard — clean, flat, router over window.WC_DATA */
(function () {
  const D = window.WC_DATA;
  const $ = (s, r = document) => r.querySelector(s);
  if (!D) { document.body.innerHTML = "<p style='padding:40px'>data.js 未加载</p>"; return; }
  const pct = (x, d = 1) => (x == null ? "—" : (100 * x).toFixed(d) + "%");
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const bold = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const fo = p => (1 / Math.max(p, 1e-6)).toFixed(2);
  const sc = s => String(s || "").replace("-", " – ");
  const pickKey = fx => { const p = { home: fx.p_home, draw: fx.p_draw, away: fx.p_away };
    return p.home >= p.draw && p.home >= p.away ? "home" : (p.away >= p.draw ? "away" : "draw"); };
  // single likeliest exact score *consistent with the model's pick* (a
  // favourite's modal win score, not the global modal which is often a low draw)
  const predScore = fx => { const byr = (fx.score_breakdown || {}).by_result || {};
    return ((byr[pickKey(fx)] || (fx.top_scores || [{}])[0]) || {}).score || ""; };
  // UTC kickoff -> the viewer's own local time (so 五湖四海各看各的本地时间)
  const koTime = iso => { if (!iso) return ""; const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }); };
  const TZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { return ""; } })();
  // chronological sort key: real kickoff (UTC ISO) first, untimed matches last in their day
  const koKey = m => m.kickoff || ((m.date || "") + "T99:99");
  const byTime = (a, b) => (a.date || "").localeCompare(b.date || "") || koKey(a).localeCompare(koKey(b)) || ((a.n || 0) - (b.n || 0));
  const INJ = D.injuries || {};
  const PAL = ["#10b981", "#3b82f6", "#a78bfa", "#f472b6", "#fbbf24", "#22d3ee"];

  const NAV = [
    ["home", "🏠", "首页"], ["schedule", "📅", "赛程"], ["bracket", "🗺️", "晋级树"],
    ["matches", "⚽", "比赛预测"], ["score", "🎯", "比分预测"], ["picks", "⭐", "最佳选择"],
    ["bet", "💰", "赔率与买入"], ["groups", "📊", "小组"], ["analytics", "🔬", "数据分析"],
    ["panel", "🤖", "AI论战"],
  ];
  const upcoming = () => D.fixtures.slice().sort(byTime);

  function chrome() {
    $("#topnav").innerHTML = NAV.map(([id, , l]) => `<a href="#${id}" data-v="${id}">${esc(l)}</a>`).join("");
    const sn = $("#sidenav"); if (sn) sn.innerHTML = "";
    $("#asof-chip").textContent = "数据 " + D.meta.asof;
    const lo = D.live_odds;
    if (lo) $("#live-chip").textContent = "实时赔率 " + (lo.asof || ""); else $("#live-chip").style.display = "none";
  }

  /* ---------- match card ---------- */
  function formDots(form) {
    return `<span class="form-dots">${(form || []).slice(-5).map(f => `<span class="fdot f${f.res}" title="${esc(f.date)} ${esc(f.opp)} ${f.gf}-${f.ga}">${f.res}</span>`).join("")}</span>`;
  }
  function refLine(r) {
    if (!r) return "";
    const stats = [r.y != null ? `黄 ${r.y}` : "", r.pen != null ? `点球 ${r.pen}/场` : ""].filter(Boolean).join(" · ");
    return `<div class="ref-line"><span class="ic">🧑‍⚖️</span><span>主裁 <b>${esc(r.referee)}</b>（${esc(r.nat || "")}）${stats ? "· " + stats : ""}${r.style ? "<br><span class='dim'>" + esc(r.style.slice(0, 90)) + "</span>" : ""}</span></div>`;
  }
  const EVICON = { h2h: "🆚", h2h_last: "🕐", form: "📈", goals: "⚽", elo: "🎯", value: "💰", inj: "🩹", climate: "🌡️", market: "💱", squad: "🌟", travel: "✈️" };
  function starSection(fx) {
    const sm = fx.star_matchup || {}, sh = sm.home || [], sa = sm.away || [];
    if (!sh.length && !sa.length) return "";
    const story = fx.storyline ? `<div class="mm-story">${esc(fx.storyline)}</div>` : "";
    const col = arr => arr.length ? arr.map(p => `<div class="star${p.doubtful ? " star-out" : ""}">
        <div class="star-nm">${esc(p.name)}${p.doubtful ? ` <span class="star-flag">伤?</span>` : ""}</div>
        <div class="star-meta">${esc(p.pos)} · ${esc(p.club)} · ≈€${p.val}M</div>
        <div class="star-tag">${esc(p.tag)}</div></div>`).join("") : `<div class="dim" style="font-size:12px">核心球员数据补全中</div>`;
    return `<div class="mm-sec">🌟 球星对位 · 看点</div>${story}
      <div class="star-grid"><div class="star-col">${col(sh)}</div><div class="star-vs">VS</div><div class="star-col away">${col(sa)}</div></div>`;
  }
  function evList(fx) {
    const e = fx.evidence || []; if (!e.length) return "";
    return `<details class="evidence"><summary>判断依据 · ${e.length} 条证据</summary><ul>` +
      e.map(x => `<li><span class="evi">${EVICON[x.k] || "•"}</span>${esc(x.t)}</li>`).join("") + `</ul></details>`;
  }
  function climLine(fx) {
    const c = fx.climate; if (!c || (Math.abs(c.d_home) < 2 && Math.abs(c.d_away) < 2)) return "";
    const tags = [];
    if (c.altitude_m >= 1200) tags.push(`🏔️ ${c.altitude_m}m 高原`);
    if (c.heat_severity >= 0.4) tags.push(`🌡️ ${c.temp_c}°C${c.humid ? "湿热" : "高温"}${c.roof ? "·有顶棚" : ""}`);
    if (!tags.length) tags.push(`📍 ${esc(c.venue)} ${c.altitude_m}m / ${c.temp_c}°C`);
    const worse = c.d_home <= c.d_away ? fx.home : fx.away, adj = Math.min(c.d_home, c.d_away);
    return `<div class="clim-line"><span class="ic">${tags.join(" · ")}</span><span class="dim">${esc(worse)} 适应偏弱 ${adj.toFixed(0)} Elo</span></div>`;
  }
  function matchCard(fx) {
    const ph = fx.p_home, pdr = fx.p_draw, pa = fx.p_away;
    const seg = (w, c, l) => `<span class="${c}" style="width:${100 * w}%">${100 * w >= 13 ? l : ""}</span>`;
    const facs = (fx.factors || []).filter(f => f.label !== "近期状态").map(f =>
      `<div class="fac lean-${f.lean}"><span class="dot"></span><span class="fl">${esc(f.label)}</span><span class="fd">${esc(f.detail)}</span></div>`).join("");
    const sl = (fx.top_scores || []).slice(0, 3).map(s => `<span class="sl">${esc(s.score)}<small>${esc(s.p)}</small></span>`).join("");
    const m = fx.markets;
    const mkts = m ? `<div class="mkts">
      <span class="mkt">大 2.5 <b>${pct(m.over_under["2.5"].over, 0)}</b></span>
      <span class="mkt">双方进球 <b>${pct(m.btts.yes, 0)}</b></span>
      <span class="mkt">预期 <b>${fx.lambda_h.toFixed(1)}–${fx.lambda_a.toFixed(1)}</b></span>
      <span class="mkt">公平赔率 <span class="fo">${fo(ph)}/${fo(pdr)}/${fo(pa)}</span></span></div>` : "";
    const injLine = (t, fl) => { const it = INJ[t]; if (!it || !it.length) return "";
      return `<div class="inj"><span class="ic">🩹</span><span>${fl} ${esc(t)}：${it.slice(0, 3).map(x => esc(x.player) + (x.status && x.status !== "out" ? `(${esc(x.status)})` : "")).join("、")}${it.length > 3 ? " 等" : ""}</span></div>`; };
    const badge = fx.stage === "group" ? "组 " + fx.group : String(fx.stage).toUpperCase();
    return `<div class="mc clickable" data-match-n="${fx.n}">
      <div class="mc-head"><span class="badge">${esc(badge)}</span><span class="mc-date">${fx.kickoff ? "🕒 " + esc(koTime(fx.kickoff)) : esc(fx.date)}</span></div>
      <div class="mc-teams">
        <div class="mc-team home"><span class="fn">${fx.flagH} ${esc(fx.home)}</span><span class="elo">Elo ${fx.elo_h} ${formDots(fx.form_h)}</span></div>
        <div class="mc-pred-score">${sc(predScore(fx))}<small>最可能比分</small></div>
        <div class="mc-team away"><span class="fn">${esc(fx.away)} ${fx.flagA}</span><span class="elo">${formDots(fx.form_a)} Elo ${fx.elo_a}</span></div>
      </div>
      <div class="wdl">${seg(ph, "win", pct(ph, 0))}${seg(pdr, "draw", pct(pdr, 0))}${seg(pa, "loss", pct(pa, 0))}</div>
      <div class="wdl-leg"><span>胜 <b>${pct(ph)}</b></span><span>平 <b>${pct(pdr)}</b></span><span>负 <b>${pct(pa)}</b></span></div>
      <div class="scorelines">${sl}</div>
      <div class="narr">${bold(fx.narrative)}</div>
      <div class="factors">${facs}</div>
      ${evList(fx)}
      ${mkts}${climLine(fx)}${refLine(fx.referee)}${injLine(fx.home, fx.flagH)}${injLine(fx.away, fx.flagA)}</div>`;
  }

  /* ---------- HOME ---------- */
  function homeHTML() {
    const all = D.credibility.backtest.find(x => x.wc === "all") || {};
    const stats = [[D.meta.tournament.teams, "参赛球队"], ["104", "比赛场次"], [(D.meta.n_sims / 1000) + "k", "模拟次数"], [(all.rps_model || 0).toFixed(3), "回测 RPS · 越低越好"]];
    const feats = [["多维数据", "Elo · 状态 · 市值 · 气候/海拔 · 伤停 · 裁判"], ["统计 + ML", "Dixon-Coles 双泊松 + Elo"], ["大量模拟", "5 万次蒙特卡洛 + 多届回测"], ["实时更新", "the-odds-api 赔率对标"]];
    return `<section class="view" id="view-home">
      <div class="hero"><div class="tag">FIFA WORLD CUP 2026 · 美国 加拿大 墨西哥</div><h1>世界杯夺冠概率预测</h1>
        <p>多维数据 + Dixon-Coles 双泊松 + 5 万次蒙特卡洛模拟。基准是<b>对标赔率的概率校准（RPS）</b>，不是「猜中率」。数据更新于 ${D.meta.asof}。</p></div>
      <div class="stats">${stats.map(([v, k]) => `<div class="stat"><div class="sv">${v}</div><div class="sk">${esc(k)}</div></div>`).join("")}</div>
      ${liveStrip()}
      <div class="home-grid">
        <div class="col">
          <div class="panel"><div class="p-title">夺冠概率 TOP 10 <span class="more" data-go="picks">完整排名 →</span></div>
            <div class="champ-flex"><div class="cbars" id="champ-bars"></div><div class="donut-wrap"><div class="donut" id="donut"></div><div class="legend" id="donut-legend"></div></div></div></div>
          <div class="panel"><div class="p-title">实力评分（Elo）走势 · 头部球队近 16 个月</div><svg class="trend-svg" id="trend-svg" viewBox="0 0 720 220"></svg><div class="trend-legend" id="trend-legend"></div></div>
        </div>
        <div class="col">
          <div class="panel"><div class="p-title">夺冠概率排行 <span class="more" data-go="picks">全部 →</span></div><table class="rank-t" id="rank-table"></table></div>
          <div class="panel"><div class="p-title">近期比赛 <span class="more" data-go="schedule">赛程 →</span></div><div id="recent-matches"></div></div>
          <div class="panel"><div class="p-title">模型如何工作</div><div class="feats">${feats.map(([t, d]) => `<div class="feat"><div class="ft">${esc(t)}</div><div class="fd">${esc(d)}</div></div>`).join("")}</div></div>
        </div></div></section>`;
  }
  function homePost() {
    const lb = [...D.leaderboard].sort((a, b) => b.p_champion - a.p_champion);
    const top = lb.slice(0, 10), mx = top[0].p_champion;
    $("#champ-bars").innerHTML = top.map((t, i) => `<div class="cbar"><span class="rk">${i + 1}</span><span class="fl">${t.flag}</span><div><div class="nm">${esc(t.team)}</div><div class="track"><span class="fill" style="width:${100 * t.p_champion / mx}%"></span></div></div><span class="pv">${pct(t.p_champion)}</span></div>`).join("");
    drawDonut($("#donut"), top.slice(0, 8));
    drawTrend();
    $("#rank-table").innerHTML = `<thead><tr><th class="l">排名 / 球队</th><th>夺冠</th><th>vs市场</th></tr></thead><tbody>` + lb.slice(0, 8).map((t, i) => {
      const d = t.diff, tr = d == null ? `<span class="trend-eq">—</span>` : d > 0.003 ? `<span class="trend-up">▲${(100 * d).toFixed(1)}</span>` : d < -0.003 ? `<span class="trend-dn">▼${(100 * -d).toFixed(1)}</span>` : `<span class="trend-eq">—</span>`;
      return `<tr><td class="l tm"><span class="rkn">${i + 1}</span>${t.flag} ${esc(t.team)}</td><td><b>${pct(t.p_champion)}</b></td><td>${tr}</td></tr>`; }).join("") + `</tbody>`;
    $("#recent-matches").innerHTML = upcoming().slice(0, 5).map(fx => {
      const w = fx.p_home >= fx.p_away ? [fx.home, fx.p_home] : [fx.away, fx.p_away];
      return `<div class="rmatch clickable" data-match-n="${fx.n}"><span class="rm-d">${esc(fx.date.slice(5))}</span><span class="rm-t">${fx.flagH} ${esc(fx.home)} <span class="dim">${sc((fx.top_scores[0] || {}).score)}</span> ${esc(fx.away)} ${fx.flagA}</span><span class="rm-r">${esc(w[0])} ${pct(w[1], 0)}</span></div>`; }).join("");
  }
  function drawDonut(el, top) {
    const others = Math.max(0, 1 - top.reduce((s, t) => s + t.p_champion, 0));
    const segs = top.map((t, i) => ({ name: t.team, flag: t.flag, v: t.p_champion, c: i < PAL.length ? PAL[i] : "#3a4150" }));
    if (others > 0.001) segs.push({ name: "其他", v: others, c: "#363b46", flag: "" });
    const R = 92, r = 60, cx = 100, cy = 100; let ang = -Math.PI / 2; const arcs = [];
    segs.forEach(s => { const a2 = ang + s.v * 2 * Math.PI;
      const x1 = cx + R * Math.cos(ang), y1 = cy + R * Math.sin(ang), x2 = cx + R * Math.cos(a2), y2 = cy + R * Math.sin(a2);
      const xi2 = cx + r * Math.cos(a2), yi2 = cy + r * Math.sin(a2), xi1 = cx + r * Math.cos(ang), yi1 = cy + r * Math.sin(ang);
      const lg = (a2 - ang) > Math.PI ? 1 : 0;
      arcs.push(`<path d="M${x1} ${y1} A${R} ${R} 0 ${lg} 1 ${x2} ${y2} L${xi2} ${yi2} A${r} ${r} 0 ${lg} 0 ${xi1} ${yi1} Z" fill="${s.c}"/>`); ang = a2; });
    el.innerHTML = `<svg viewBox="0 0 200 200" width="200" height="200">${arcs.join("")}</svg><div class="ctr"><div class="t">${segs[0].flag} ${esc(segs[0].name)}</div><div class="v">${pct(segs[0].v)}</div><div class="s">夺冠概率</div></div>`;
    $("#donut-legend").innerHTML = segs.map(s => `<span><i style="background:${s.c}"></i>${esc(s.name)}</span>`).join("");
  }
  function drawTrend() {
    const et = D.elo_trend; if (!et || !et.teams.length) return;
    const W = 720, H = 220, pad = { l: 36, r: 10, t: 10, b: 20 };
    let allE = [], maxLen = 0;
    et.teams.forEach(t => (et.series[t] || []).forEach(p => { allE.push(p.elo); }));
    et.teams.forEach(t => maxLen = Math.max(maxLen, (et.series[t] || []).length));
    const lo = Math.min(...allE) - 8, hi = Math.max(...allE) + 8;
    const sx = i => pad.l + (i / Math.max(maxLen - 1, 1)) * (W - pad.l - pad.r), sy = v => H - pad.b - (v - lo) / (hi - lo) * (H - pad.t - pad.b);
    let g = "";
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4, y = sy(v); g += `<line x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}" stroke="#23262e"/><text x="2" y="${y + 3}" fill="#5e6573" font-size="9">${Math.round(v)}</text>`; }
    et.teams.forEach((t, ti) => { const s = et.series[t] || []; if (!s.length) return;
      g += `<polyline points="${s.map((p, i) => `${sx(i)},${sy(p.elo)}`).join(" ")}" fill="none" stroke="${PAL[ti % PAL.length]}" stroke-width="1.8"/><circle cx="${sx(s.length - 1)}" cy="${sy(s[s.length - 1].elo)}" r="2.5" fill="${PAL[ti % PAL.length]}"/>`; });
    $("#trend-svg").innerHTML = g;
    $("#trend-legend").innerHTML = et.teams.map((t, i) => `<span><i style="background:${PAL[i % PAL.length]}"></i>${et.flags[t] || ""} ${esc(t)}</span>`).join("");
  }

  /* ---------- LIVE scoreboard (model vs reality, this tournament) ---------- */
  const OUTCOME_CN = { H: "主胜", D: "平局", A: "客胜" };
  function liveStrip() {
    const s = D.live_scoreboard, rows = D.live || [];
    if (!s || !s.n) return "";
    const cards = rows.map(r => {
      const beat = r.rps < r.rps_uniform;
      return `<div class="lc clickable" data-match-n="${r.n}"><div class="lc-teams">${r.flagH} ${esc(r.home)} <span class="lc-score">${esc(r.actual)}</span> ${esc(r.away)} ${r.flagA}</div>
        <div class="lc-pred">赛前 胜 ${pct(r.p_home, 0)} / 平 ${pct(r.p_draw, 0)} / 负 ${pct(r.p_away, 0)}</div>
        <div class="lc-pred">模型预测比分 <b>${esc(sc(r.pred_score))}</b> · 方向 <span class="${r.fav_hit ? "hit-y" : "hit-n"}">${r.fav_hit ? "✓" : "✗"}</span> · 比分 <span class="${r.score_hit ? "hit-y" : "hit-n"}">${r.score_hit ? "✓ 中" : "✗"}</span></div>
        <div style="margin-top:8px"><span class="lc-rps ${beat ? "rps-good" : "rps-bad"}">RPS ${r.rps.toFixed(3)} ${beat ? "↓优于基线" : "↑差于基线"}</span></div></div>`;
    }).join("");
    const verdict = s.beats_uniform
      ? `模型平均 RPS <b>${s.rps_model}</b> 低于均匀基线 <b>${s.rps_uniform}</b>——目前跑赢基线`
      : `模型平均 RPS <b>${s.rps_model}</b> 高于均匀基线 <b>${s.rps_uniform}</b>——目前落后基线`;
    return `<div class="panel live-panel">
      <div class="p-title">本届进行中 · 模型 vs 实际 <span class="more" data-go="schedule">完整赛程 →</span></div>
      <div class="live-head">
        <div class="lh-stat"><div class="v">${s.n}</div><div class="k">已赛场次</div></div>
        <div class="lh-stat"><div class="v" style="color:var(--acc)">${s.rps_model}</div><div class="k">模型 RPS · 越低越好</div></div>
        <div class="lh-stat"><div class="v">${s.calls_hit}/${s.n}</div><div class="k">方向（胜平负）命中</div></div>
        <div class="lh-stat"><div class="v">${s.scores_hit != null ? s.scores_hit : "—"}/${s.n}</div><div class="k">精确比分命中</div></div>
      </div>
      <div class="live-grid">${cards}</div>
      <div class="note">${verdict}。⚠️ 样本极小（${s.n} 场），只是滚动校验，统计上不能据此下任何结论——这页的意义是<b>诚实地把模型每天放到现实里对账</b>，而非自证。</div>
    </div>`;
  }

  /* ---------- SCHEDULE ---------- */
  function scheduleHTML() {
    const byDate = {};
    (D.schedule_full || []).forEach(m => (byDate[m.date] = byDate[m.date] || []).push(m));
    Object.values(byDate).forEach(arr => arr.sort(byTime));  // chronological within each day
    const days = Object.keys(byDate).sort().map(d => {
      const rows = byDate[d].map(m => {
        const stage = m.stage === "group" ? "组 " + m.group : String(m.stage).toUpperCase();
        let mid, tag;
        if (m.actual) {
          mid = `<span class="s-mid played">${esc(m.actual)}</span>`;
          tag = m.pred ? `<span class="s-result ${m.pred_hit ? "s-hit" : "s-miss"}">${m.pred_hit ? "✓ 预测命中" : "✗ 预测 " + sc(m.pred.score)}</span>` : `<span class="s-result s-up">已赛</span>`;
        } else if (m.pred) {
          mid = `<span class="s-mid pred">${sc(m.pred.score)}</span>`;
          const w = m.pred.pick === "draw" ? "平局" : (m.pred.pick === "home" ? m.home : m.away) + " 胜";
          tag = `<span class="s-result s-up" title="模型预测该结果的概率">预测 ${esc(w)} ${pct(m.pred.pick_p, 0)}</span>`;
        } else { mid = `<span class="s-mid pred s-tbd">待定</span>`; tag = `<span class="s-result s-up">未定队</span>`; }
        const hn = m.ko_slot ? `<span class="s-tbd">${esc(m.home)}</span>` : `${m.flagH} ${esc(m.home)}`;
        const an = m.ko_slot ? `<span class="s-tbd">${esc(m.away)}</span>` : `${esc(m.away)} ${m.flagA}`;
        const predTag = (m.actual && m.pred) ? `赛前 ${pct({ home: m.pred.p_home, draw: m.pred.p_draw, away: m.pred.p_away }[m.pred.pick], 0)}` : "";
        const clk = m.ko_slot ? "" : ` data-match-n="${m.n}"`;
        return `<div class="srow${m.ko_slot ? "" : " clickable"}"${clk}><div class="s-meta">${esc(stage)}${m.kickoff ? `<br><b class="s-ko">🕒 ${esc(koTime(m.kickoff))}</b>` : ""}<br>${esc(m.venue || "")}</div>
          <div class="s-teams"><span class="s-h">${hn}</span>${mid}<span class="s-a">${an}</span></div>
          <div class="s-pred-tag">${predTag}</div><div>${tag}</div></div>`;
      }).join("");
      return `<div class="sched-day"><div class="sched-date">${esc(d)}</div>${rows}</div>`;
    }).join("");
    const koN = (D.schedule_full || []).filter(m => m.kickoff).length;
    return `<section class="view" id="view-schedule"><div class="vhead"><h1>赛程</h1><span class="sub">全部 104 场。已赛显示<b>真实比分</b>与模型赛前预测是否命中；未赛显示<b>预测比分</b>。🕒 开球时间已按<b>你所在时区${TZ ? "（" + esc(TZ) + "）" : ""}</b>换算（已录入 ${koN} 场，其余陆续补全）。</span></div>${days}</section>`;
  }

  /* ---------- BRACKET (projected knockout tree) ---------- */
  const RNAME = { r32: "32 强", r16: "16 强", qf: "8 强", sf: "4 强", final: "决赛", third: "季军赛" };
  function bkTeam(name, fl, p, win, actual) {
    const tbd = !name;
    const right = actual != null ? (win ? "✓" : "") : (p != null ? pct(p, 0) : "");
    return `<div class="bk-team ${win ? "bk-win" : ""} ${tbd ? "bk-tbd" : ""}">
      <span class="bf">${fl || ""}</span><span class="bn">${esc(name || "待定")}</span><span class="bp">${right}</span></div>`;
  }
  function bkMatch(m) {
    const hw = m.p_home_adv != null && m.p_home_adv >= (m.p_away_adv ?? 0);
    const aw = m.p_away_adv != null && !hw;
    const tag = m.actual ? `<div class="bk-sc">${esc(m.actual)}</div>` : "";
    return `<div class="bk-match">${bkTeam(m.home, m.flagH, m.p_home_adv, hw, m.actual)}${bkTeam(m.away, m.flagA, m.p_away_adv, aw, m.actual)}${tag}</div>`;
  }
  function bracketHTML() {
    const b = D.bracket;
    if (!b || !b.rounds || !b.rounds.length) return `<section class="view" id="view-bracket"><div class="vhead"><h1>晋级树</h1></div><p class="dim">暂无淘汰赛投影数据。</p></section>`;
    const cols = b.rounds.filter(r => r.stage !== "third").map(r =>
      `<div class="bk-round"><div class="bk-round-h">${RNAME[r.stage] || r.stage}</div><div class="bk-matches">${r.matches.map(bkMatch).join("")}</div></div>`).join("");
    const champ = b.projected_champion;
    const champBox = champ ? `<div class="bk-round bk-champ-col"><div class="bk-round-h">投影冠军</div><div class="bk-matches"><div class="bk-champ">🏆<div class="bc-fl">${esc((D.leaderboard.find(t => t.team === champ) || {}).flag || "")}</div><div class="bc-nm">${esc(champ)}</div></div></div></div>` : "";
    const third = (b.rounds.find(r => r.stage === "third") || {}).matches || [];
    const thirdBox = third.length ? `<div class="panel sec-block" style="margin-top:18px;max-width:420px"><div class="mini-title">${RNAME.third}</div>${bkMatch(third[0])}</div>` : "";
    return `<section class="view" id="view-bracket"><div class="vhead"><h1>晋级树 · 模型投影路径</h1>
      <span class="sub">每个空位由模型<b>最可能的占位球队</b>填充（小组名次按 P(第1/2名)、最佳第三按 P(以第三名出线)），再让<b>赛前favorite逐轮晋级</b>。淘汰赛胜率含加时(1/3 进球率)+点球 50/50，与模拟一致。</span></div>
      <div class="banner">这是「<b>每场取最可能结果</b>」的投影路径，<b>不等于「最可能的整张签表」</b>，更不是各队夺冠概率（夺冠概率来自 5 万次完整模拟，见首页/最佳选择）。世界杯 64 场全中的概率约 10⁻³⁰——投影是给你一条「最不意外」的脉络，不是预言。</div>
      <div class="bracket">${cols}${champBox}</div>${thirdBox}</section>`;
  }

  /* ---------- MATCHES ---------- */
  function matchesHTML() {
    return `<section class="view" id="view-matches"><div class="vhead"><h1>比赛预测</h1><span class="sub">每场：胜平负 / 最可能比分 / 判断依据（含历史交手）/ 盘口 / 裁判 / 伤停</span></div>
      <div class="banner" style="border-left-color:var(--acc)">💡 <b>为什么比分都偏小？</b> 足球进球服从泊松分布——即便强队，<b>单一最可能的精确比分</b>通常也只是 1–0、2–0、2–1（没有哪个大比分能单独成为最大概率）。强弱要看<b>预期进球</b>（如 2.8–0.4）与<b>胜率</b>，而非那一个小比分；想覆盖更多比分见「赔率与买入」的<b>比分篮子</b>。</div>
      <div class="filters" id="match-filters"></div><div class="match-grid" id="match-grid"></div></section>`;
  }
  function matchesPost() {
    const dates = [...new Set(upcoming().map(f => f.date))].sort();
    let active = "all"; const grid = $("#match-grid"), filt = $("#match-filters");
    filt.innerHTML = `<button class="fbtn active" data-d="all">全部 ${D.fixtures.length} 场</button>` + dates.map(d => `<button class="fbtn" data-d="${d}">${d.slice(5)}</button>`).join("");
    const draw = () => grid.innerHTML = upcoming().filter(f => active === "all" || f.date === active).map(matchCard).join("");
    filt.addEventListener("click", e => { const b = e.target.closest(".fbtn"); if (!b) return; filt.querySelectorAll(".fbtn").forEach(x => x.classList.remove("active")); b.classList.add("active"); active = b.dataset.d; draw(); });
    draw();
  }

  /* ---------- SCORE PREDICTION ---------- */
  function scoreHTML() {
    const cards = upcoming().map(fx => {
      const m = fx.markets; if (!m || !m.grid) return "";
      const grid = m.grid, mxc = Math.max(...grid.flat());
      let heat = `<div class="heat"><div class="axh">客队进球 →</div><div></div>` + grid[0].map((_, j) => `<div class="lbl">${j}</div>`).join("");
      grid.forEach((row, i) => { heat += `<div class="lbl">${i}</div>` + row.map((p, j) => { const a = Math.pow(p / mxc, 0.6);
        return `<div class="hc" style="background:rgba(16,185,129,${(0.05 + 0.9 * a).toFixed(2)})" title="${i}-${j} ${pct(p)}">${p >= 0.03 ? Math.round(p * 100) : ""}</div>`; }).join(""); });
      heat += `</div>`;
      const sb = fx.score_breakdown || {}, br = sb.by_result || {}, top1 = (sb.top || [{}])[0];
      const bars = (sb.top || []).slice(0, 6).map(c => `<div class="cs-bar"><span>${esc(c.score)}</span><div class="track"><span class="fill" style="width:${100 * c.p / (sb.top[0].p)}%"></span></div><span>${pct(c.p)}</span></div>`).join("");
      const ou = m.over_under["2.5"];
      const an = `最可能 <strong>${esc(fx.home)} ${sc(top1.score)} ${esc(fx.away)}</strong>（${pct(top1.p)}）。预期进球 ${fx.lambda_h.toFixed(1)}–${fx.lambda_a.toFixed(1)}，${ou.over >= 0.5 ? "偏大球" : "偏小球"}（大 2.5 ${pct(ou.over, 0)}）。`;
      return `<div class="mc"><div class="mc-head"><span class="badge">${fx.stage === "group" ? "组 " + fx.group : String(fx.stage).toUpperCase()}</span><span class="mc-date">${esc(fx.date)}</span></div>
        <div class="bigscore"><span class="nm">${fx.flagH} ${esc(fx.home)}</span> ${sc(top1.score)} <span class="nm">${esc(fx.away)} ${fx.flagA}</span></div>
        ${heat}<div class="cs-bars">${bars}</div>
        <div class="byres"><div class="br"><div class="k">主胜比分</div><div class="v">${br.home ? sc(br.home.score) : "—"}</div></div><div class="br"><div class="k">平局比分</div><div class="v">${br.draw ? sc(br.draw.score) : "—"}</div></div><div class="br"><div class="k">客胜比分</div><div class="v">${br.away ? sc(br.away.score) : "—"}</div></div></div>
        <div class="narr">${an}</div></div>`;
    }).join("");
    return `<section class="view" id="view-score"><div class="vhead"><h1>比分预测</h1><span class="sub">每场给出最可能的具体比分（如 0–1），下方热力图是完整比分概率分布</span></div><div class="score-grid">${cards}</div></section>`;
  }

  /* ---------- PICKS ---------- */
  function picksHTML() {
    const cards = (D.best_picks || []).map(p => {
      const lbl = { 主胜: p.home + " 胜", 平局: "平局", 客胜: p.away + " 胜" }[p.pick];
      const edge = p.best_edge, ep = edge == null ? "" : `<span class="pick-edge ${edge > 0.03 ? "edge-pos" : "edge-neg"}">最优盘口 EV ${edge > 0 ? "+" : ""}${(100 * edge).toFixed(0)}%</span>`;
      return `<div class="pick clickable"${p.n != null ? ` data-match-n="${p.n}"` : ""}><div class="conf" style="width:${100 * p.pick_p}%"></div>
        <div class="pick-top"><span class="pick-match">${p.flagH} ${esc(p.home)} <span class="dim">vs</span> ${esc(p.away)} ${p.flagA}</span><span class="pick-call">${esc(lbl)} ${pct(p.pick_p, 0)}</span></div>
        <div class="pick-meta"><span>预测比分 <b>${sc(p.score)}</b></span><span>预期 <b>${p.lambda_h.toFixed(1)}–${p.lambda_a.toFixed(1)}</b></span>${ep}</div>
        <div class="pick-an">${bold(p.narrative)}</div></div>`;
    }).join("");
    return `<section class="view" id="view-picks"><div class="vhead"><h1>最佳选择</h1><span class="sub">模型最有把握的方向，按概率从高到低</span></div>
      <div class="banner">⭐ 这是「<b>最大概率</b>」——模型最确定的方向，<b>不等于最大赔率、更不等于稳赢</b>。强队低赔，赢了也赚得少；想看「价值/买入」去「赔率与买入」，想看「能否赚钱」去「数据分析」的下注回测。</div>
      <div class="picks-grid">${cards}</div></section>`;
  }

  /* ---------- BET (odds compare + recommendations + combo) ---------- */
  function betSmartCard(fx) {
    const s = fx.smart_bets; if (!s) return "";
    const evtag = e => e == null ? "" : `<span class="${e >= 0 ? "edge-pos" : "edge-neg"}">EV ${e >= 0 ? "+" : ""}${(100 * e).toFixed(0)}%</span>`;
    const src = b => b ? `<span class="src live">实时</span>` : `<span class="src">模型公允</span>`;
    const add = (id, label, p, odds) => `<button class="add-leg" data-id="${esc(id)}" data-match="${esc(fx.home)}|${esc(fx.away)}" data-label="${esc(label)}" data-p="${p}" data-odds="${odds}">＋ 串</button>`;
    const mm = `${esc(fx.home)} vs ${esc(fx.away)}`;
    const rows = [];
    if (s.safest) { const x = s.safest;
      rows.push(`<div class="sb-play"><span class="sbk safe">最稳</span><span class="sbsel"><b>${esc(x.sel)}</b> <span class="dim">${esc(x.market)}</span></span><span class="sbp">命中 <b>${pct(x.p, 0)}</b></span><span class="sbo">赔 ${x.odds} ${evtag(x.ev)} ${src(x.book)}</span>${add("sb-s-" + fx.home + fx.away, mm + " · " + x.sel, x.p, x.odds)}</div>`); }
    if (s.value) { const x = s.value;
      rows.push(`<div class="sb-play"><span class="sbk val">最值</span><span class="sbsel"><b>${esc(x.sel)}</b> <span class="dim">${esc(x.market)}</span></span><span class="sbp">命中 ${pct(x.p, 0)}</span><span class="sbo">赔 ${x.odds} ${evtag(x.ev)}</span>${add("sb-v-" + fx.home + fx.away, mm + " · " + x.sel, x.p, x.odds)}</div>`); }
    else rows.push(`<div class="sb-play"><span class="sbk val">最值</span><span class="dim" style="flex:1">暂无书面盘口的正 EV 选项（仅 1X2 / 大小2.5 有实时赔率）</span></div>`);
    if (s.basket) { const b = s.basket;
      rows.push(`<div class="sb-play"><span class="sbk bask">比分篮子</span><span class="sbsel">${b.scores.map(x => `<i class="cs-chip">${esc(sc(x))}</i>`).join("")}</span><span class="sbp">命中 ~<b>${pct(b.hit, 0)}</b></span><span class="sbo">公允赔率 ${b.fair} · EV≈0%</span></div>`); }
    if (s.combo) { const c = s.combo;
      rows.push(`<div class="sb-play"><span class="sbk combo">组合</span><span class="sbsel"><b>${c.legs.map(esc).join(" + ")}</b></span><span class="sbp">命中 <b>${pct(c.p, 0)}</b></span><span class="sbo">赔 ${c.odds} ${evtag(c.ev)} ${src(c.book)}</span>${add("sb-c-" + fx.home + fx.away, mm + " · " + c.legs.join("+"), c.p, c.odds)}</div>`); }
    return `<div class="sb-card"><div class="sb-head">${fx.flagH} ${esc(fx.home)} <span class="dim">vs</span> ${esc(fx.away)} ${fx.flagA} <span class="dim">${esc(fx.date.slice(5))}</span></div>${rows.join("")}</div>`;
  }
  function betHTML() {
    const recs = (D.betting && D.betting.recommendations) || [];
    const recRows = recs.map(v => `<tr class="rec-row"><td class="l">${esc(v.pick)}</td><td>${pct(v.model_p, 0)}</td><td>${v.odds}</td><td class="edge-pos">+${v.ev_pct.toFixed(0)}%</td><td class="stk">${v.stake}</td><td>${v.exp_return >= 0 ? "+" : ""}${v.exp_return}</td>
      <td><button class="add-leg" data-id="rec-${esc(v.home)}-${esc(v.side)}" data-match="${esc(v.home)}|${esc(v.away)}" data-label="${esc(v.pick)}" data-p="${v.model_p}" data-odds="${v.odds}">＋</button></td></tr>`).join("");
    const smartCards = upcoming().filter(f => f.smart_bets).map(betSmartCard).join("");
    return `<section class="view" id="view-bet"><div class="vhead"><h1>赔率与买入</h1><span class="sub">每场的最优玩法（模型 + 实时赔率）· 串关计算器</span></div>
      <div class="banner"><b>⚠️ 诚实声明：</b>EV / 预期收益是<b>模型视角</b>的名义值。历史下注回测证明模型<b>跑不赢闭线</b>(见「数据分析」),所谓「价值」多为噪声;<b>串关只会把每注抽水相乘——是「方差最大化」不是「收益最大化」</b>。此页供研究,非投注建议。</div>
      <div class="panel sec-block"><div class="mini-title">每场最优玩法</div>
        <div class="note" style="margin-bottom:13px;line-height:1.7">
          <b>四种玩法：</b>「最稳」= 命中率最高的单选；「最值」= <b>预期收益(EV)最高</b>的单选（仅 1X2 与大小2.5 有实时赔率，故只有这两类能算出真实 EV）；「比分篮子」= 覆盖 ≥50% 概率的几个比分一起买；「组合」= 同场两个条件须<b>同时成立</b>，联合命中率由比分网格<b>精确计算</b>（非独立相乘，已计入相关性）。<br>
          <b>盘口含义：</b>「大 2.5」= 全场总进球 ≥3；「小 2.5」= 总进球 ≤2；「双重机会·平或客胜」= 客队不输（平/客胜都算赢）；「亚盘 主 -1.5」= 主队需净胜 2 球+。<br>
          <b>预期收益 EV = 模型概率 × 赔率 − 1：</b>正数 = 模型认为划算、负数 = 吃亏；标「模型公允」者无实时盘口、按公允赔率定价，故 EV≈0（无套利空间，仅供参考命中率）。
        </div>
        <div class="sb-grid">${smartCards || "<p class='dim'>暂无可下注的近期比赛</p>"}</div></div>
      <div class="bet-grid">
        <div class="panel sec-block"><div class="mini-title">模型正 EV 买入建议（¼ Kelly，本金 1000）</div>
          <table class="vt"><thead><tr><th class="l">比赛 · 选项</th><th>模型</th><th>赔率</th><th>EV</th><th>注额</th><th>预期</th><th></th></tr></thead><tbody>${recRows || "<tr><td class='l dim'>暂无</td></tr>"}</tbody></table></div>
        <div class="panel slip"><div class="mini-title">🧾 串关计算器</div>
          <div id="slip-legs"><p class="dim" style="font-size:12px">从上面点「＋ 串」添加投注项，看组合赔率、模型胜率与 EV 如何变化。</p></div>
          <div class="combo-input">本金 <input id="combo-stake" type="number" value="10" min="1"> 元</div>
          <div class="slip-foot" id="slip-stats"></div>
        </div>
      </div></section>`;
  }
  function betPost() {
    const legs = [];
    const stakeEl = () => Math.max(1, parseFloat(($("#combo-stake") || {}).value || "10") || 10);
    function recompute() {
      const lg = $("#slip-legs"), st = $("#slip-stats");
      if (!legs.length) { lg.innerHTML = `<p class="dim" style="font-size:12px">点 ＋ 添加投注项，看组合赔率、模型胜率与 EV 如何变化。</p>`; st.innerHTML = ""; document.querySelectorAll(".add-leg.in").forEach(b => b.classList.remove("in")); return; }
      lg.innerHTML = legs.map((l, i) => `<div class="slip-leg"><span>${esc(l.label)} <span class="dim">@${l.odds}</span></span><span class="x" data-i="${i}">✕</span></div>`).join("");
      const oddsProd = legs.reduce((a, l) => a * l.odds, 1), probProd = legs.reduce((a, l) => a * l.model_p, 1);
      const stake = stakeEl(), payout = stake * oddsProd, ev = probProd * oddsProd - 1;
      st.innerHTML = `<div class="slip-stat"><span>腿数</span><span class="v">${legs.length}</span></div>
        <div class="slip-stat"><span>组合赔率</span><span class="v">${oddsProd.toFixed(2)}</span></div>
        <div class="slip-stat"><span>模型胜率（全中）</span><span class="v" style="color:${probProd > 0.2 ? "var(--acc)" : probProd > 0.05 ? "var(--warn)" : "var(--neg)"}">${pct(probProd, 1)}</span></div>
        <div class="slip-stat"><span>潜在回报</span><span class="v">${payout.toFixed(1)} 元</span></div>
        <div class="slip-stat"><span>模型 EV</span><span class="v ${ev >= 0 ? "edge-pos" : "edge-neg"}">${ev >= 0 ? "+" : ""}${(100 * ev).toFixed(0)}%</span></div>
        <div class="note" style="margin-top:8px">${legs.length >= 2 ? `每多 1 腿,胜率乘下去越来越小、抽水越叠越厚——这正是串关「看着回报高、实则 EV 更差」的原因。` : `单注：胜率最高，但回报有限。`}</div>`;
      document.querySelectorAll(".add-leg").forEach(b => b.classList.toggle("in", legs.some(l => l.id === b.dataset.id)));
    }
    const v = $("#view-bet");
    v.addEventListener("click", e => {
      const add = e.target.closest(".add-leg");
      if (add) { const id = add.dataset.id, ix = legs.findIndex(l => l.id === id);
        if (ix >= 0) { legs.splice(ix, 1); }
        else { const mt = add.dataset.match;
          const mi = legs.findIndex(l => l.match === mt); if (mi >= 0) legs.splice(mi, 1);  // one leg per match
          legs.push({ id, match: mt, label: add.dataset.label, model_p: +add.dataset.p, odds: +add.dataset.odds }); }
        recompute(); return; }
      const x = e.target.closest(".x"); if (x) { legs.splice(+x.dataset.i, 1); recompute(); }
    });
    v.addEventListener("input", e => { if (e.target.id === "combo-stake") recompute(); });
  }

  /* ---------- GROUPS ---------- */
  function groupsHTML() {
    const cards = Object.keys(D.groups).sort().map(g => {
      const st = {}; (D.standings[g] || []).forEach(s => st[s.team] = s);
      const rows = D.groups[g].map(t => { const s = st[t.team] || { pld: 0, pts: 0, gf: 0, ga: 0 }; return { ...t, pld: s.pld, pts: s.pts, gd: s.gf - s.ga, padv: t.p_advance || 0 }; }).sort((a, b) => b.padv - a.padv);
      const body = rows.map((r, i) => `<tr class="${i < 2 ? "q" : ""}"><td class="l tm">${r.flag} ${esc(r.team)}</td><td>${r.pld}</td><td>${r.pts}</td><td>${r.gd > 0 ? "+" : ""}${r.gd}</td><td><span class="adv-pill">${pct(r.padv, 0)}</span><div class="gbar"><i style="width:${100 * r.padv}%"></i></div></td></tr>`).join("");
      return `<div class="gcard"><h3><span class="gl">${g}</span> 小组 ${g}</h3><table class="gtable"><thead><tr><th class="l">球队</th><th>赛</th><th>分</th><th>净</th><th>出线</th></tr></thead><tbody>${body}</tbody></table></div>`;
    }).join("");
    return `<section class="view" id="view-groups"><div class="vhead"><h1>小组形势</h1><span class="sub">实时积分 + 出线概率（5 万次模拟，前二高亮）</span></div><div class="group-grid">${cards}</div></section>`;
  }

  /* ---------- ANALYTICS ---------- */
  function analyticsHTML() {
    const bt = D.credibility.backtest, mb = D.credibility.market_beat, bb = D.credibility.betting_backtest;
    const btTable = bt.length ? `<table class="ctable"><thead><tr><th class="l">届</th><th>场</th><th>RPS模型</th><th>RPS均匀</th><th>比分命中</th></tr></thead><tbody>${bt.map(r => `<tr class="${r.wc === "all" ? "hl" : ""}"><td class="l">${r.wc}</td><td>${r.n}</td><td>${r.rps_model.toFixed(3)}</td><td>${r.rps_uniform.toFixed(3)}</td><td>${pct(r.exact_hit_top1, 0)}</td></tr>`).join("")}</tbody></table>` : "";
    const mbRows = mb && mb.tournaments ? mb.tournaments.map(t => `<div class="mb-row"><span>${esc(t.wc)} · ${t.n} 场 <span class="dim">${esc(t.kind || "")}</span></span><span>模型 <b>${t.rps_model.toFixed(3)}</b> · 对手 <b>${t.rps_market.toFixed(3)}</b> <span class="cb-edge ${t.rps_model < t.rps_market ? "edge-pos" : "edge-neg"}">${t.rps_model < t.rps_market ? "模型更优" : "对手更优"}</span></span></div>`).join("") + (mb.overall ? `<div class="mb-row"><span class="mb-win">合计 ${mb.overall.n} 场</span><span class="mb-win" style="color:${mb.overall.model_better ? "var(--acc)" : "var(--neg)"}">${mb.overall.model_better ? "模型 ≤ 市场" : "市场 < 模型"}（Δ${(mb.overall.margin >= 0 ? "+" : "") + mb.overall.margin.toFixed(4)}）</span></div>` : "") : "—";
    const roiRows = bb && bb.strategies ? `<div class="trend">要求越高把握(EV 阈值↑),ROI <b>反而越低</b> ⇒ 分歧是噪声、不是优势：</div>` + bb.strategies.map(s => `<div class="roi-bar-row"><span class="nm">${esc(s.name)} <span class="dim">(${s.n_bets}注)</span></span><span class="rv ${s.roi >= 0 ? "roi-pos" : "roi-neg"}">${100 * s.roi >= 0 ? "+" : ""}${(100 * s.roi).toFixed(1)}%</span></div>`).join("") : "";
    const meth = `<div class="card method"><h3>方法与数据</h3><ul>
      <li><b>Elo</b>：eloratings.net 公式自算，全史单遍递推，只用赛前评分（无泄漏，随每轮结果动态更新）。</li>
      <li><b>比分模型</b>：λ = exp(b0 ± b1·ΔElo/400 + 主场)，Dixon-Coles ρ 修正 + 指数时间衰减 MLE。</li>
      <li><b>多维</b>：Elo + 阵容市值融合 + 伤停/裁判定性层。</li>
      <li><b>2026 气候/海拔</b>：按场馆海拔（墨西哥城 2240m、瓜达拉哈拉 1566m）与高温湿热，对不适应的客队做<b>小幅 Elo 修正</b>（海拔参考 McSharry 2007；有顶棚/空调球场打折）。<b>仅作用于 2026 赛程，不触碰历史训练与回测/校准</b>——属透明先验，非拟合参数。</li>
      <li><b>模拟</b>：FIFA tiebreakers + 8 best thirds + 淘汰赛 × ${D.meta.n_sims.toLocaleString()}。</li>
      <li><b>派生盘口</b>：大小球/双方进球/亚盘/正确比分均由比分网格解析。</li></ul></div>`;
    return `<section class="view" id="view-analytics"><div class="vhead"><h1>数据分析</h1><span class="sub">回测 · 概率校准 · 市场对标 · 下注回测（诚实版）</span></div>
      <div class="cred-grid">
        <div class="card"><div class="mini-title">历届世界杯回测</div>${btTable}<p class="card-note">RPS 越低越好；模型完胜均匀基线(0.242)。精确比分命中约 11.5%——国家队足球理论上限附近。</p></div>
        <div class="card"><div class="mini-title">概率校准 <span class="badge-inline" id="ece-badge"></span></div><svg class="cal-svg" id="cal-svg" viewBox="0 0 320 200"></svg><p class="card-note">点越近对角线越校准。0.4–0.7 区间略偏保守，但留一届 CV 证明「锐化」不可泛化。</p></div>
        <div class="card"><div class="mini-title">市场对标（能否跑赢赔率）</div>${mbRows}<p class="card-note">对标真实 Betfair 闭线(2014+2018)。</p></div>
        <div class="card" style="grid-column:span 2"><div class="mini-title">⚠️ 下注回测：这些「价值」能赚钱吗？</div>${roiRows}<div class="verdict"><b>别被正收益骗了。</b> ${bb ? esc(bb.note) : ""}</div></div>
      </div>${meth}</section>`;
  }
  function analyticsPost() {
    const cal = D.credibility.calibration; if (!cal || !cal.length) return;
    $("#ece-badge").textContent = "ECE " + (D.credibility.calibration_ece || 0).toFixed(3);
    const W = 320, H = 200, pad = 28, sx = v => pad + v * (W - 2 * pad), sy = v => H - pad - v * (H - 2 * pad);
    const mxN = Math.max(...cal.map(c => c.n));
    const pts = cal.map(c => `<circle cx="${sx(c.pred_mean)}" cy="${sy(c.obs_freq)}" r="${3 + 6 * c.n / mxN}" fill="rgba(16,185,129,.45)" stroke="#10b981"/>`).join("");
    $("#cal-svg").innerHTML = `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" stroke="#3a4150" stroke-dasharray="4 4"/><line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}" stroke="#2a2e37"/><line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#2a2e37"/>${pts}<text x="${W / 2}" y="${H - 4}" fill="#5e6573" font-size="10" text-anchor="middle">模型预测概率 →</text>`;
  }

  /* ---------- AI 论战 (multi-agent analyst panel) ---------- */
  function panelHTML() {
    const ap = D.ai_panel;
    if (!ap || !ap.panel) return `<section class="view" id="view-panel"><div class="vhead"><h1>🤖 AI 论战</h1></div><p class="dim">暂无 AI 面板数据。</p></section>`;
    const flagOf = {}; (D.leaderboard || []).forEach(t => flagOf[t.team] = t.flag);
    const fl = t => flagOf[t] || "";
    const con = ap.consensus || {};
    const myTop = [...(D.leaderboard || [])].sort((a, b) => b.p_champion - a.p_champion)[0] || {};
    const votes = {}; ap.panel.forEach(p => { const c = p.forecast && p.forecast.champion; if (c) votes[c] = (votes[c] || 0) + 1; });
    const voteStr = Object.entries(votes).sort((a, b) => b[1] - a[1]).map(([t, n]) => `${esc(t)} ${n}`).join(" / ");
    const cards = ap.panel.map(p => {
      const f = p.forecast || {}, d = p.debate || {};
      const top4 = (f.top4 || []).map(t => `<span class="pp-team">${fl(t)} ${esc(t)}</span>`).join("");
      return `<div class="persona">
        <div class="pp-name">${esc(p.name)}</div>
        <div class="pp-pick"><span class="pp-champ">🏆 ${fl(f.champion)} <b>${esc(f.champion)}</b></span></div>
        <div class="pp-sub">亚军 ${fl(f.runner_up)} ${esc(f.runner_up)} · 黑马 ${fl(f.dark_horse)} ${esc(f.dark_horse)}</div>
        <div class="pp-top4">四强 ${top4}</div>
        <div class="pp-rat">${esc(f.rationale)}</div>
        <div class="pp-deb">💬 ${esc(d.defense)}<div class="pp-reb">↩ 怼「${esc(d.target)}」：${esc(d.rebuttal)}</div></div>
      </div>`;
    }).join("");
    const converge = con.champion === myTop.team;
    return `<section class="view" id="view-panel"><div class="vhead"><h1>🤖 AI 论战 · 大模型预测</h1>
      <span class="sub">5 个 AI 分析师 persona（数据/状态/球星/市场/黑马）独立预测 → 互相辩论 → 主持人综合。多智能体 workflow 生成，<b>不调用外部 LLM API</b>。这就是「问大模型预测世界杯」的本质——看它们的共识与分歧。</span></div>
      <div class="banner">${esc(ap.note || "")}${ap.asof ? " · 生成于 " + esc(ap.asof) : ""}</div>
      <div class="panel sec-block"><div class="p-title">AI 面板共识 vs 本统计模型</div>
        <div class="vs-grid">
          <div class="vs-box"><div class="vs-champ">${fl(con.champion)} ${esc(con.champion)}</div><div class="vs-k">🤖 AI 面板共识（${esc(voteStr)}）</div></div>
          <div class="vs-mid">VS</div>
          <div class="vs-box"><div class="vs-champ">${myTop.flag || ""} ${esc(myTop.team)}</div><div class="vs-k">⚙️ 本模型冠军（${pct(myTop.p_champion)}）</div></div>
        </div>
        <div class="card-note">${converge ? "两条<b>相互独立</b>的路线指向同一冠军——<b>独立方法的趋同，比任何单一「神预测」更有信息量</b>。" : "AI 面板与统计模型给出不同冠军，是值得玩味的分歧点。"} 但要警惕：「问大模型」往往只是<b>复述训练数据里的共识</b>（所以它们大多说西班牙/法国）；真正的检验靠回测/校准，见「数据分析」。</div></div>
      <div class="panel sec-block"><div class="p-title">主持人综合</div>
        <div class="cons-line"><b>一致度：</b>${esc(con.agreement)}</div>
        <div class="cons-line"><b>最大分歧：</b>${esc(con.biggest_disagreement)}</div>
        <div class="cons-line"><b>综合四强：</b>${(con.top4 || []).map(t => fl(t) + " " + esc(t)).join(" · ")}</div>
        <div class="card-note">${esc(con.summary)}</div></div>
      <div class="persona-grid">${cards}</div></section>`;
  }

  /* ---------- match detail modal (click any match) ---------- */
  const fixturesByN = {}; (D.fixtures || []).forEach(f => { fixturesByN[f.n] = f; });
  const schedByN = {}; (D.schedule_full || []).forEach(m => { schedByN[m.n] = m; });
  const detailOf = n => fixturesByN[n] || (D.match_details || {})[n];
  function openMatch(n) {
    const fx = detailOf(n); if (!fx) return;
    const sm = schedByN[n];
    const actual = sm && sm.actual
      ? `<div class="mm-actual">本场已结束 · 实际比分 <b>${esc(sm.actual)}</b>${sm.pred_hit != null ? ` · 模型方向 <span class="${sm.pred_hit ? "hit-y" : "hit-n"}">${sm.pred_hit ? "✓ 命中" : "✗ 未中"}</span>` : ""}</div>`
      : (fx.kickoff ? `<div class="mm-actual dim">开球 🕒 ${esc(koTime(fx.kickoff))}（你所在时区）</div>` : "");
    $("#mm-body").innerHTML = actual + matchCard(fx) + starSection(fx)
      + `<div class="mm-sec">💰 赔率与买入 · 本场最优玩法</div><div class="sb-grid">${betSmartCard(fx)}</div>`;
    const mod = $("#match-modal"); mod.classList.add("open"); $("#mm-body").scrollTop = 0;
    document.body.style.overflow = "hidden";
  }
  function closeMatch() { $("#match-modal").classList.remove("open"); document.body.style.overflow = ""; }

  /* ---------- confetti (champion celebration) ---------- */
  function confetti(el) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const colors = ["#1fc398", "#f6a93c", "#3b82f6", "#f472b6", "#fbbf24", "#22d3ee", "#fff"];
    const r = el ? el.getBoundingClientRect() : { left: innerWidth / 2, top: 140, width: 0, height: 0 };
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const wrap = document.createElement("div"); wrap.className = "confetti-layer";
    for (let i = 0; i < 90; i++) {
      const p = document.createElement("i");
      const a = Math.random() * Math.PI * 2, v = 100 + Math.random() * 240;
      p.style.cssText = `left:${cx}px;top:${cy}px;background:${colors[i % colors.length]};`
        + `--dx:${Math.cos(a) * v}px;--dy:${Math.sin(a) * v - 140}px;--rot:${Math.random() * 720 - 360}deg;`
        + `animation-delay:${Math.random() * 80}ms`;
      wrap.appendChild(p);
    }
    document.body.appendChild(wrap);
    setTimeout(() => wrap.remove(), 1700);
  }
  let _confettiDone = false;

  /* ---------- router ---------- */
  const POST = { home: homePost, matches: matchesPost, bet: betPost, analytics: analyticsPost };
  function setView(id) {
    if (!NAV.find(n => n[0] === id)) id = "home";
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + id));
    document.querySelectorAll("[data-v]").forEach(a => a.classList.toggle("active", a.dataset.v === id));
    window.scrollTo(0, 0);
    if (id === "bracket" && !_confettiDone) {
      _confettiDone = true;
      setTimeout(() => confetti(document.querySelector("#view-bracket .bk-champ")), 250);
    }
  }
  function init() {
    chrome();
    $("#main").innerHTML = [homeHTML(), scheduleHTML(), bracketHTML(), matchesHTML(), scoreHTML(), picksHTML(), betHTML(), groupsHTML(), analyticsHTML(), panelHTML()].join("");
    document.body.insertAdjacentHTML("beforeend",
      `<div id="match-modal" class="mmodal"><div class="mm-back"></div><div class="mm-card"><button class="mm-x" aria-label="关闭">✕</button><div id="mm-body"></div></div></div>`);
    Object.values(POST).forEach(f => { try { f(); } catch (e) { console.error(e); } });
    document.addEventListener("click", e => {
      const g = e.target.closest("[data-go]"); if (g) { location.hash = g.dataset.go; return; }
      if (e.target.closest(".mm-x, .mm-back")) { closeMatch(); return; }
      const champ = e.target.closest(".bk-champ"); if (champ) { confetti(champ); return; }
      const mn = e.target.closest("[data-match-n]");
      if (mn && !e.target.closest("button, a, summary, .add-leg, .more")) openMatch(+mn.dataset.matchN);
    });
    window.addEventListener("keydown", e => { if (e.key === "Escape") closeMatch(); });
    window.addEventListener("hashchange", () => { closeMatch(); setView(location.hash.slice(1)); });
    setView(location.hash.slice(1) || "home");
  }
  init();
})();
