# 外部記号のライセンス

このプロジェクトのMITライセンスは、自作のコード・文書・部品定義に適用します。外部由来の記号、その派生部分、外部ソフトウェアの権利・利用条件を変更するものではありません。

## このプロジェクトでは何が該当するか

GitHubで配布しているのは、自作アプリのソースコード・文書・部品定義です。QET標準コレクションは同梱していません。READMEの図面例は、標準記号を電気図面に組み込んだ利用に当たります。

利用者が生成した図面を納品・販売するときに、その図面をMITで公開する必要はありません。一方、QET標準記号から作った部品を `.elmt` ファイルや部品集として配布するときは、「図面とは別の記号の再配布」に当たるため、下記の外部記号の条件が関係します。

## QElectroTech標準コレクション

- 出典：[QElectroTech公式要素コレクション](https://github.com/qelectrotech/qelectrotech-elements)
- 作者：The QElectroTech team および各記号の作者。個別の作者表示は元の記号の `informations` に記載されています。
- 利用条件：[公式の ELEMENTS.LICENSE](https://github.com/qelectrotech/qelectrotech-elements/blob/master/ELEMENTS.LICENSE)
- 記号を図面と別に再配布する場合のライセンス：[Creative Commons Attribution 3.0 Unported（CC BY 3.0）](https://creativecommons.org/licenses/by/3.0/)

本プロジェクトは、標準コレクションをQElectroTechのインストール先から読み込みます。参照する記号は [標準記号の定義](parts/standard_symbols.toml) と `renderers/swallow_transformer.py` にあります。

派生部品では、元の図形を使い、機種別の型式・定格・端子名・配置などを変更します。変圧器の外部端子図では標準記号の巻線・鉄心などを組み込みます。書き出し時は元記号の作者・ライセンス情報を保持します。

公式条件は、電気図面内での記号の利用・変更・組み込みを、図面の最終ライセンスに関係なく認めています。記号や派生部品を図面と別に再配布するときは、作者・出典・ライセンス・変更内容の表示を保持し、CC BY 3.0の条件に従ってください。

現在の公式 `ELEMENTS.LICENSE` には、機械学習モデルの構築用サンプルデータとしての利用を許諾しない旨の追加記載もあります。利用するコレクションに付属する原文と、個別記号の表示を確認してください。外部由来の部分を本プロジェクトのMITライセンスで再許諾するものではありません。

## QElectroTech本体

QElectroTech本体と要素コレクションは別のライセンスです。本プロジェクトはQElectroTech本体を同梱しません。本体の利用・再配布には、その配布物に付属するライセンスが適用されます。
