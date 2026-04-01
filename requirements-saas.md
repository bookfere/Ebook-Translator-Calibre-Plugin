# 要件定義書: Ebook Translator SaaS

- 文書名: Ebook Translator SaaS 要件定義書
- バージョン: 1.0
- 最終更新日: 2026-02-24
- 作成者: Codex

## 改訂履歴
| 版 | 日付 | 変更内容 | 変更者 |
|---|---|---|---|
| 1.0 | 2026-02-24 | 初版作成 | Codex |

---

## 1. 背景と目的

### 背景
- 既存の Calibre Plugin（Ebook-Translator）を SaaS として提供し、クライアントへの配布を行わない運用を前提とする。

### 目的
- 実装者・運用者・意思決定者が同一の要件を参照できるように、現時点の実装と合意済み方針を1つの文書に統合する。

### 非目的
- 課金機能の要件化
- 顧客向け配布物（コンテナ・オンプレ）の要件化

---

## 2. スコープ

### In Scope
- API + UI の提供
- 非同期ジョブ処理（API/Worker 分離）
- R2 直送アップロード
- 対応形式: EPUB / SRT / PGN
- 対応エンジン: OpenAI / DeepL / Google / DeepInfra(DeepSeek)

### Out of Scope
- 課金・請求機能
- オンプレ納品・配布
- 顧客へのコンテナ提供

---

## 3. システム全体像

### 構成要素
- `api`: FastAPI
- `worker`: Celery + Calibre
- `redis`: キュー
- `postgres`: Supabase Postgres
- `r2`: Cloudflare R2
- `ui`: Next.js

### データフロー
1. クライアントが Supabase 認証で JWT 取得
2. `POST /v1/uploads:init` で署名PUT URL取得
3. クライアントが R2 に直接アップロード
4. `POST /v1/jobs` でジョブ作成
5. Worker が R2 から入力を取得し変換・翻訳を実行
6. 出力を R2 に保存し状態更新
7. `GET /v1/jobs/{id}/download-url` で署名GET URL取得

---

## 4. 機能要件（FR）

1. 認証・認可
- Supabase JWT を利用
- API は JWT を検証し認可を行う

2. アップロード初期化
- `POST /v1/uploads:init`
- 署名PUT URL発行

3. ジョブ作成・一覧・詳細・キャンセル
- `POST /v1/jobs`
- `GET /v1/jobs`
- `GET /v1/jobs/{id}`
- `POST /v1/jobs/{id}:cancel`

4. ダウンロードURL発行
- `GET /v1/jobs/{id}/download-url`

5. 形式別制約
- SRT/PGN は入出力形式を一致させる

6. UI機能
- ログイン
- 単一画面ジョブ作成（format切替）
- ジョブ一覧

---

## 5. 非機能要件（NFR）

- SLO: 99.5%
- 性能目標: 同時20ジョブ
- ファイルサイズ上限: 100MB
- 保持期間: 24時間 TTL
- 監視指標: job_success_rate, job_latency_p95, queue_depth, worker_fail_rate, api_5xx_rate

---

## 6. API要件

### エンドポイント一覧
- `POST /v1/uploads:init`
- `POST /v1/jobs`
- `GET /v1/jobs/{id}`
- `GET /v1/jobs`
- `POST /v1/jobs/{id}:cancel`
- `GET /v1/jobs/{id}/download-url`
- `GET /v1/engines`
- `GET /v1/formats`
- `GET /v1/admin/metrics`

### ステータスコード方針
- 2xx: 正常
- 4xx: 入力不正/認証失敗
- 5xx: サーバ処理失敗

### エラーコード方針
- `QUEUE_ERROR`
- `PROCESSING_ERROR`
- 将来: `OUTPUT_VALIDATION_FAILED`

---

## 7. データ要件

### テーブル
- `jobs`
- `job_events`
- `usage_daily`
- `api_tokens`

### インデックス
- `jobs.status`
- `jobs.user_id + created_at`
- `jobs.expires_at`

### 状態遷移
`queued -> processing -> succeeded/failed/canceled/expired`

---

## 8. UI要件

### 画面一覧
- `/login`
- `/new-job`（単一画面、format切替）
- `/jobs`

### 入力項目
- 入力形式
- ソース/ターゲット言語
- エンジン
- ファイル
- 詳細設定（model/prompt/temperature/top_p など安全範囲のみ）

### 表示項目
- ジョブ状態
- 進捗
- 作成/完了時刻
- エラー理由

---

## 9. 運用・保守要件

- デプロイ方式: Docker Compose / Helm
- 環境変数管理: Secret Manager連携
- Cleanup: 期限切れオブジェクト削除
- 監査証跡: job_events とログ

---

## 10. コンプライアンス要件

- GPLv3 SaaS前提
- 参照: `docs/saas-gplv3-compliance-checklist.md`
- 配布発生時は追加手順を適用

---

## 11. テスト要件

- 単体テスト
- API統合テスト
- Worker統合テスト
- E2Eテスト
- 障害試験

---

## 12. 受け入れ基準

- 形式ごとのE2E成功率が 95%以上
- 状態遷移が想定外の値を取らない
- 24時間+1時間以内にデータ削除が完了する
- ローリング更新で停止なく入替が可能

---

## 13. 未解決課題・今後の拡張

- Google OAuth の最終UI統合
- engine_options の安全な公開範囲
- 出力バリデーション強化

---

## 14. 参照

- `ebook-translator-api/README.md`
- `ebook-translator-api/api/app/routers/*.py`
- `ebook-translator-api/api/app/models.py`
- `ebook-translator-api/db/migrations/001_init.sql`
- `ebook-translator-api/worker/app/*.py`
- `ebook-translator-api/ui/app/*.tsx`
- `docs/saas-gplv3-compliance-checklist.md`
