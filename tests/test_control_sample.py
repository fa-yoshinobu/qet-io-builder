from tests.qet_support import requires_qet
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from tools.make_control_sample import make


class ControlSampleTest(unittest.TestCase):
    @requires_qet
    def test_native_links_terminals_and_self_hold_sequence(self):
        for horizontal in (False, True):
            with self.subTest(horizontal=horizontal):
                self.check_sample(horizontal)

    def check_sample(self, horizontal):
        with tempfile.TemporaryDirectory() as folder:
            root = ET.parse(make(Path(folder) / 'sample.qet', horizontal)).getroot()
        definitions = {e.get('name'): e.find('definition') for e in root.findall('./collection/category/category/element')}
        elements = {e.get('uuid'): e for e in root.findall('./diagram/elements/element')}
        parts = {e.get('type').split('/')[-1][:-5]: uid for uid, e in elements.items()
                 if not e.get('type').endswith(('junction.elmt', 'node.elmt'))}
        terminals = {}
        for uid, element in elements.items():
            definition = definitions[element.get('type').split('/')[-1]]
            terminals[uid] = {t.get('name') or t.get('uuid'): t.get('uuid') for t in definition.findall('./description/terminal')}
            for link in element.findall('./links_uuids/link_uuid'):
                other = elements[link.get('uuid')]
                self.assertIn(uid, [n.get('uuid') for n in other.findall('./links_uuids/link_uuid')])
        self.assertEqual(len(root.findall('.//links_uuids/link_uuid')), 6)
        self.assertEqual(set(terminals[parts['relay_coil']]), {'13', '14'})
        self.assertEqual(set(terminals[parts['relay_contact_1']]), {'9', '5', '1'})
        self.assertEqual(set(terminals[parts['contactor_aux_1']]), {'13', '14'})
        if horizontal:
            self.assertEqual(elements[parts['relay_coil']].get('orientation'), '3')
            self.assertEqual(elements[parts['relay_coil']].get('x'), '900')
        if not horizontal:
            for part in ('relay_coil', 'contactor_coil'):
                fields = {n.findtext('info_name'): n for n in elements[parts[part]].findall('./dynamic_texts/dynamic_elmt_text')}
                self.assertLess(float(fields['label'].get('y')), float(fields['manufacturer_reference'].get('y')))
                self.assertLess(float(fields['manufacturer_reference'].get('y')), float(fields['comment'].get('y')))
                self.assertGreaterEqual(float(fields['label'].get('text_height')), 50)
        if horizontal:
            for uid in parts.values():
                fields = {n.findtext('info_name'): n for n in elements[uid].findall('./dynamic_texts/dynamic_elmt_text')}
                label, model = fields['label'], fields['manufacturer_reference']
                self.assertEqual(label.get('y'), model.get('y'))
                self.assertLess(float(model.get('x')), float(label.get('x')))
                if 'comment' in fields:
                    self.assertEqual(fields['comment'].get('text_from'), 'ElementInfo')
                    self.assertLess(float(fields['comment'].get('x')), float(model.get('x')))
        wires = []
        for conductor in root.findall('./diagram/conductors/conductor'):
            endpoints = [(conductor.get('element' + n), conductor.get('terminal' + n)) for n in ('1', '2')]
            for uid, terminal in endpoints:
                self.assertIn(terminal, terminals[uid].values())
            wires.append(tuple(endpoints))
        def pin(part, name):
            uid = parts[part]
            return uid, terminals[uid][name]

        # 実際の生成配線をたどる理想接点の導通検査。実機・時間応答のシミュレーションではない。
        def step(start, stop, state):
            k1, km1 = state
            for _ in range(4):
                graph = {}
                def join(a, b):
                    graph.setdefault(a, set()).add(b)
                    graph.setdefault(b, set()).add(a)
                for a, b in wires:
                    join(a, b)
                for uid, element in elements.items():
                    if element.get('type').endswith(('junction.elmt', 'node.elmt')):
                        pins = list(terminals[uid].values())
                        for terminal in pins[1:]:
                            join((uid, pins[0]), (uid, terminal))
                for part, a, b, closed in [('start_pushbutton', '3', '4', start), ('stop_nc', '1', '2', not stop),
                        ('relay_contact_1', '9', '5', k1), ('relay_contact_2', '12', '8', k1),
                        ('contactor_aux_1', '13', '14', km1)]:
                    if closed:
                        join(pin(part, a), pin(part, b))
                def reachable(source, target):
                    seen, todo = set(), [source]
                    while todo:
                        current = todo.pop()
                        if current == target:
                            return True
                        if current not in seen:
                            seen.add(current)
                            todo.extend(graph.get(current, ()))
                    return False
                positive, negative = pin('stop_nc', '1'), pin('relay_coil', '14')
                self.assertFalse(reachable(positive, negative))
                powered = lambda part, a, b: reachable(positive, pin(part, a)) and reachable(negative, pin(part, b))
                next_state = powered('relay_coil', '13', '14'), powered('contactor_coil', 'A1', 'A2')
                if next_state == (k1, km1):
                    return next_state, powered('lamp_lamp', 'X1', 'X2')
                k1, km1 = next_state
            self.fail('接点状態が収束しません')

        state = (False, False)
        for start, stop, expected in [(False, False, False), (True, False, True), (False, False, True),
                                       (False, True, False), (False, False, False), (True, True, False)]:
            state, lamp = step(start, stop, state)
            self.assertEqual((state, lamp), ((expected, expected), expected))


if __name__ == '__main__':
    unittest.main()
