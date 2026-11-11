"""QET標準図形を読み込む結合テストの実行条件。"""
import unittest

from renderers import standard


try:
    standard.collection_root()
except ValueError:
    requires_qet = unittest.skip('QET標準コレクションが未導入（QET_ELEMENTS_DIRで指定可）')
else:
    requires_qet = lambda test: test
