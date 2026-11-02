import unittest

import gen_io_page as gen
from renderers.communication import wrap


class NoteWrapTest(unittest.TestCase):
    def test_punctuation_and_brackets_follow_japanese_line_rules(self):
        for text in ('CC-Link IE FieldはNETWORK(SW1)=ON（電源OFF時に変更）、FW02以降',
                     'CQ:IO-Link/SIO;Q:SIO入出力（モード設定）',
                     'I/OはM12 Aコード、通信はM12 Xコード。コードを混同しない'):
            for width in (90, 120, 160, 226):
                lines = wrap(text, width, 7, gen.text_w)
                with self.subTest(text=text, width=width):
                    self.assertEqual(''.join(lines).replace(' ', ''), text.replace(' ', ''))
                    self.assertTrue(all(line[0] not in '、。）)」' for line in lines[1:]))
                    self.assertTrue(all(line[-1] not in '（(「' for line in lines[:-1]))
                    if len(lines) > 1:
                        self.assertGreater(len(lines[-1]), 2)

    def test_alphanumeric_words_are_not_split(self):
        lines = wrap('Field動作にはFW02以降・機能設定スイッチ1=ONが必要。TSN/Fieldの同時使用ではない。', 150, 8, gen.text_w)
        self.assertTrue(any('TSN/Fieldの' in line or line.startswith('TSN/Field') for line in lines))


if __name__ == '__main__':
    unittest.main()
