# Pico2 W + RL7023-11 (Wi-SUN B-route) → InfluxDB v1 Logger

Raspberry Pi **Pico2 W / CircuitPython** と **RL7023-11 (MB‑RL7023‑11)** を使い、スマートメーターから **E0:積算電力量[Wh]** と **E7:瞬時電力[W]** を取得して **InfluxDB v1** へ書き込みます。  
再接続・再JOINの自動回復、HTTP送信の指数バックオフ実装済み。

---

## 特徴
- 30秒ごとに E7、5回に1回 E0 を取得して送信
- JOIN直後の ERXUDP を自動ドレイン
- 自動回復
  - ECHONET 応答の連続失敗 3回 → Re-JOIN
  - HTTP 連続失敗 5回 → Wi‑Fi再接続 + HTTPセッション再生成
  - 送信失敗時は 1,2,4,8,16 秒の指数バックオフ
- SCAN の EPANDESC を全回収し LQI 最大を自動採択
- **1ファイル運用**（`code.py`）＋ **機微情報は `secrets.py`** に分離

---

## ハードウェア
- ボード: Raspberry Pi Pico2 W（Pico W でも可）
- Wi‑SUN: RL7023‑11（MB‑RL7023‑11）
- 配線（UART0, 3.3V TTL）
  | Pico2 W | RL7023‑11 | 備考 |
  |---|---|---|
  | GP0 (TX) | RXD | 交差接続 |
  | GP1 (RX) | TXD | 交差接続 |
  | 3V3 | VCC | 3.3V |
  | GND | GND | 共通 |

> 注意: MB‑RL7023‑11 の FTDI 端子とは二股接続しないでください。

---

## ソフト要件
- CircuitPython 9.x（Pico2 W 用 UF2）
- `code.py`（本リポジトリ）
- `secrets.py`（各自作成。**公開しない**）

---

## セットアップ
1. Pico2 W に CircuitPython を書き込み。
2. このリポジトリの `code.py` を Pico の `CIRCUITPY` にコピー。
3. `secrets.example.py` を **`secrets.py` にコピーして編集**（※ `secrets.py` は公開しない）。
4. 電源投入（**CircuitPython は `code.py` を自動実行**）。

`.gitignore` には `secrets.py` を含めてください。

---

## `secrets.py` に必要なキー（**値はREADMEに書かないでください**）
- Wi‑Fi
  - `ssid`
  - `password`
- InfluxDB v1（/write）
  - `influx_host`
  - `influx_port`（数値）
  - `influx_db`
  - `influx_user`
  - `influx_pass`
- B‑route 認証
  - `rbid`
  - `rbpwd`
- 任意（公開しても良いメタ）
  - `measurement`（既定: `power`）
  - `tags`（例: `place=lab,host=RL7023` など ※ここにも秘匿情報は入れない）

> **大事なこと**: `secrets.py` を絶対にコミットしない/共有しない。値は README にも書かない。

---

## 実行・監視
- USBシリアルでログ確認（Thonny / Mu / mpremote など）
  - `JOIN OK` が出て、その後 `Influx: 204` が周期的に出れば正常。

---

## トラブルシュート（要点）
- `SKSCAN failed` → 設置場所/距離/アンテナを調整。スキャン持続時間を延長。
- `SKJOIN failed` → B‑route 認証を確認。2.4GHz干渉源の確認。
- Influx が 204 以外 → DB名・認証・ポート・ネットワーク到達性を確認。

---

## 免責
本ソフトウェアは無保証です。自己責任で利用してください。B‑route 認証情報は厳重に管理してください。

---

## ライセンス
MIT
