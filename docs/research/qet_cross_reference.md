# QETクロスリファレンスの表示・追従確認

確認日: 2026-10-28。インストール済みQETで実際に接点を移動し、保存した。

## 確認できたこと

- 標準の「十字表示」(`displayhas="cross"`)は、a接点(NO)とb接点(NC)を左右に分ける。見出しは接点記号。
- MY2Nのコイルと、a接点9–5、b接点12–4をQETの双方向リンクで関連付けた。
- a接点をQET上でx=650から776へ移動すると、コイル側の参照が `1-11C` から `1-13C` に自動更新された。b接点の `1-16C` は変わらない。
- 保存後のファイルでも移動位置とコイル・接点のリンクを確認した。生成スクリプトの再実行はしていない。

## 制限

既存PLCのIO図の「機器番号・型式｜a/bの上下2行｜各極の使用位置」という独自表と、QET標準の十字表示は別形式。
QET標準設定で上下2行・極ごとの列へ変更する方法は確認できなかった。公開ソースの `CrossRefItem::drawAsCross()` も中央の縦線、見出しの横線、左右の接点記号を直接描画する構造だった。
独自表の文字はQETの自動参照ではないので、標準の双方向リンクを付けるだけでは移動後に更新されない。

## 外部更新機能（実装済み）

`tools/update_xrefs.py` とGUIの「参照表を更新」で、QETに保存されたコイル・接点のリンクからa/bの横表を生成・更新する。
表の部品情報に所有コイルの固有IDを保存し、QETで保存し直しても重複せず更新できる。表を手動で移動した位置も維持する。
自動更新のタイミングは外部ツール実行時。QET内で移動した瞬間に更新する機能ではない。既存PLCのIO図の生成処理は変更していない。

## 参照資料

- [QET公式マニュアル](https://qelectrotech.org/test/lang-en/manual): Cross references / View cross。
- [QET公開ソース](https://github.com/qelectrotech/qelectrotech-source-mirror/blob/master/sources/qetgraphicsitem/crossrefitem.cpp): `buildHeaderContact()`、`drawAsCross()`。公開masterの実装であり、インストール版との完全一致は未確認。
