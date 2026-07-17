Claude Code で「既存コードベース＋詳細設計書＋科学的根拠のある工数見積もり」を扱うなら、見積もり**ロジック自体**は skill / subagent に分け、配布や再利用の単位は plugin にするのが最も自然です。 [code.claude](https://code.claude.com/docs/en/plugins)
科学的に有効な見積もり手法は複数ありますが、実務でツール化しやすいのは「参照クラス予測」「分解見積もり（WBS）」「3点見積もり」「COSMIC / Function Point 系」「COCOMO II 系」「履歴データに基づく回帰・ベイズ更新」です。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)

## 見積もり手法

まず前提として、ソフトウェア工数見積もりで「科学的に有効」と言いやすいのは、直感だけでなく、過去データ・不確実性・構造化分解を扱える手法です。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
その観点では、次の手法を候補にするとよいです。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)

- 参照クラス予測（Reference Class Forecasting）: 類似案件の実績分布を基準に補正する手法で、楽観バイアス対策に強いです。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
- 分解見積もり（WBS / bottom-up）: 機能・設計・実装・試験・移行などに分解して積み上げる方法で、既存コードベースや詳細設計書と相性がよいです。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
- 3点見積もり（PERT / Triangular）: 楽観・最頻・悲観の3値で不確実性を扱えるため、単一値より説明責任を持たせやすいです。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
- Function Point / COSMIC: 仕様ベースで規模を測る方法で、コード量ではなく機能量を基準にできます。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
- COCOMO II 系: 規模や複雑性ドライバから工数を計算する代表的パラメトリック手法です。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
- 履歴データ回帰・ベイズ更新: 自社実績を継続学習して精度改善できるため、長期的には最も強いです。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)

## 手法の使い分け

あなたの想定ユースケースでは、既存コードベースと詳細設計書の両方が入力にあるので、1手法に絞るより「ハイブリッド見積もり」の形が適切です。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
具体的には、設計書から機能規模、コードベースから変更難易度、履歴から生産性分布を取り、最後に参照クラス予測でバイアス補正する構成が堅いです。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)

| 手法 | 強み | 弱み | 今回の適合 |
|---|---|---|---|
| 参照クラス予測 | バイアス補正に強い  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 類似案件データが必要  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 高い  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) |
| WBS積み上げ | 詳細設計書と親和性が高い  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 分解品質に依存  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 非常に高い  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) |
| 3点見積もり | 不確実性を表現しやすい  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 前提が粗いと形だけになる  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 高い  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) |
| COSMIC / FP | 機能規模を仕様ベースで測れる  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | カウント規約整備が必要  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 中〜高  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) |
| COCOMO II | 標準化しやすい  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 現代の小変更案件では粗くなりやすい  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 中  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) |
| 回帰・ベイズ更新 | 継続改善しやすい  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 実績DB整備が必要  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) | 非常に高い  [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc) |

## Claude Codeへの落とし込み

Claude Code の docs では、skills は「繰り返し使う手順・チェックリスト・参照知識」を追加する仕組みで、必要時だけ読み込まれます。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
一方 plugins は、skills・agents・hooks・MCP servers などをまとめて共有・再利用するための仕組みとして位置づけられています。 [code.claude](https://code.claude.com/docs/en/plugins)

したがって、今回のようなツールは次の分担が適切です。 [code.claude](https://code.claude.com/docs/en/plugins)

- **Skill**: 見積もり手順書、WBS生成ルール、設計書の読み方、見積もり観点チェックリスト。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
- **Agent / subagent**: 「コード解析担当」「設計書解析担当」「見積もり統合担当」の役割分離。 [code.claude](https://code.claude.com/docs/en/plugins)
- **Plugin**: 上記 skills / agents に加え、必要なら hooks・MCP・LSP をまとめて配布する箱。 [code.claude](https://code.claude.com/docs/en/plugins)
- **Hook**: コミット差分や設計書更新時に見積もり再計算を促す自動化。 [code.claude](https://code.claude.com/docs/en/plugins)
- **MCP server**: チケット、実績DB、工数台帳、DWH など外部データを参照する連携層。 [code.claude](https://code.claude.com/docs/en/plugins)

## 推奨アーキテクチャ

Claude Code の公式 docs では、個人・単一プロジェクト用途なら `.claude/` の standalone 構成、チーム共有や複数案件で使うなら plugin が適するとされています。 [code.claude](https://code.claude.com/docs/en/plugins)
また skill には `disable-model-invocation`、`allowed-tools`、`context: fork`、`agent` などの frontmatter があり、タスク型か参照型かで使い分けできます。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)

今回なら、次の構成が実装しやすいです。 [code.claude](https://code.claude.com/docs/en/plugins)

1. `estimate-scope` skill: 設計書から機能一覧・変更単位・依存関係を抽出する。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
2. `analyze-codebase` skill または subagent: 既存コードの変更影響、複雑度、テスト範囲、外部依存を調べる。 [youtube](https://www.youtube.com/watch?v=jzf7DQa2CAc)
3. `estimate-effort` subagent: WBS化し、各タスクに 3点見積もりを付与し、履歴データで補正する。 [code.claude](https://code.claude.com/docs/en/plugins)
4. `plugin` 化: 上記を namespaced skill / agent としてまとめ、複数PJやチームに配布する。 [code.claude](https://code.claude.com/docs/en/plugins)

## 実装方針

最初から plugin を大きく作るより、Claude Code の推奨どおり `.claude/skills/` で素早く試作し、使える形になったら plugin に昇格する進め方が適しています。 [code.claude](https://code.claude.com/docs/en/plugins)
特に見積もり精度の核心は UI ではなく「過去実績をどう参照し、どのように補正するか」なので、plugin の中に skill 群と見積もり専用 subagent、さらに実績DB参照用の MCP を同梱する設計が最も再現性があります。 [code.claude](https://code.claude.com/docs/en/plugins)

私の提案は次です。 [code.claude](https://code.claude.com/docs/en/plugins)

- 初期版は **plugin + 複数skills + 1〜3 subagents**。
- 見積もりアルゴリズムは **WBS積み上げ + 3点見積もり + 参照クラス予測** を中核にする。
- 自社実績が溜まったら **回帰 / ベイズ更新** を追加する。
- 設計書だけでなく既存コードを使う以上、単独 skill より **subagent 分業** の方が品質が安定しやすいです。 [code.claude](https://code.claude.com/docs/en/plugins)

次に進めるなら、「Claude Code 用の plugin 構成案」と「見積もりロジックの具体的プロンプト設計」をそのまま書き下しますか。 [code.claude](https://code.claude.com/docs/en/plugins)
