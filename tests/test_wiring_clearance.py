"""接続図の水平引出し範囲を、別機器・文字・設定欄でふさがない。"""
import unittest

import gen_io_page as gen
from renderers import hmi
from renderers.controllers import build_body
from renderers.inverter import build_body as inverter_body


def obstacles(page):
    objects = []
    for shape in page.shapes:
        if shape.get('type') == 'Rectangle':
            objects.append(('枠', *(float(shape.get(k)) for k in ('x1', 'y1', 'x2', 'y2'))))
    for text in page.texts:
        x, y = float(text.get('x')), float(text.get('y'))
        size = float(text.get('font').split(',')[1])
        value = text.get('text', '')
        objects.append((value, x + 4, y + 4, x + 4 + gen.text_w(value, size), y + 4 + size * gen.PX_PER_PT))
    hits = []
    for key, _, x, y in page.placed:
        for _, orientation, dx, dy in page.sym[key].terminals.values():
            if orientation not in ('w', 'e'):
                continue
            px, py = x + dx, y + dy
            low, high = ((620 if px >= 620 else 20), px) if orientation == 'w' else (px, 1220 if px >= 620 else 620)
            for label, x1, y1, x2, y2 in objects:
                if label == '枠' and x1 <= px <= x2 and y1 <= py <= y2:
                    continue  # 接続点が属する機器の外枠。
                if y1 < py < y2 and min(high, x2) - max(low, x1) > 1:
                    hits.append((key, px, py, label))
    return hits


class WiringClearanceTest(unittest.TestCase):
    def test_mxf_maximum_composition_leaves_power_lan_and_usb_routes_clear(self):
        for model, spec in gen.MX_CPU.items():
            page = dict(kind='mxbody', model=model, modules=['FX5-4AD-ADP'] * 4 + ['FX5-485ADP'] * 2 + ['MXF100-X32'] * 12,
                        settings_visibility={k: True for k in ('station', 'ip', 'communication', 'dip')})
            built = build_body(page, spec, gen.build_symbols())
            self.assertEqual(obstacles(built), [], model)
            frames = [s for s in built.shapes if s.get('type') == 'Rectangle']
            self.assertLessEqual(max(float(s.get('y2')) for s in frames), 790)

    def test_got_terminal_serial_and_lan_routes_are_clear(self):
        for model, spec in gen.GOT_BODY.items():
            built = hmi.build_body(dict(model=model), gen.build_symbols(), spec, gen.Page, gen.Symbol, gen.page_heading)
            self.assertEqual(obstacles(built), [], model)

    def test_inverter_terminals_and_connectors_leave_space_to_the_right(self):
        for model in ('FR-E820-0.75K-1', 'FR-E820-0.75K-EPA', 'FR-D820-0.75K-042'):
            built = inverter_body(dict(kind='inverter', model=model), gen.INVERTERS[model], gen.build_symbols())
            self.assertEqual(obstacles(built), [], model)


if __name__ == '__main__':
    unittest.main()
