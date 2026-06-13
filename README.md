# worldcup-predict — 2026 世界杯胜负/比分预测

多维数据(国际比赛史 Elo + Transfermarkt 阵容市值 + 博彩赔率)→ Dixon-Coles 双泊松比分模型 → 全赛程 Monte Carlo 模拟。
**Benchmark 不是 accuracy,而是与赔率隐含概率同台对比的 RPS / 概率校准。**

## 结论速览(2026-06-13 生成,50000 次模拟)

- **夺冠概率**:Spain 18.6% · Argentina 13.9% · France 10.3% · England 7.3% · Brazil 5.8%。
- **模型 vs 市场最大分歧**:模型比市场更看好 Argentina(+5.6pp),更不看好 Portugal(−5.8pp)、France(−4.7pp)。
- **回测(2014/18/22,严格 cutoff)**:RPS **0.207** vs 均匀基线 0.242、历史频率 0.238;精确比分命中 **11.5%**,前 5 命中 51.6%。
- **校准**:ECE 0.054;对强队略偏保守,但留一届 CV 证明「锐化」不可泛化,故保留原参(详见报告「概率校准」节)。
- 完整产物见 `outputs/report.md`。

## 结构

```
data/raw/        martj42 国际比赛史 results.csv(1872–今)+ shootouts/goalscorers + acquisition_*.json(抓取留痕)
data/wc2026/     groups/schedule/format(赛制 + 495 组 best-thirds 组合表)、odds_outright、odds_matches、
                 squad_values、name_map(均经联网核对 + 规范化球队名)
src/wc/          names · data · elo · model · market · simulate · backtest · report
scripts/         run_pipeline.py(端到端)· run_backtest.py · build_market_data.py(把抓取 JSON 落成数据文件)
                 · calibration_experiment.py(锐化的留一届 CV,负结果)· sanity.py(不变量自检)
outputs/         report.md · advancement.csv · ratings.csv · match_predictions.csv · live_eval.csv
                 · calibration.csv · backtest_{summary,matches}.csv · market_compare_{outright,matches}.csv · predictions.json
```

## 模型

1. **Elo**:eloratings.net 公式自算(K 按赛事重要性 20–60、净胜球放大、主场 +100),全史单遍递推,训练只用赛前 Elo(无泄漏)。
2. **比分模型**:λ_home = exp(b0 + b1·ΔElo/400 + b_home·主场),λ_away = exp(b0 − b1·ΔElo/400),Dixon-Coles ρ 修正低比分相关,指数时间衰减(ξ=0.25)加权 MLE。国家队样本稀疏,故用 Elo 驱动 λ 而非每队自由攻防参数。
3. **市值融合**:横截面回归 elo ~ a + b·log(市值),按权重 0.25 把每队评分朝市值隐含值收缩(对 Iran 等「Elo 高、市值低」的队是温和正则)。
4. **模拟**:小组赛(已赛结果固定)→ FIFA tiebreakers(分→净胜→进球→相互战绩递归→抽签代理)→ 12 组前二 + 8 best thirds(FIFA 组合表,缺则约束回溯)→ R32 对位 → 淘汰赛(加时按 1/3 进球率、点球 50/50)× N 次。
5. **回测 + 校准**:2014/18/22 严格 cutoff;RPS/LogLoss/Brier/精确比分命中 vs 基线;三分类 one-vs-rest 概率校准表 + ECE。
6. **市场对比**:夺冠赔率 power 法去 margin → 对照模型夺冠概率;单场 1X2 proportional 去 margin(并剔除疑似解析错误的赔率行)。
7. **滚动校验**:对本届已赛比赛实时算模型 RPS / 方向命中(`live_eval.csv`)。

## 数据来源(均联网核对,2026-06-12/13)

- 比赛史:martj42/international_results。分组/赛程/已赛比分:Wikipedia + ESPN + CBS + FIFA(分组 `matches_canonical=true`,零分歧)。
- 夺冠赔率:BetMGM(经 Yahoo 汇总,DraftKings/Kalshi 交叉验证)。单场赔率:Oddschecker/ESPN/Bet365。阵容市值:Transfermarkt。

## 运行

```bash
.venv/bin/python scripts/sanity.py                          # 不变量自检
.venv/bin/python scripts/build_market_data.py               # (重)生成赔率/市值/比分数据文件
.venv/bin/python scripts/run_pipeline.py --sims 50000       # 端到端 → outputs/report.md
.venv/bin/python scripts/calibration_experiment.py          # 复核「不锐化」的决策
```

## 已知局限

- 点球大战 50/50(文献:接近抛硬币);公平竞赛分等次级 tiebreaker 用随机代理(对夺冠概率为二阶影响)。
- 国家队样本天然稀疏,单场预测上限有限——**看概率校准,别看单场是否猜中**。
- 市值融合权重(0.25)无法用历史世界杯直接交叉验证(回测只用 Elo 特征),取保守先验。
- 真正的「能否跑赢市场」需历史赔率做市场对标回测——当前用本届滚动 RPS 近似,赔率覆盖 24/28 场上场。
