# Fact Check Scorer Audit Report

生成: 2026-06-12T14:40:19Z

## 1. 実行情報

| 項目 | 値 |
|------|----|
| 期間 | (全期間) 〜 (全期間) |
| JSONL 総レコード数 | 96 |
| 分析対象 (status=ok) | 81 |
| 除外: fact_check_unavailable | 10 |
| 除外: failed_fact_check | 2 |
| hash 不一致再採点ペア (除外) | 0 paths |
| 使用モデル (主分析) | gemini-2.5-flash |
| モデル混在 | ⚠️ gemini-2.5-flash=93; gemini-2.5-flash-lite=3 |
| prompt_version 混在 | なし |
| 削除済み記事 (データには残存) | 2 |

## 2. 結論

- **再現性**: グレーゾーン多数決を検討 (5-15)
- **判別力(フリップ率)**: 安定 (<10%)
- **実行健全性**: 10.4% unavailable — エラー詳細は分析G参照

## 3. 主要指標

| 指標 | 値 | 判定基準 | 判定 |
|------|----|----------|------|
| factual レンジ中央値 | 10.0 | <5 安定 / 5-15 グレー / >15 要見直し | グレーゾーン多数決を検討 (5-15) |
| フリップ率 | 0.0% | <10% 安定 / 10-25% 多数決 / >25% 再設計 | 安定 (<10%) |
| グレーゾーン率 | 40.0% | — | — |
| 軸間最大|ρ| | なし | >0.8 = 冗長候補 | ✅ |
| unavailable 率 | 10.4% | <5% 正常 | ⚠️ |
| 実質無機能軸 | Citation Cov. | なし = 正常 | ⚠️ 要確認 |

## 4. 各分析の要約

### A. 再採点分散

純粋再採点グループ数: **1**（同一記事・同一本文の複数採点）

| 軸 | レンジ中央値 | p90 | 最大 | std中央値 |
|----|-------------|-----|------|----------|
| Factual | 10.0 | 10.0 | 10.0 | 5.0 |
| Freshness | 0.0 | 0.0 | 0.0 | 0.0 |
| Citation Cov. | 0.0 | 0.0 | 0.0 | 0.0 |
| Risk | 29.0 | 29.0 | 29.0 | 14.5 |

**factual レンジ最大5記事:**
- `docker_500.md` factual_range=10.0  [Factual=[100.0, 90.0], Freshness=[95.0, 95.0], Citation Cov.=[10.0, 10.0], Risk=[5.0, 34.0]]

![rescore range histogram](figures/fig_a_rescore_range.png)

### B. 合否フリップ率

純粋再採点グループ 1 件中、判定が変わったグループ: **0 件**
フリップ率: **0.0%** → 安定 (<10%)

### C. しきい値感度・グレーゾーン

最新レコード使用: 80 件

⚠️ **実質無機能の軸** (合格率 >95%): Citation Cov.

| 軸 | 中央値 | 合格率 | グレーゾーン率 |
|----|--------|--------|--------------|
| Factual | 95.0 | 90.0% | 13.8% |
| Freshness | 87.0 | 95.0% | N/A |
| Citation Cov. | 18.0 | 100.0% | N/A |
| Risk | 21.0 | 83.8% | 35.0% |

![score distributions](figures/fig_c_distributions.png)

### D. 軸間相関 (Spearman)

n=80 件（最新レコード）
冗長ペアなし (|ρ|≦0.8)

| | Factual | Freshness | Citation Cov. | Risk |
|---|---|---|---|---|
| Factual | 1.000 | 0.312 | 0.175 | -0.643 |
| Freshness | 0.312 | 1.000 | -0.161 | -0.300 |
| Citation Cov. | 0.175 | -0.161 | 1.000 | -0.176 |
| Risk | -0.643 | -0.300 | -0.176 | 1.000 |

![correlations](figures/fig_d_correlations.png)

### E. 時系列ドリフト

週数: 1  （現時点のデータ期間が短いため、将来の監査に向けた枠組みとして出力）
変化点: model=gemini-2.5-flash-lite at 2026-06-12T07:48:20Z
![timeseries](figures/fig_e_timeseries.png)

### F. セグメント別分析

**daily** (n=46)
**rss** (n=32)
**deleted** (n=2)

**仮説検証:**

① risk 軸は不適格(deleted)群で高いか？
  - deleted 中央値=57.5 (n=2), daily=24.5, rss=18.0
  → deleted > daily (**仮説支持**) ※ n が小さいため解釈は慎重に

② factual 軸は不適格群を検出できるか？
  - deleted 中央値=83.0 (n=2), daily=95.0, rss=95.0
  → deleted < daily (**仮説支持**) ※ n が小さいため解釈は慎重に

**ツール別スコア中央値 (n≥3のみ):**

| ツール | n | Factual | Freshness | Citation | Risk |
|--------|---|---------|-----------|----------|------|
| AWS | 10 | 87.5 | 87.0 | 17.5 | 47.5 |
| Ansible | 6 | 95.0 | 88.5 | 13.5 | 24.5 |
| Azure | 8 | 95.0 | 87.0 | 19.0 | 30.0 |
| Dev.to - AWS | 9 | 95.0 | 87.0 | 21.0 | 18.0 |
| Dev.to - DevOps | 10 | 93.5 | 90.0 | 11.0 | 18.0 |
| Dev.to - Docker | 10 | 90.0 | 87.0 | 10.0 | 18.0 |
| Docker | 11 | 95.0 | 90.0 | 27.0 | 26.0 |
| Docker Compose | 8 | 95.0 | 90.0 | 10.0 | 20.5 |
| Firebase | 3 | 95.0 | 95.0 | 24.0 | 5.0 |

![segment boxplots](figures/fig_f_segments.png)

### G. 実行健全性

| status | 件数 | 割合 |
|--------|------|------|
| ok | 84 | 87.5% |
| fact_check_unavailable | 10 | 10.4% |
| failed_fact_check | 2 | 2.1% |

**error_detail 頻度上位:**
- `gemini`: 4 件
- `empty`: 1 件
- `json_parse_error`: 1 件

**URL チェック結果** (総ソース 2770 件):
- 200: 1963 (70.9%)
- skipped: 806 (29.1%)
- 202: 1 (0.0%)
- grounding URL (vertexaisearch等): 2064 (74.51%)

unsupported_claims / 記事: 中央値=1.0, 最大=20

## 5. 推奨アクション

- ⚠️ factual レンジ中央値 5-15 → **新記事ゲートの3回採点・多数決化**を推奨
- ⚠️ 実質無機能軸 (Citation Cov.) → しきい値の見直しまたは軸の廃止を検討

---
*このレポートは `scripts/audit_fact_check.py` により自動生成されました。*