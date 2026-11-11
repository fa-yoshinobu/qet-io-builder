# コネクタの絵(共通部品)

図面に出るコネクタの正面図は、すべて `renderers/connectors.py` の1か所で定義しています。PLC・通信ユニット・GOT・リモートIO のどのページでも同じ絵になります。

## 描き方の決まり
- 外形は太線の角丸、内部は細線
- ピン: オスは黒丸、メスは白丸、性別未確認は位置だけ小さな細線の丸
- D-sub 系の固定ねじは二重丸(中を塗る)
- 高さはおおむね 40(USB・HDMI・SD は実物に合わせて 18〜24)
- 端子(ケーブル1本ぶんの接続点)は左に1つ。SD カードは配線しないので端子なし

## 種類
| 種類 | 名前 |
|---|---|
| `rj45` | RJ-45 |
| `dsub9` | D-sub 9pin |
| `dsub15` | D-sub 15pin |
| `dsub25` | D-sub 25pin |
| `vga` | 高密度D-sub 15pin（3段） |
| `dvi_d` | DVI-D共通外形（リンク数・実ピン数は表さない） |
| `audio_jack` | 3.5mm音声ジャック |
| `gpib` | IEEE 488 24pin |
| `minidin8` | MINI-DIN 8pin |
| `minidin6` | MINI-DIN 6pin |
| `coax_f` | 同軸 F形 |
| `coax_bnc` | 同軸 BNC |
| `optical` | 光ファイバ 2心 |
| `usb_minib` | USB Mini-B |
| `usb_a` | USB Type-A |
| `usb_b` | USB Type-B |
| `modular6` | モジュラー 6pin |
| `usb_c` | USB Type-C |
| `hdmi` | HDMI Type-A |
| `sd` | SD カード |
| `bus` | バス接続 |
| `handheld32` | 丸形 32極 |
| `handheld42` | 角形 42極 |
| `m12_a_5` | M12 Aコード 5極 |
| `m12_x_8` | M12 Xコード 8極 |
| `m12_l_5` | M12 Lコード 5極 |
| `7_8_5` | 7/8インチ 5極 |
| `econ_4` | e-CON 4極 |
| `terminal_3` | ねじ端子台 3極 |
| `terminal_40` | ねじ端子台 40極 |
| `fcn_40` | FCN 40極 |
| `one_touch_5` | ワンタッチ 5極 |
| `power_5` | 電源コネクタ 5極 |
| `proprietary` | 専用コネクタ |

極数つきの `terminal_N`(ねじ端子台)・`mil_N`・`fcn_N`・`power_N`・`one_touch_N` は、定義の `connector_type` に書けば自動で作ります。別名: `usb`・`usb_mini_b` → `usb_minib`、`coax` → `coax_f`、`dsub9_male` → `dsub9`(オス)、`dsub9_neutral` → `dsub9`(性別なし)。

## QET の部品として使う
`python tools/export_connector_elements.py parts/connectors/elements` で `parts/connectors/elements/` に .elmt を書き出します。フォルダごと QET のユーザーコレクションにコピーすると、図面に手で置けます。性別で絵が変わるものはオス・メスの2つを書き出します。

## 新しいコネクタを足すとき
`renderers/connectors.py` に絵の関数を書き、`CONNECTORS` に登録します。上の決まりに合わせてください。図面生成と .elmt の書き出しの両方に反映されます。
