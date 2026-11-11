import json
import tempfile
import unittest
from pathlib import Path

import gen_io_page as gen
from renderers import settings
from webgui.api import Api


class SettingVisibilityTest(unittest.TestCase):
    def api(self):
        api = Api()
        api._data['pages'] = [{'kind': 'qcomm', 'left_model': 'QJ61BT11N',
                               'right_model': 'QJ71E71-100', 'left_station': '3',
                               'right_ip': '192.168.1.10', 'left_dip': 'SW1 ON'}]
        return api

    def texts(self, page):
        root, _ = gen.build_project({'front_pages': False}, [(page, None)])
        return [t.get('text') for t in root.findall('./diagram/inputs/input')]

    def test_sides_use_their_own_model_and_optional_fields_start_hidden(self):
        page = self.api().page(0)
        self.assertIn('left_station', page['visible'])
        self.assertIn('left_communication', page['visible'])
        self.assertNotIn('left_ip', [c['key'] for c in page['settings']])
        self.assertIn('right_ip', page['visible'])
        self.assertNotIn('right_station', [c['key'] for c in page['settings']])
        self.assertNotIn('left_dip', page['visible'])
        self.assertEqual(page['values']['left_dip'], 'SW1 ON')

    def test_hide_save_reload_and_restore_preserve_values_and_change_output(self):
        api = self.api()
        self.assertIn('192.168.1.10', self.texts(api._data['pages'][0]))
        hidden = api.set_setting_visibility(0, 'right_ip', False)
        self.assertNotIn('error', hidden)
        # Editing a different field must not erase the invisible value or its visibility.
        values = hidden['values']; values['title'] = 'test'
        self.assertNotIn('error', api.update_page(0, values, '', 'title'))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'project.json'
            self.assertNotIn('error', api.save_as(str(path)))
            saved = json.loads(path.read_text(encoding='utf-8'))['pages'][0]
            self.assertEqual(saved['right_ip'], '192.168.1.10')
            self.assertFalse(saved['settings_visibility']['right_ip'])
            other = Api(); other.open_project(str(path))
            self.assertNotIn('right_ip', other.page(0)['visible'])
            self.assertNotIn('192.168.1.10', self.texts(other._data['pages'][0]))
            other.set_setting_visibility(0, 'right_ip', True)
            self.assertIn('192.168.1.10', self.texts(other._data['pages'][0]))

    def test_undo_and_invalid_toggle(self):
        api = self.api()
        api.set_setting_visibility(0, 'right_ip', False)
        self.assertNotIn('error', api.undo())
        self.assertIn('right_ip', api.page(0)['visible'])
        before = json.dumps(api._data)
        for key, value in [('left_ip', True), ('right_ip', 'false'), ('unknown', False)]:
            self.assertIn('error', api.set_setting_visibility(0, key, value))
            self.assertEqual(json.dumps(api._data), before)

    def test_optional_setting_and_communication_name(self):
        api = self.api()
        api.set_setting_visibility(0, 'left_dip', True)
        texts = self.texts(api._data['pages'][0])
        self.assertIn('機器設定', texts)
        self.assertIn('SW1 ON', texts)
        self.assertIn('通信設定', texts)
        self.assertNotIn('ディップスイッチ', texts)

    def test_no_independent_fields_on_expansion_and_optical_tsn_keeps_ip(self):
        self.assertEqual(settings.controls({'kind': 'remotebody', 'model': 'NZ2EX2B1-16D'}),
                         [{'key': 'dip', 'label': '機器設定', 'visible': False}])
        rows = settings.fields(model='RJ71GN11-SX', values={})
        self.assertIn(('IP設定', 'ip'), rows)
        self.assertNotIn('station', settings.profile('IESH-MB205G-R')['available'])
        self.assertEqual(settings.profile('IESH-MB205G-R')['available'], [])


    def test_cpu_got_and_remote_drawings_follow_visibility(self):
        pages = [dict(kind='iqrbody', model='R04CPU', base_model='R35B', power_model='R61P'),
                 dict(kind='qbody', model='Q03UDVCPU', base_model='Q35B', power_model='Q61P'),
                 dict(kind='fx5body', model='FX5U-32MR/ES'),
                 dict(kind='gotbody', model='GT2715-XTBA'),
                 dict(kind='remotebody', model='NZ2GF2B1-16D')]
        for page in pages:
            with self.subTest(kind=page['kind']):
                page.update(ip='192.168.1.77', settings_visibility={'ip': True})
                root, _ = gen.build_project({'front_pages': False}, [(page, None)])
                self.assertIn('192.168.1.77', [n.get('text') for n in root.findall('./diagram/inputs/input')])
                page['settings_visibility']['ip'] = False
                root, _ = gen.build_project({'front_pages': False}, [(page, None)])
                self.assertNotIn('192.168.1.77', [n.get('text') for n in root.findall('./diagram/inputs/input')])
                self.assertEqual(page['ip'], '192.168.1.77')


if __name__ == '__main__':
    unittest.main()
