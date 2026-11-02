import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from tools import regenerate_hub_power_samples as samples


class RegenerateHubPowerSamplesTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.path = self.folder / 'hub.qet'
        self.enterContext(patch.dict(samples.SAMPLES, {'hub': (1, 1)}))
        root = ET.Element('project', title='指定の案件')
        props = ET.SubElement(root, 'properties')
        ET.SubElement(props, 'property', name='saveddate').text = '20261028'
        category = ET.SubElement(ET.SubElement(ET.SubElement(root, 'collection'), 'category'), 'category')
        entry = ET.SubElement(category, 'element', name='hub0.elmt')
        spec = samples.records('hub')['IESH-MB205G-R']
        definition = samples.hub_definition('IESH-MB205G-R', spec)
        definition.find('./description/rect').set('width', '261')
        entry.append(definition)
        page = ET.SubElement(root, 'diagram', cols='20', colsize='62', rows='10', rowsize='80',
                             title='指定のページ', date='20261028')
        element = ET.SubElement(ET.SubElement(page, 'elements'), 'element',
                                type='embed://import/plc_io/hub0.elmt', uuid='{keep-me}', x='220', y='52')
        infos = ET.SubElement(element, 'elementInformations')
        ET.SubElement(infos, 'elementInformation', name='label').text = 'HUB-設備A'
        ET.SubElement(infos, 'elementInformation', name='auxiliary1').text = '7'
        dynamic = ET.SubElement(element, 'dynamic_texts')
        ET.SubElement(dynamic, 'dynamic_elmt_text', y='999')
        ET.ElementTree(root).write(self.path, encoding='utf-8', xml_declaration=True)
        self.before = self.path.read_bytes()

    def test_refreshes_parts_and_preserves_layout_tags_and_project_date(self):
        before = ET.fromstring(self.before)
        result = samples.regenerate(self.path, 'hub')
        self.assertEqual(result['status'], 'ok', result['error'])
        after = ET.parse(self.path).getroot()
        self.assertEqual(samples.layout(before), samples.layout(after))
        self.assertEqual(after.get('title'), '指定の案件')
        self.assertEqual(after.find('./properties/property').text, '20261028')
        self.assertEqual(after.find('./collection/category/category/element/definition/description/rect').get('width'), '260')
        texts = after.findall('./diagram/elements/element/dynamic_texts/dynamic_elmt_text')
        self.assertTrue(texts)
        self.assertFalse(any(item.get('y') == '999' for item in texts))
        for item in texts:
            if item.findtext('info_name') in ('label', 'auxiliary1'):
                self.assertEqual(item.get('Halignment'), 'AlignHCenter')
        self.assertEqual(result['before_pages'], result['after_pages'])
        self.assertEqual(result['updated_paths'], [str(self.path.resolve())])

    def test_generation_failure_keeps_existing_qet(self):
        with patch.object(samples, 'hub_definition', side_effect=ValueError('invalid part')):
            result = samples.regenerate(self.path, 'hub')
        self.assertEqual(result['status'], 'error')
        self.assertIn('invalid part', result['error'])
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertFalse(list(self.folder.glob('*.tmp')))

    def test_replace_failure_keeps_existing_qet_and_removes_temporary(self):
        with patch.object(samples.os, 'replace', side_effect=OSError('cannot replace')):
            result = samples.regenerate(self.path, 'hub')
        self.assertEqual(result['status'], 'error')
        self.assertIn('cannot replace', result['error'])
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertFalse(list(self.folder.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
