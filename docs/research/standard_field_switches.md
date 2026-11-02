# 標準記号によるフィールドスイッチ（2026-10-28）

## 登録

- OMRON WLCA2 / WLCA2-7 / WLCA2-8 / WLH2：無操作時NC1–2閉、NO3–4開。2回路双断のため1cに置換しない。独立した標準リミットスイッチNO/NCに分け、同一機械で連動する旨を定義。
- SMC IS10-01 / IS10-01-L / IS10-01-Z / IS10-01-6：無圧時1a開。圧力下降設定目盛と上昇ON圧力を区別。2芯無極性。保護箱CD-P12の色・極性を本体に転記しない。
- NOHKEN FQ-6 / FQ-6T / FQ-8 / FQ-8T：フロート単体2芯、標準上限ON・下限OFFの自己保持。上下限間は履歴で決まる。FQ-8Tの温度は−20～+70℃で、FQ-6Tの−10～+90℃と異なる。

## 資料

| 資料 | 公式製品・資料ページ | 確認箇所 |
|---|---|---|
| CSM_WL_DS_E_19_8 | OMRON WL | p1接点・端子、形式表、p20定格 |
| CAT.S60-19B | [SMC IS10](https://www.smcworld.com/webcatalog/ja-jp/switches-sensors-controllers/mechanical-pressure-switches/IS10) | p1形式表示・定格・電気回路、p4設定 |
| CAT.No.315G | [NOHKEN FQ](https://www.nohken.com/products/235/) | p3形式、p4-5定格・2芯・自己保持動作 |
| TS03-0066 | 同上 | p4-6結線・動作確認 |
| CAT.No.343G | [NOHKEN FT](https://www.nohken.com/products/238/) | 候補調査資料。今回登録なし |
| CAT.No.318B | [NOHKEN FS](https://www.nohken.com/products/241/) | FS-2Sは公開資料で端子図不足、今回登録なし |

## 記号

QElectroTech同梱 390_sensors_instruments配下のみ使用。

| キー | ファイル | 役割 |
|---|---|---|
| limit_no | 41_limit_switches/fin_de_course_no.elmt | first=(0,-21), second=(0,21) |
| limit_nc | 41_limit_switches/fin_de_course_nf.elmt | first=(0,-21), second=(0,21) |
| pressure_reed_no | 13_sensors_pressure/pressostat_no.elmt | first=(0,-20), second=(0,20) |
| float_no | 12_sensors_level/niv_liquide_no.elmt | first=(0,-20), second=(0,20)。XML列挙順に依存しない |

芯線のメーカー表示がない2線式は「片側/他側」という編集上の呼称であることを記載し、架空の端子番号や線色を付けていない。安全用途、アナログ伝送器、61F等のフロートレスコントローラは含めない。
