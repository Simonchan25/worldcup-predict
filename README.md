# worldcup-predict — 2026 世界杯胜负/比分预测

多维数据(国际比赛史 Elo + Transfermarkt 阵容市值 + 博彩赔率)→ Dixon-Coles 双泊松比分模型 → 全赛程 Monte Carlo 模拟。
**Benchmark 不是 accuracy,而是与赔率隐含概率同台对比的 RPS / 概率校准。**

## 结论速览(2026-06-13 生成,50000 次模拟)

- **夺冠概率**:Spain 18.6% · Argentina 13.9% · France 10.3% · England 7.3% · Brazil 5.8%。
- **模型 vs 市场最大分歧**:模型比市场更看好 Argentina(+5.6pp),更不看好 Portugal(−5.8pp)、France(−4.7pp)。
- **回测(2014/18/22,严格 cutoff)**:RPS **0.207** vs 均匀基线 0.242、历史频率 0.238;精确比分命中 **11.5%**,前 5 命中 51.6%。
- **校准**:ECE 0.054;对强队略偏保守,但留一届 CV 证明「锐化」不可泛化,故保留原参(详见报告「概率校准」节)。
- **能否跑赢市场**:对标 112 场真实 Betfair 闭线(2014+2018),模型 RPS 0.1957 vs 市场 0.1914——**2014 跑赢、2018 落后,合计略逊市场 0.0043**。即「在牌桌上但不稳定跑赢」,与先验一致(跑赢闭线极罕见)。
- **能否靠下注赚钱(诚实版)**:历史价值投注回测里「要求越高把握、ROI 反而越低」(EV>0→+1.5%、EV>20%→−16.9%),这是**无可利用优势**的典型特征;盲投热门的正收益是 2014/18「大热之年」的小样本运气。**串关只会把抽水相乘——是「方差最大化」不是「收益最大化」。**
- **全盘口**:Dixon-Coles 比分网格直接派生大小球/双方进球/正确比分/亚盘等所有市场的模型「公平赔率」。
- **照妖镜**:EA Sports / Goldman / 本模型三套独立方法都把西班牙列为 2026 头号热门;「预测全对」从来只是「猜中冠军」(3⁻⁶⁴ ≈ 不可能猜全 64 场)。
- **实时赔率**:已接入 the-odds-api(`soccer_fifa_world_cup`,eu 区 ~25 家书,含滚球)——68 场 1X2 + 大小球实时赔率 + 全队夺冠赔率,用于赔率比较/价值/对标。
- **前端**:`web/index.html` 专业仪表盘(侧边栏 + 多面板),8 大板块:首页(夺冠环图/实力走势/排行)、比赛预测、比分预测(热力图)、赔率比较(模型 vs 实时书)、最佳选择(按概率排序,每条带分析)、小组、数据分析、照妖镜。
- 完整产物见 `outputs/report.md`,网页见 `web/`(`python3 -m http.server -d web`)。

## 结构

```
data/raw/        martj42 国际比赛史 results.csv(1872–今)+ shootouts/goalscorers + acquisition_*.json(抓取留痕)
data/wc2026/     groups/schedule/format(赛制 + 495 组 best-thirds 组合表)、odds_outright、odds_matches、
                 squad_values、name_map(均经联网核对 + 规范化球队名)
src/wc/          names · data · elo · model · market · markets(派生盘口) · betting(价值/Kelly/下注回测)
                 · simulate · backtest · market_backtest · webdata · report
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

**赛期自动刷新**:`scripts/refresh.sh` 每天拉取最新国际比赛结果并重跑管线(机械重算,自动在 7/19 后停)。
已注册为 macOS LaunchAgent `com.simonchan.wc2026-refresh`(每天 9:00)。停用:
`launchctl unload ~/Library/LaunchAgents/com.simonchan.wc2026-refresh.plist`。
注意:新的世界杯**赔率/比分**仍需跑一次数据抓取(`build_market_data.py` + 联网),cron 只做重算不做抓取。

## 已知局限

- 点球大战 50/50(文献:接近抛硬币);公平竞赛分等次级 tiebreaker 用随机代理(对夺冠概率为二阶影响)。
- 国家队样本天然稀疏,单场预测上限有限——**看概率校准,别看单场是否猜中**。
- 市值融合权重(0.25)无法用历史世界杯直接交叉验证(回测只用 Elo 特征),取保守先验。
- 市场对标回测样本为可联网取得的历史 Betfair 赔率(2014 全 64 场 + 2018 小组赛 48 场),不含 2018 淘汰赛与 2022(2022 仅有 538 概率对照);2022 闭线赔率未找到可直接下载的镜像。
- **实时/滚球赔率**需第三方 API:推荐 the-odds-api.com 免费档(500 credits/月,需自助申请 key,sport key `soccer_fifa_world_cup`,region `eu` 给 Pinnacle/亚盘);拿到 key 我可接入。当前只有联网抓取的赛前赔率。
- **球员个人数据**:深度球员级建模数据稀缺、且相对「球队 Elo + 阵容市值」边际增益有限,故只做**伤停/缺阵定性层**(`injuries.json`,前端比赛卡展示),不改模型评分——伤停影响留给人结合该清单判断。
