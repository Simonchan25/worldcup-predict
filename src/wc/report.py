"""Generate the Chinese-language markdown report from pipeline artifacts."""
from __future__ import annotations

import pandas as pd


def _pct(x):
    return f"{100 * x:.1f}%"


def render(ctx: dict) -> str:
    """ctx keys: asof, data_info, fit, blend_info, adv (DataFrame),
    market_outright (DataFrame|None), fixtures (DataFrame),
    fixtures_market (DataFrame|None), backtest_summary (DataFrame|None),
    sources (dict)."""
    L = []
    L.append("# 2026 世界杯预测报告\n")
    L.append(f"_生成时间:{ctx['asof']};模型:Elo 特征 + Dixon-Coles 双泊松 + 全赛程 Monte Carlo({ctx.get('n_sims', '?')} 次模拟)_\n")

    # ---- headline: title probabilities vs market
    L.append("## 夺冠概率:模型 vs 博彩市场\n")
    mo = ctx.get("market_outright")
    if mo is not None and len(mo):
        L.append("| # | 球队 | 模型夺冠 | 市场隐含 | 差值(模型-市场) |")
        L.append("|---|------|---------|---------|----------------|")
        for i, r in enumerate(mo.head(20).itertuples(index=False), 1):
            L.append(f"| {i} | {r.team} | {_pct(r.p_model)} | {_pct(r.p_market)} | "
                     f"{100 * (r.p_model - r.p_market):+.1f}pp |")
        L.append("")
        big = mo.reindex(mo['p_model'].sub(mo['p_market']).abs()
                         .sort_values(ascending=False).index).head(5)
        L.append("**模型与市场分歧最大的队伍**(正 = 模型比市场更看好):")
        for r in big.itertuples(index=False):
            L.append(f"- {r.team}: 模型 {_pct(r.p_model)} vs 市场 {_pct(r.p_market)}"
                     f"({100 * (r.p_model - r.p_market):+.1f}pp)")
        L.append("")
    else:
        adv = ctx["adv"]
        L.append("(未获取到可用的夺冠赔率,仅列模型结果)\n")
        L.append("| # | 球队 | 模型夺冠概率 |")
        L.append("|---|------|------------|")
        for i, r in enumerate(adv.head(15).itertuples(index=False), 1):
            L.append(f"| {i} | {r.team} | {_pct(r.p_champion)} |")
        L.append("")

    # ---- advancement table
    L.append("## 晋级概率(前 20)\n")
    L.append("| 球队 | 出线(32强) | 16强 | 8强 | 4强 | 决赛 | 夺冠 |")
    L.append("|------|-----------|------|-----|-----|------|------|")
    for r in ctx["adv"].head(20).itertuples(index=False):
        L.append(f"| {r.team} | {_pct(r.p_r32)} | {_pct(r.p_r16)} | {_pct(r.p_qf)} "
                 f"| {_pct(r.p_sf)} | {_pct(r.p_final)} | {_pct(r.p_champion)} |")
    L.append("")

    # ---- live: model vs reality on matches already played
    live = ctx.get("live")
    if live is not None and len(live):
        L.append("## 本届赛事进行中:模型 vs 实际\n")
        L.append(f"已赛 {len(live)} 场,模型平均 RPS **{live['rps'].mean():.3f}**"
                 f"(越低越好,回测均值约 0.207),最大概率方向命中 "
                 f"{int(live['fav_hit'].sum())}/{len(live)}。样本极小,仅作滚动校验。\n")
        L.append("| 日期 | 比赛 | 实际 | 模型(胜/平/负) | RPS |")
        L.append("|---|---|---|---|---|")
        for r in live.itertuples(index=False):
            L.append(f"| {r.date} | {r.home} vs {r.away} | {r.actual} | "
                     f"{_pct(r.p_home)}/{_pct(r.p_draw)}/{_pct(r.p_away)} | {r.rps:.3f} |")
        L.append("")

    # ---- upcoming fixtures
    fx = ctx.get("fixtures")
    if fx is not None and len(fx):
        L.append("## 未来一周比赛预测\n")
        fm = ctx.get("fixtures_market")
        has_mkt = fm is not None and len(fm) > 0
        hdr = "| 日期 | 比赛 | 胜 | 平 | 负 | 最可能比分 |"
        if has_mkt:
            hdr += " 市场(胜/平/负) |"
        L.append(hdr)
        L.append("|---|---|---|---|---|---|" + (" ---|" if has_mkt else ""))
        for r in fx.itertuples(index=False):
            tops = str(r.top_scores).split("; ")[:3]
            row = (f"| {r.date} | {r.home} vs {r.away} | {_pct(r.p_home)} "
                   f"| {_pct(r.p_draw)} | {_pct(r.p_away)} | {', '.join(tops)} |")
            if has_mkt:
                m = fm[(fm["home"] == r.home) & (fm["away"] == r.away)]
                if len(m):
                    mm = m.iloc[0]
                    row += (f" {_pct(mm['mkt_home'])}/{_pct(mm['mkt_draw'])}/"
                            f"{_pct(mm['mkt_away'])} |")
                else:
                    row += " — |"
            L.append(row)
        L.append("")

    # ---- backtest
    bt = ctx.get("backtest_summary")
    if bt is not None and len(bt):
        L.append("## 历届世界杯回测(2014 / 2018 / 2022)\n")
        L.append("RPS 越低越好;基线为均匀分布(0.333/0.333/0.333)与历史频率。\n")
        L.append("| 届 | 场次 | RPS(模型) | RPS(均匀) | RPS(频率) | LogLoss | 精确比分命中 | 比分前5命中 |")
        L.append("|---|------|-----------|-----------|-----------|---------|--------------|-------------|")
        for idx, r in bt.iterrows():
            L.append(f"| {idx} | {int(r['n'])} | {r['rps_model']:.4f} | "
                     f"{r['rps_uniform']:.4f} | {r['rps_freq']:.4f} | "
                     f"{r['logloss_model']:.4f} | {_pct(r['exact_hit_top1'])} | "
                     f"{_pct(r['exact_hit_top5'])} |")
        L.append("")

    # ---- calibration
    cal = ctx.get("calibration")
    if cal is not None and len(cal):
        ece = ctx.get("calibration_ece")
        L.append("## 概率校准(回测 192 场,三分类 one-vs-rest 池化)\n")
        L.append("把模型给出的所有概率按预测值分箱,对比该箱实际发生频率;校准良好则"
                 "两列接近。" + (f"ECE(期望校准误差)= **{ece:.3f}**。\n" if ece is not None else "\n"))
        L.append("| 预测概率区间 | 样本数 | 平均预测 | 实际频率 |")
        L.append("|---|---|---|---|")
        for r in cal.itertuples(index=False):
            L.append(f"| {r.bin} | {r.n} | {_pct(r.pred_mean)} | {_pct(r.obs_freq)} |")
        L.append("")
        L.append("> 样本充足的 0.4–0.7 区间显示模型对强队**略偏保守**(报 50% 实际赢约 67%)。"
                 "但 `scripts/calibration_experiment.py` 用「留一届交叉验证」检验「锐化」修正后发现:"
                 "最优锐化幅度是逐届噪声(2014 是大热届、2022 是冷门届),调参反而让**留出届 RPS 变差"
                 "(0.207→0.209)**。故保留 MLE 拟合值,不做事后锐化——这点保守正是模型对现代世界杯"
                 "不可预测性应有的谦逊。")
        L.append("")

    # ---- methodology
    fit = ctx.get("fit", {})
    blend = ctx.get("blend_info", {})
    L.append("## 方法与数据\n")
    L.append(f"- **比赛历史**:{ctx.get('data_info', '')}")
    p = fit.get("params")
    if p:
        L.append(f"- **Dixon-Coles 拟合**(时间衰减 ξ={fit.get('xi')},样本 {fit.get('n_matches')} 场,自 {fit.get('since')}):"
                 f"b0={p[0]:.3f}, b1(Elo)={p[1]:.3f}, 主场={p[2]:.3f}, ρ={p[3]:.4f}")
    if blend and not blend.get("skipped"):
        L.append(f"- **阵容市值融合**:elo ~ {blend['a']:.0f} + {blend['b']:.0f}·log(市值), "
                 f"权重 {blend['weight']:.0%}(n={blend['n']})")
    for k, v in (ctx.get("sources") or {}).items():
        L.append(f"- **{k}**:{v}")
    L.append("")
    L.append("## 已知局限\n")
    L.append("- 点球大战按 50/50 处理(文献结论:接近抛硬币)。")
    L.append("- 公平竞赛积分等次级 tiebreaker 用随机代理。")
    L.append("- 第三名晋级对位若 FIFA 组合表缺失,用约束匹配近似,对夺冠概率影响为二阶。")
    L.append("- 国家队样本天然稀疏,单场预测上限有限——重点看概率校准而非单场命中。")
    return "\n".join(L) + "\n"
