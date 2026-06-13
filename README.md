# worldcup-predict — 2026 世界杯胜负/比分预测

多维数据(国际比赛史 Elo + Transfermarkt 阵容市值 + 博彩赔率)→ Dixon-Coles 双泊松比分模型 → 全赛程 Monte Carlo 模拟。
**Benchmark 不是 accuracy,而是与赔率隐含概率同台对比的 RPS / 概率校准。**

## 结论速览(2026-06-13 生成,50000 次模拟)

- **夺冠概率**:Spain 18.6% · Argentina 13.9% · France 10.3% · England 7.3% · Brazil 5.8%。
- **模型 vs 市场最大分歧**:模型比市场更看好 Argentina(+5.6pp),更不看好 Portugal(−5.8pp)、France(−4.7pp)。
- **回测(2014/18/22,严格 cutoff)**:RPS **0.207** vs 均匀基线 0.242、历史频率 0.238;精确比分命中 **11.5%**,前 5 命中 51.6%。
- **校准**:ECE 0.054;对强队略偏保守,但留一届 CV 证明「锐化」不可泛化,故保留原参(详见报告「概率校准」节)。
- **能否跑赢市场**:对标 112 场真实 Betfair 闭线(2014+2018),模型 RPS 0.1957 vs 市场 0.1914——**2014 跑赢、2018 落后,合计略逊市场 0.0043**。即「在牌桌上但不稳定跑赢」,与先验一致(跑赢闭线极罕见)。
- **前端**:`web/index.html` 是一个世界杯主题的单页仪表盘,逐场展示胜平负/比分/判断依据(Elo·xG·市值·状态·主场·模型vs市场)。
- 完整产物见 `outputs/report.md`,网页见 `web/`。

## 结构

```
data/raw/        martj42 国际比赛史 results.csv(1872–今)+ shootouts/goalscorers + acquisition_*.json(抓取留痕)
data/wc2026/     groups/schedule/format(赛制 + 495 组 best-thirds 组合表)、odds_outright、odds_matches、
                 squad_values、name_map(均经联网核对 + 规范化球队名)
src/wc/          names · data · elo · model · market · simulate · backtest · market_backtest · webdata · report
scripts/         run_pipeline.py(端到端)· run_backtest.py · build_market_data.py(把抓取 JSON 落成数据文件)
                 · calibration_experiment.py(锐化的留一届 CV,负结果)· sanity.py(不变量自检)
web/             index.html · styles.css · app.js · data.js(由管线生成)——世界杯主题单页仪表盘
outputs/         report.md · advancement.csv · ratings.csv · match_predictions.csv · live_eval.csv
                 · calibration.csv · market_beat.json · backtest_{summary,matches}.csv · market_compare_*.csv · predictions.json
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
.venv/bin/python scripts/run_pipeline.py --sims 50000       # 端到端 → outputs/report.md + web/data.js
.venv/bin/python scripts/calibration_experiment.py          # 复核「不锐化」的决策
python3 -m http.server -d web 8765                          # 打开 http://localhost:8765 看前端
```

## 已知局限

- 点球大战 50/50(文献:接近抛硬币);公平竞赛分等次级 tiebreaker 用随机代理(对夺冠概率为二阶影响)。
- 国家队样本天然稀疏,单场预测上限有限——**看概率校准,别看单场是否猜中**。
- 市值融合权重(0.25)无法用历史世界杯直接交叉验证(回测只用 Elo 特征),取保守先验。
- 市场对标回测样本为可联网取得的历史 Betfair 赔率(2014 全 64 场 + 2018 小组赛 48 场),不含 2018 淘汰赛与 2022(2022 仅有 538 概率对照);2022 闭线赔率未找到可直接下载的镜像。
