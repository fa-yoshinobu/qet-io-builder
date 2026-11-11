import unittest

import gen_io_page as gen
from renderers.communication import wrap
from renderers.typography import fit_cell


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

    def test_cell_uses_eight_point_wrapping_before_shrinking(self):
        text, size = fit_cell('RS-232C データ端末準備完了', 94)
        self.assertEqual(text, 'RS-232C データ端\n末準備完了')
        self.assertEqual(size, 8)

    def test_cell_prefers_word_breaks_at_each_font_size(self):
        for value, width, expected, size in (
            ('RS-232C 送信データ', 72, 'RS-232C\n送信データ', 8),
            ('測温抵抗体入力信号 測温抵抗体入力信号', 94,
             '測温抵抗体入力信号\n測温抵抗体入力信号', 7),
        ):
            with self.subTest(value=value):
                self.assertEqual(fit_cell(value, width), (expected, size))

    def test_cell_does_not_drop_the_end_of_a_long_signal(self):
        value = '測温抵抗体入力' * 5
        text, size = fit_cell(value, 60)
        self.assertEqual(text.replace('\n', ''), value)
        self.assertEqual(size, 7)


if __name__ == '__main__':
    unittest.main()
