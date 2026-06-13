/* 2026 World Cup prediction dashboard — renders window.WC_DATA */
(function () {
  const D = window.WC_DATA;
  if (!D) { document.body.innerHTML = "<p style='padding:40px'>data.js 未加载</p>"; return; }
  const $ = (s, r = document) => r.querySelector(s);
  const pct = (x, d = 1) => (x == null ? "—" : (100 * x).toFixed(d) + "%");
  const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const bold = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const elx = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };

  /* ---------- hero ---------- */
  function hero() {
    const m = D.meta, lead = D.leaderboard.find(x => x.p_champion === Math.max(...D.leaderboard.map(t => t.p_champion)));
    $("#hero-sub").innerHTML =
      `Elo 评分 + Dixon-Coles 双泊松比分模型 + 全赛程 ${m.n_sims.toLocaleString()} 次 Monte Carlo 模拟。` +
      `数据截至 <b>${m.asof}</b>，${m.tournament.dates}，主办 ${m.tournament.hosts}。`;
    const all = D.credibility.backtest.find(x => x.wc === "all") || {};
    const stats = [
      ["夺冠领跑", `${lead.flag} ${pct(lead.p_champion, 0)}`, lead.team],
      ["回测 RPS", all.rps_model ? all.rps_model.toFixed(3) : "—", `均匀基线 ${all.rps_uniform ? all.rps_uniform.toFixed(3) : "—"}`],
      ["校准 ECE", D.credibility.calibration_ece ? D.credibility.calibration_ece.toFixed(3) : "—", "越低越准"],
      ["模拟次数", (m.n_sims / 1000) + "k", `${m.tournament.teams} 队 · 104 场`],
    ];
    $("#hero-stats").innerHTML = stats.map(([k, v, sub]) =>
      `<div class="stat"><div class="v">${v} <small>${sub ? "· " + esc(sub) : ""}</small></div><div class="k">${k}</div></div>`).join("");
    $("#foot-asof").textContent = `生成于 ${m.asof} · 模型参数 b0=${m.fit.b0} b1(Elo)=${m.fit.b1} 主场=${m.fit.home} ρ=${m.fit.rho}（${m.fit.n} 场拟合）`;
  }

  /* ---------- championship ---------- */
  function champ() {
    const lb = [...D.leaderboard].sort((a, b) => b.p_champion - a.p_champion);
    const top = lb.slice(0, 16);
    const maxv = top[0].p_champion;
    const hasMkt = top.some(t => t.p_market != null);
    $("#champ-lead").innerHTML = hasMkt
      ? `把 5 万次模拟出的夺冠概率，与 BetMGM 赔率去 margin 后的市场隐含概率并排。<b>蓝紫渐变=模型，灰=市场</b>。右侧标出二者差值（pp）。`
      : `各队夺冠概率（5 万次模拟）。`;
    $("#champ-board").innerHTML = top.map((t, i) => {
      const mw = 100 * t.p_champion / maxv, kw = t.p_market != null ? 100 * t.p_market / maxv : 0;
      const edge = t.diff == null ? "" :
        `<span class="cb-edge ${t.diff > 0.005 ? "edge-pos" : t.diff < -0.005 ? "edge-neg" : "edge-zero"}">${t.diff > 0 ? "+" : ""}${(100 * t.diff).toFixed(1)}pp</span>`;
      return `<div class="cb-row ${i === 0 ? "top1" : ""}">
        <div class="cb-rank">${i + 1}</div><div class="cb-flag">${t.flag}</div>
        <div class="cb-main">
          <div class="cb-name">${esc(t.team)}</div>
          <div class="cb-bars">
            <div class="cmp model"><span class="lbl">模型</span><span class="track"><span class="fill" style="width:${mw}%"></span></span><span class="num">${pct(t.p_champion)}</span></div>
            ${t.p_market != null ? `<div class="cmp market"><span class="lbl">市场</span><span class="track"><span class="fill" style="width:${kw}%"></span></span><span class="num">${pct(t.p_market)}</span></div>` : ""}
          </div>
          ${edge}
        </div></div>`;
    }).join("");

    const dv = D.leaderboard.filter(t => t.diff != null).sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff)).slice(0, 6);
    $("#diverge").innerHTML = dv.map(t => {
      const pos = t.diff > 0;
      return `<div class="dv-card">
        <div class="dv-team">${t.flag} ${esc(t.team)}</div>
        <div class="dv-delta" style="color:${pos ? "#5ef2c4" : "#ffa1b4"}">${pos ? "+" : ""}${(100 * t.diff).toFixed(1)}<span style="font-size:13px;color:var(--mut)">pp</span></div>
        <div class="dv-detail">模型 ${pct(t.p_champion)} · 市场 ${pct(t.p_market)}<br>模型比市场更${pos ? "看好" : "看淡"}</div>
      </div>`;
    }).join("");
  }

  /* ---------- matches ---------- */
  function formDots(form) {
    return `<span class="form-dots">${form.slice(-5).map(f => `<span class="fdot f${f.res}" title="${esc(f.date)} vs ${esc(f.opp)} ${f.gf}-${f.ga}">${f.res}</span>`).join("")}</span>`;
  }
  function matchCard(fx) {
    const ph = fx.p_home, pdr = fx.p_draw, pa = fx.p_away;
    const seg = (w, c, lbl) => `<span class="${c}" style="width:${100 * w}%">${100 * w >= 12 ? lbl : ""}</span>`;
    const facs = fx.factors.filter(f => f.label !== "近期状态").map(f =>
      `<div class="fac lean-${f.lean}"><span class="dot"></span><span class="fl">${esc(f.label)}</span><span class="fd">${esc(f.detail)}</span></div>`).join("");
    const sl = fx.top_scores.slice(0, 3).map(s => `<span class="sl">${esc(s.score)}<small>${esc(s.p)}</small></span>`).join("");
    const mk = fx.market ? `<div class="mc-market"><span>市场</span><div class="mm-bar">
        <i class="mm-h" style="width:${100 * fx.market.h}%"></i><i class="mm-d" style="width:${100 * fx.market.d}%"></i><i class="mm-a" style="width:${100 * fx.market.a}%"></i>
      </div><span>${pct(fx.market.h, 0)}/${pct(fx.market.d, 0)}/${pct(fx.market.a, 0)}</span></div>` : "";
    const badge = fx.stage === "group" ? "组 " + fx.group : fx.stage.toUpperCase();
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
      ${mk}</div>`;
  }
  function matches() {
    const dates = [...new Set(D.fixtures.map(f => f.date))].sort();
    let active = "all";
    const grid = $("#match-grid"), filt = $("#match-filters");
    filt.innerHTML = `<button class="fbtn active" data-d="all">全部 ${D.fixtures.length} 场</button>` +
      dates.map(d => `<button class="fbtn" data-d="${d}">${d.slice(5)}</button>`).join("");
    const draw = () => {
      grid.innerHTML = D.fixtures.filter(f => active === "all" || f.date === active).map(matchCard).join("");
    };
    filt.addEventListener("click", e => {
      const b = e.target.closest(".fbtn"); if (!b) return;
      filt.querySelectorAll(".fbtn").forEach(x => x.classList.remove("active"));
      b.classList.add("active"); active = b.dataset.d; draw();
    });
    draw();
  }

  /* ---------- groups ---------- */
  function groups() {
    const order = Object.keys(D.groups).sort();
    $("#group-grid").innerHTML = order.map(g => {
      const st = {}; (D.standings[g] || []).forEach(s => st[s.team] = s);
      const rows = D.groups[g].map(t => {
        const s = st[t.team] || { pld: 0, pts: 0, gf: 0, ga: 0 };
        return { ...t, pld: s.pld, pts: s.pts, gd: s.gf - s.ga, padv: t.p_advance || 0 };
      }).sort((a, b) => b.padv - a.padv);
      const body = rows.map((r, i) => `<tr class="${i < 2 ? "q" : ""}">
        <td class="l tm">${r.flag} ${esc(r.team)}</td>
        <td>${r.pld}</td><td>${r.pts}</td><td>${r.gd > 0 ? "+" : ""}${r.gd}</td>
        <td><span class="adv-pill">${pct(r.padv, 0)}</span><div class="gbar"><i style="width:${100 * r.padv}%"></i></div></td>
      </tr>`).join("");
      return `<div class="gcard"><h3><span class="gl">${g}</span> 小组 ${g}</h3>
        <table class="gtable"><thead><tr><th class="l">球队</th><th>赛</th><th>分</th><th>净</th><th>出线</th></tr></thead>
        <tbody>${body}</tbody></table></div>`;
    }).join("");
  }

  /* ---------- live ---------- */
  function live() {
    if (!D.live.length) { $("#live").style.display = "none"; return; }
    const avg = D.live.reduce((s, x) => s + x.rps, 0) / D.live.length;
    const hits = D.live.reduce((s, x) => s + x.fav_hit, 0);
    $("#live-lead").innerHTML = `已赛 <b>${D.live.length}</b> 场，模型赛前预测的平均 RPS <b>${avg.toFixed(3)}</b>（回测均值约 0.207），最大概率方向命中 <b>${hits}/${D.live.length}</b>。样本极小，仅作滚动校验——比赛越多越有意义。`;
    $("#live-grid").innerHTML = D.live.map(x => {
      const cls = x.rps < 0.1 ? "rps-good" : x.rps < 0.22 ? "rps-mid" : "rps-bad";
      const pv = { H: x.p_home, D: x.p_draw, A: x.p_away }[x.outcome];
      return `<div class="lc">
        <div class="lc-top"><span class="lc-teams">${x.flagH} ${esc(x.home)} <span class="lc-score">${esc(x.actual)}</span> ${esc(x.away)} ${x.flagA}</span></div>
        <div class="lc-pred">模型赛前：胜 ${pct(x.p_home)} / 平 ${pct(x.p_draw)} / 负 ${pct(x.p_away)} ·
          实际给该结果 <b>${pct(pv)}</b> · <span class="${x.fav_hit ? "hit-y" : "hit-n"}">${x.fav_hit ? "✓ 方向命中" : "○ 爆冷"}</span></div>
        <div style="margin-top:8px"><span class="lc-rps ${cls}">RPS ${x.rps.toFixed(3)}</span></div>
      </div>`;
    }).join("");
  }

  /* ---------- credibility ---------- */
  function cred() {
    const bt = D.credibility.backtest;
    if (bt.length) {
      $("#bt-table").innerHTML = `<table class="ctable">
        <thead><tr><th class="l">届</th><th>场</th><th>RPS模型</th><th>RPS均匀</th><th>LogLoss</th><th>比分命中</th></tr></thead>
        <tbody>${bt.map(r => `<tr class="${r.wc === "all" ? "hl" : ""}">
          <td class="l">${r.wc}</td><td>${r.n}</td><td>${r.rps_model.toFixed(3)}</td><td>${r.rps_uniform.toFixed(3)}</td>
          <td>${r.logloss_model.toFixed(3)}</td><td>${pct(r.exact_hit_top1, 0)}</td></tr>`).join("")}</tbody></table>`;
    }
    // calibration scatter
    const cal = D.credibility.calibration;
    if (cal.length) {
      $("#ece-badge").textContent = "ECE " + (D.credibility.calibration_ece || 0).toFixed(3);
      const W = 320, H = 200, pad = 28, sx = v => pad + v * (W - 2 * pad), sy = v => H - pad - v * (H - 2 * pad);
      const maxN = Math.max(...cal.map(c => c.n));
      const pts = cal.map(c => `<circle cx="${sx(c.pred_mean)}" cy="${sy(c.obs_freq)}" r="${3 + 7 * c.n / maxN}" fill="rgba(34,211,238,.55)" stroke="#22d3ee"/>`).join("");
      $("#cal-chart").innerHTML = `<div class="calwrap"><svg class="cal-svg" viewBox="0 0 ${W} ${H}">
        <line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" stroke="#566" stroke-dasharray="4 4" opacity=".6"/>
        <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}" stroke="#334" />
        <line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#334"/>
        ${pts}
        <text x="${W / 2}" y="${H - 4}" fill="#6b7494" font-size="10" text-anchor="middle">模型预测概率 →</text>
        <text x="8" y="${H / 2}" fill="#6b7494" font-size="10" transform="rotate(-90 8 ${H / 2})" text-anchor="middle">实际频率 →</text>
      </svg></div>`;
    }
    // market beat
    const mb = D.credibility.market_beat;
    const body = $("#mb-body");
    if (mb && mb.tournaments && mb.tournaments.length) {
      const rows = mb.tournaments.map(t =>
        `<div class="mb-row"><span>${esc(t.wc)} · ${t.n} 场 <span class="dim">${esc(t.kind || "")}</span></span>
          <span>模型 <b>${t.rps_model.toFixed(3)}</b> · 对手 <b>${t.rps_market.toFixed(3)}</b>
          <span class="cb-edge ${t.rps_model < t.rps_market ? "edge-pos" : "edge-neg"}">${t.rps_model < t.rps_market ? "模型更优" : "市场更优"}</span></span></div>`).join("");
      const o = mb.overall;
      body.innerHTML = rows +
        `<div class="mb-row"><span class="mb-win">合计 ${o.n} 场</span>
          <span class="mb-win" style="color:${o.model_better ? "#5ef2c4" : "#ffa1b4"}">
          ${o.model_better ? "模型 ≤ 市场" : "市场 < 模型"} （Δ${(o.margin >= 0 ? "+" : "") + o.margin.toFixed(4)}）</span></div>` +
        (mb.note ? `<p class="card-note">${esc(mb.note)}</p>` : "");
    } else {
      body.innerHTML = `<p class="mb-pending">真正的「能否跑赢市场」需要历史世界杯的赔率做对标回测。该数据正在抓取/整理中——一旦就位，这里会显示模型 RPS vs 市场 RPS 的逐届对比。<br><br>当前用<b>本届滚动实测</b>（见上方「本届实测」）近似：已赛比赛模型 vs 实际的 RPS。</p>`;
    }
    // method
    $("#method").innerHTML = `<h3>方法与数据</h3><ul>
      <li><b>Elo</b>：eloratings.net 公式自算（K 按赛事重要性 20–60、净胜球放大、主场 +100），${D.meta.fit.n ? "" : ""}全史单遍递推，只用赛前评分（无泄漏）。</li>
      <li><b>比分模型</b>：λ = exp(b0 ± b1·ΔElo/400 + 主场)，Dixon-Coles ρ 修正低比分相关，指数时间衰减加权 MLE。</li>
      <li><b>市值融合</b>：横截面回归 elo ~ log(市值)，权重 0.25 把评分朝市值收缩。</li>
      <li><b>模拟</b>：小组赛（已赛固定）→ FIFA tiebreakers → 12 组前二 + 8 best thirds（495 组合表）→ 淘汰赛（加时 1/3 进球率、点球 50/50）× ${D.meta.n_sims.toLocaleString()}。</li>
      <li><b>数据源</b>：${Object.entries(D.meta.data_info || {}).map(([k, v]) => `${esc(k)}（${esc(String(v).slice(0, 60))}）`).join("；") || "—"}</li>
    </ul>`;
  }

  /* ---------- nav ---------- */
  function nav() {
    const tabs = [...document.querySelectorAll(".tab")], secs = tabs.map(t => $(t.getAttribute("href")));
    const io = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) {
        const id = "#" + e.target.id;
        tabs.forEach(t => t.classList.toggle("active", t.getAttribute("href") === id));
      }});
    }, { rootMargin: "-45% 0px -50% 0px" });
    secs.forEach(s => s && io.observe(s));
  }

  hero(); champ(); matches(); groups(); live(); cred(); nav();
})();
