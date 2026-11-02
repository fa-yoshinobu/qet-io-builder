# 部品定義

標準ではこのフォルダ以下の機種JSONを読み込みます。

- `plc/mitsubishi/`: FX5、iQ-R、Q、MX、CC-Link／CC-Link IEリモートIO。
- `hmi/mitsubishi/`: GOT2000、GOT3000、通信・接続オプション。
- `inverter/`: インバータの端子図。
- `network/`: ミスミの産業用スイッチングハブ。電源・接地・警報・RJ-45の箱型部品。
- `control/`: リレー・接触器・操作機器・保護器など。[制御部品](control/README.md)を参照。
- `power_supply/omron/`: DC24V電源の機種JSONと単体QET部品（ELMT）。

各形名は1つのJSONで定義します。機種を追加する際は該当フォルダの既存定義を参考にし、公式資料の文書番号と照合ページをsourceに記録してください。ローカルパス・PDFファイル名・資料の保存記録は記載しません。JSONはUTF-8、Excelで編集するCSVはUTF-8 BOM付きです。

GUIの表示項目は部品フォルダのgui_properties.tomlが管理します。GOT本体はgot_body（ページ種類gotbody）、オプションはgot_option（gotoption）。GOT本体はseries/display/resolution/power/interfaces/battery_supported/battery_type/sd_card_supported/sourceを記載し、非搭載端子を追加しないでください。GOT3000のdisplayは画面・解像度・タッチ方式の辞書です。未確認のピン番号や内部接続を推測して追加しないでください。

一般機器は[control/README.md](control/README.md)の方式を使い、共通のstandard_symbols.tomlを参照します。標準記号を基本とし、箱型の外部端子図が必要な機器は機種定義で区別します。
