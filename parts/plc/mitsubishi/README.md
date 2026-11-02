# 機種別定義

`iq_f`（FX5）、`iq_r`、`q` の下を、`cpu`、`digital_io`、`analog_io`、`power_supply`、`base`、`serial`、`network` などの種類ごとに分けています。GUIの「部品から選択」から Maker → Series → Unit の順に選べます。

各JSONは1形名を定義します。該当するフォルダの既存ファイルをコピーし、`model` と `definition` を編集してください。ファイル名は識別しやすい名前にします（Windowsでは `/` を `-` に置き換えます）。`category` と `model` の組み合わせは重複できません。

- `iqr_q`: iQ-R・Qの入力／出力ユニット。`io`、`points`、`pins`、コモン等を指定します。
- `fx5_cpu`: FX5本体。`base` と `variants` の唯一の文字列を結合すると `model` と一致させます。入力点数、出力コモンごとの先頭アドレス（8進文字列）と点数を指定します。本体図では `battery_supported`、`usb_port`、`analog`、`rs485`、`service` を真偽値で指定します。
- `fx5_ext`: FX5デジタル増設。`model` に完全な形名を指定し、`variants` は `[""]` とします。`outputs` は `[コモン番号, 点数]` の配列、番号なしコモンは空文字です。必要に応じて `in_common` や `sink_only` を指定します。
- `fx5_analog`: FX5アナログ機器の端子展開。`channels` に入力／出力、`terminals` に端子名（`{n}` はCH番号）、`power` に電源・接地端子を指定します。外部配線は生成しません。
- `iqr_analog`: iQ-Rアナログ機器の端子展開。指定方法と外部配線の扱いは `fx5_analog` と同じです。
- `iqr_cpu`、`iqr_power`、`iqr_base`: iQ-R構成図のCPU、電源、ベースをそれぞれ1機種ずつ定義します。
- `q_cpu`、`q_power`、`q_base`、`q_analog`: MELSEC-Qの構成図とアナログ端子図の機種別定義です。
- `q_comm`: MELSEC-Q通信ユニットの規格とポート名を機種別に定義します。

アナログ入出力混合機種では、`terminals_by_direction` に `入力` と `出力` の端子配列を指定できます。共通の `terminals` は空配列にします。

`source` にメーカー資料の番号と該当箇所を記入し、未確認情報は `confirmed` や `note` に明記します。定義追加後は `python -m unittest discover -s tests -v` と `python tools/export_units_csv.py` を実行し、該当機種の生成とQET表示を確認してください。
