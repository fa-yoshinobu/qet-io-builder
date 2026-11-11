from tests.qet_support import requires_qet
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from tools.make_control_sample import make
from tools.update_xrefs import OWNER, definitions, infos, location, update, update_file


class UpdateXrefsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'sample.qet'
        self.root = ET.parse(make(self.path)).getroot()

    def parts(self):
        return {e.get('type').split('/')[-1][:-5]: e for e in self.root.findall('./diagram/elements/element')
                if OWNER not in infos(e)}

    def tables(self):
        return {infos(e)[OWNER]: e for e in self.root.findall('./diagram/elements/element') if OWNER in infos(e)}

    def table_texts(self, master):
        table = self.tables()[master.get('uuid')]
        return [t.get('text') for t in definitions(self.root)[table.get('type')].findall('./description/text')]

    @requires_qet
    def test_real_poles_and_unused_changeover_side(self):
        before_wires = ET.tostring(self.root.find('./diagram/conductors'))
        positions = {e.get('uuid'): (e.get('x'), e.get('y')) for e in self.parts().values()}
        self.assertEqual(update(self.root), 2)
        relay = self.parts()['relay_coil']
        text = self.table_texts(relay)
        self.assertEqual(text[0], 'a')
        self.assertIn('1-E6', text)
        self.assertIn('1-C11', text)
        self.assertEqual(text[-3:], ['b', '', ''])
        self.assertEqual(before_wires, ET.tostring(self.root.find('./diagram/conductors')))
        self.assertEqual(positions, {e.get('uuid'): (e.get('x'), e.get('y')) for e in self.parts().values()})
        self.assertEqual(len(relay.findall('./links_uuids/link_uuid')), 2)
        labels = [t for t in relay.findall('./dynamic_texts/dynamic_elmt_text') if t.get('uuid') in infos(relay)['qet_io_xref_labels']]
        self.assertTrue(labels)
        self.assertTrue(all(t.get('text_from') == 'UserText' and t.findtext('text') == 'K1' for t in labels))

    @requires_qet
    def test_move_rename_reorder_and_repeat_preserve_manual_table_position(self):
        parts = self.parts()
        update(self.root)
        relay = parts['relay_coil']
        table = self.tables()[relay.get('uuid')]
        table_uid = table.get('uuid')
        table.set('x', str(float(table.get('x')) + 30))
        old_x = float(table.get('x'))
        relay.set('x', str(float(relay.get('x')) + 50))
        relay.find("./elementInformations/elementInformation[@name='label']").text = 'K99'
        parts['relay_contact_1'].set('x', '800')
        second = ET.SubElement(self.root, 'diagram', order='0', cols='20', colsize='62', rows='10', rowsize='80')
        ET.SubElement(second, 'elements')
        self.root.find('diagram').set('order', '1')
        update(self.root)
        table = self.tables()[relay.get('uuid')]
        self.assertEqual(table.get('uuid'), table_uid)
        self.assertEqual(float(table.get('x')), old_x + 50)
        self.assertIn('2-E13', self.table_texts(relay))
        self.assertIn('K99', [t.findtext('text') for t in relay.findall('./dynamic_texts/dynamic_elmt_text')])
        update(self.root)
        self.assertEqual(len(self.tables()), 2)
        self.assertEqual(float(self.tables()[relay.get('uuid')].get('x')), old_x + 50)

    @requires_qet
    def test_b_contact_and_deleted_contact_clear_only_managed_entries(self):
        parts = self.parts()
        first = parts['relay_contact_1']
        definition = definitions(self.root)[first.get('type')]
        pins = {t.get('name'): t.get('uuid') for t in definition.findall('./description/terminal')}
        for conductor in self.root.findall('./diagram/conductors/conductor'):
            for n in ('1', '2'):
                if conductor.get('element' + n) == first.get('uuid') and conductor.get('terminal' + n) == pins['5']:
                    conductor.set('terminal' + n, pins['1'])
        update(self.root)
        self.assertEqual(self.table_texts(parts['relay_coil'])[-3:], ['b', '1-E6', ''])
        page = self.root.find('diagram')
        page.find('elements').remove(first)
        relay = parts['relay_coil']
        for link in list(relay.find('links_uuids')):
            if link.get('uuid') == first.get('uuid'):
                relay.find('links_uuids').remove(link)
        update(self.root)
        self.assertEqual(self.table_texts(relay)[-3:], ['b', '', ''])

    @requires_qet
    def test_out_of_range_or_broken_link_does_not_replace_output(self):
        self.parts()['relay_contact_1'].set('x', '-1')
        ET.ElementTree(self.root).write(self.path, encoding='utf-8')
        output = self.path.with_name('output.qet')
        output.write_text('keep', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '範囲外'):
            update_file(self.path, output)
        self.assertEqual(output.read_text(), 'keep')
        self.parts()['relay_contact_1'].set('x', '350')
        self.parts()['relay_coil'].find('./links_uuids/link_uuid').set('uuid', '{missing}')
        with self.assertRaisesRegex(ValueError, '関連付け先'):
            update(self.root)

    @requires_qet
    def test_in_place_backup_and_removed_coil(self):
        before = self.path.read_bytes()
        update_file(self.path, self.path)
        self.assertEqual(self.path.with_suffix('.qet.bak').read_bytes(), before)
        self.root = ET.parse(self.path).getroot()
        parts = self.parts()
        relay = parts['relay_coil']
        self.root.find('./diagram/elements').remove(relay)
        for contact in (parts['relay_contact_1'], parts['relay_contact_2']):
            contact.remove(contact.find('links_uuids'))
        update(self.root)
        self.assertEqual(len(self.tables()), 1)
        self.assertNotIn(relay.get('uuid'), self.tables())

    @requires_qet
    def test_link_across_pages_and_one_way_link(self):
        parts = self.parts()
        contact = parts['relay_contact_1']
        second = ET.SubElement(self.root, 'diagram', order='2', cols='20', colsize='62', rows='10', rowsize='80')
        holder = ET.SubElement(second, 'elements')
        self.root.find('./diagram/elements').remove(contact)
        holder.append(contact)
        contact.remove(contact.find('links_uuids'))
        update(self.root)
        self.assertIn('2-E6', self.table_texts(parts['relay_coil']))

    @requires_qet
    def test_horizontal_table_is_below_coil_and_keeps_rotation(self):
        self.root = ET.parse(make(self.path, horizontal_coils=True)).getroot()
        relay = self.parts()['relay_coil']
        update(self.root)
        table = self.tables()[relay.get('uuid')]
        self.assertEqual(relay.get('orientation'), '3')
        self.assertEqual(float(table.get('x')), 382)
        self.assertEqual(float(table.get('y')), float(relay.get('y')) - 16)
        update(self.root)
        self.assertEqual(len(self.tables()), 2)

    @requires_qet
    def test_table_uses_compact_io_dimensions(self):
        update(self.root)
        relay = self.parts()['relay_coil']
        table = self.tables()[relay.get('uuid')]
        definition = definitions(self.root)[table.get('type')]
        rect = definition.find('./description/rect')
        self.assertEqual(float(rect.get('width')), 62)
        self.assertEqual(float(rect.get('height')), 24)


class UnrelatedDocumentTest(unittest.TestCase):
    def test_unrelated_document_is_unchanged(self):
        root = ET.fromstring('<project><diagram order="0"><elements/></diagram></project>')
        before = ET.tostring(root)
        self.assertEqual(update(root), 0)
        self.assertEqual(ET.tostring(root), before)


if __name__ == '__main__':
    unittest.main()
