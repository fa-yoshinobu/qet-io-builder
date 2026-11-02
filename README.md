# qet-io-builder

![PLC・GOT 図面生成のユニット構成画面](docs/images/app-screenshot.png)

機種別定義と入出力表（CSV）から、QElectroTechで編集できるPLC・GOTなどの配線図（`.qet`）を生成します。生成後はQETで開いて配線を仕上げます。

## 必要なもの

- Python 3.11以上（画面は pywebview。`GUI起動.bat` が初回に入れる）
- QElectroTech（図面の編集・確認・PDF書出し）

QElectroTechは [配布ページ](https://qelectrotech.github.io/qelectrotech-source-mirror/) からNightly Build（開発版）をダウンロードしてください。Windowsでは「Windows Installer.exe」を選びます。

QETは標準の場所へのインストールを推奨します。Windowsでは通常 `C:\Program Files\QElectroTech` です。別の場所にインストールした場合は、標準部品フォルダーを環境変数 `QET_ELEMENTS_DIR` で指定してください。

PDF調整などの追加要件は [使い方](docs/使い方.md) を参照してください。

## はじめ方

1. `GUI起動.bat` を起動し、メニューで「PLC・GOT の図面を作る」を選ぶ。
2. ページを追加し、メーカー → シリーズ → 図面の種類 → 形名の順に選ぶ。本体ページはベースの図でスロットを選んでユニットを追加する。
3. プロジェクトを保存して「図面生成」を押し、出力QETをQElectroTechで開く。

コマンドでの生成:

```console
python gen_io_page.py project.json 出力.qet
```

再生成するとQETで手直しした内容は上書きされます。入力形式・詳細操作は下記資料を参照してください。

リレー・スイッチなどは「制御部品の書出し・ユーザーコレクション登録」から「QETに登録」または「全部QETに登録」でユーザーコレクションへ追加できます。登録先はQETの設定を読み取ります。詳しくは [部品の登録・書出し](docs/使い方.md#部品を書き出す) を参照してください。

## PDF出力例

生成したQETをQElectroTechでPDFに書き出した例です。

### PLC構成図

iQ-Rのベースに入力・出力・アナログ・通信ユニットを搭載し、形名・タグ・アドレス割付を表示します。

![PLC構成図のPDF出力例](docs/images/pdf-example-rack.png)

### IO図（入出力図）

CSVの信号名・機器番号・線番を使い、入力接点や出力負荷と、端子・アドレス・用途の対応を図面にします。

![IO図のPDF出力例](docs/images/pdf-example-io.png)

## 資料

| 資料 | 内容 |
|---|---|
| [使い方](docs/使い方.md) | GUI、部品書出し、参照表更新、サンプル、PDF |
| [設定ファイル](docs/設定ファイル.md) | JSON・CSV、ページ種類、タグ、配線情報・端子台接続図 |
| [開発・保守](docs/開発・保守.md) | コード配置、機種追加、検証、資料・生成物の扱い |
| [図面の書き方ルール](docs/図面の書き方ルール.md) | 配置・端子・配線・注記の共通ルール |
| [対応機種一覧](units_supported.csv) | Excel用CSV。個別の確認状態は `parts/` の対応一覧を参照 |
| [CHANGELOG](CHANGELOG.md) | 変更・検証の履歴 |
| [TODO](TODO.md) | 残件・未確認事項 |

保存済みサンプルは [Sample_qet/](Sample_qet/) にあります。PDF・メーカー資料はGit対象外です。
