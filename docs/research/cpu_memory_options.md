# Q・iQ-R CPUのオプションメモリ

[設定ファイル](../設定ファイル.md) / [Q CPUの選択仕様](q_cpu_selection.md)

登録済みのQ CPU8機種・iQ-R CPU13機種について、メーカー資料で確認した候補を機種別JSONに登録しています。候補は販売中を意味せず、旧機種の図面にも使うため生産終了品を含みます。

## 適合グループ

| CPU | SDカード | メモリカード | 拡張SRAMカセット |
|---|---|---|---|
| Q00UCPU・Q01UCPU | なし | なし | なし |
| Q02UCPU | なし | 下表の13候補 | なし |
| Q03/Q04/Q06/Q13/Q26UDVCPU | NZ1MEMの4候補＋L1MEMの2候補 | なし | Q4MCAの4候補 |
| R00CPU | なし | なし | なし |
| R01CPU・R02CPU | NZ1MEMの4候補 | なし | なし |
| R04/R08/R16/R32/R120CPU（非EN） | NZ1MEMの4候補＋L1MEMの2候補 | なし | NZ2MCの5候補 |
| R04/R08/R16/R32/R120ENCPU | NZ1MEMの4候補 | なし | NZ2MCの5候補 |

## 型式と容量

### SDカード

| 型式 | 容量 |
|---|---|
| NZ1MEM-2GBSD / NZ1MEM-4GBSD / NZ1MEM-8GBSD / NZ1MEM-16GBSD | 順に2 / 4 / 8 / 16GB |
| L1MEM-2GBSD / L1MEM-4GBSD | 順に2 / 4GB |

### Q02UCPUのメモリカード

| 型式 | 種別・容量 |
|---|---|
| Q2MEM-1MBSN / Q2MEM-1MBS | SRAM・1MB |
| Q2MEM-2MBSN / Q2MEM-2MBS | SRAM・2MB |
| Q3MEM-4MBS / Q3MEM-4MBS-SET | SRAM・4MB |
| Q3MEM-8MBS / Q3MEM-8MBS-SET | SRAM・8MB |
| Q2MEM-2MBF / Q2MEM-4MBF | フラッシュ・順に2 / 4MB |
| Q2MEM-8MBA / Q2MEM-16MBA / Q2MEM-32MBA | ATA・順に8 / 16 / 32MB |

`-SET` は保護カバー付きセットです。

### 拡張SRAMカセット

| 型式 | 容量 |
|---|---|
| Q4MCA-1MBS / Q4MCA-2MBS / Q4MCA-4MBS / Q4MCA-8MBS | 順に1 / 2 / 4 / 8MB |
| NZ2MC-1MBS / NZ2MC-2MBS / NZ2MC-4MBS / NZ2MC-8MBS / NZ2MC-16MBS | 順に1 / 2 / 4 / 8 / 16MB |

NZ2MC-16MBSはCPUファームウェア12以降・GX Works3 1.015R以降が必要です。

## バッテリレスオプション

R04/R08/R16/R32/R120CPUと各ENCPUは、CPU設定の「バッテリレス（NZ1BLC）」で有・無・要確認を選びます。「有」のとき図面にNZ1BLCを表示します。拡張SRAMと共用のカセット取付部を使うため、Web GUIでは一方を「有」にすると他方を「無」に切り替えます。R00/R01/R02CPUにはこの欄を出しません。根拠はSH-082488ENG-E 1.3・1.4、2章、5.3です。

## 根拠資料

- Q：SH-080483ENG-BC 2.1.2(4)、9.1.1・9.2.1、10.1～10.2、11.1～11.2。保護カバー付きセットは三菱電機FAのQ02UCPU関連製品およびFA-A-0163 1.1・2.1～2.2も照合。
- iQ-R：SH-081262ENG-AS 1.2・4.4、SH-082488ENG-E 5.2・付録12。[公式CPU仕様](https://www.mitsubishielectric.co.jp/fa/products/cnt/plcr/pmerit/cpu/cpu.html)・[公式FAQ 18245](https://fa-faq.mitsubishielectric.co.jp/faq/show/18245)も照合。
- 個別定義：[Q CPU](../../parts/plc/mitsubishi/q/cpu/) / [iQ-R CPU](../../parts/plc/mitsubishi/iq_r/cpu/)。各定義の `memory_source` に出典を保持します。
