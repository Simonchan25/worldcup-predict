# worldcup-predict — 2026 世界杯胜负/比分预测

多维数据(比赛历史 Elo、Transfermarkt 阵容市值、博彩赔率)+ Dixon-Coles 双泊松比分模型 + 全赛程 Monte Carlo 模拟。Benchmark 不是 accuracy,而是与赔率隐含概率同台对比的 RPS / 概率校准。

## 结构

```
data/raw/        martj42 国际比赛史 (results.csv 1872-今) + 补充
data/wc2026/     赛程/分组/赛制、外部 Elo、阵容市值、赔率 (workflow agents 抓取)
src/wc/          names / data / elo / model / simulate / market / backtest / report
scripts/         run_pipeline.py (端到端) · run_backtest.py · sanity.py
outputs/         report.md · advancement.csv · match_predictions.csv · ...
```

## 模型

1. **Elo**:eloratings.net 公式自算(K 按赛事重要性 20-60,净胜球放大,主场 +100),全史单遍递推,训练用赛前 Elo。
2. **比分模型**:λ_home = exp(b0 + b1·ΔElo/400 + b_home·主场),Dixon-Coles ρ 修正低比分相关,指数时间衰减加权 MLE。
3. **市值融合**:横截面回归 elo ~ log(市值),按权重(默认 0.25)融合进评分。
4. **模拟**:小组赛(已赛结果固定)→ FIFA tiebreakers → 12 组前二 + 8 best thirds → R32 对位(FIFA 组合表或约束匹配)→ 淘汰赛(加时 λ/3,点球 50/50)× N 次。
5. **回测**:2014/2018/2022 世界杯,严格 cutoff 前训练,RPS/LogLoss/Brier/精确比分命中 vs 基线。
6. **市场对比**:夺冠赔率 power 法去 margin → 与模型夺冠概率对照;单场 1X2 同理。

## 运行

```bash
uv venv .venv && uv pip install -p .venv/bin/python pandas numpy scipy
.venv/bin/python scripts/sanity.py
.venv/bin/python scripts/run_pipeline.py --sims 20000
```
