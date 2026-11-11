import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webgui.api import Api


class WebGuiSafetyTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.path = self.folder / 'project.json'
        self.path.write_text('{"pages": [], "project_title": "saved"}', encoding='utf-8')
        self.api = Api()
        self.assertNotIn('error', self.api.open_project(str(self.path)))
        self.api.set_project({'project_title': '未保存の題名'})

    def test_encoding_failure_preserves_existing_project_and_unsaved_state(self):
        original = self.path.read_bytes()
        self.api._data['vendor_note'] = '\ud800'
        before = copy.deepcopy(self.api._data)
        self.assertIn('error', self.api.save())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.api._data, before)
        self.assertTrue(self.api.is_dirty()['dirty'])
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_replace_failure_preserves_project_path_and_removes_temporary_file(self):
        original = self.path.read_bytes()
        before = copy.deepcopy(self.api._data)
        for save_as in (False, True):
            with self.subTest(save_as=save_as), patch('webgui.api.os.replace', side_effect=PermissionError('locked')):
                result = self.api.save_as(str(self.folder / 'copy.json')) if save_as else self.api.save()
            self.assertIn('error', result)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(self.api._path, self.path)
            self.assertEqual(self.api._data, before)
            self.assertTrue(self.api.is_dirty()['dirty'])
            self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_invalid_open_preserves_unsaved_project_and_history(self):
        candidate = self.folder / 'bad.json'
        before = copy.deepcopy((self.api._data, self.api._undo, self.api._redo,
                                self.api._saved_data, self.api._index))
        cases = ['{invalid'] + [json.dumps(value) for value in (
            [], {'pages': [] , 'power': None}, {'pages': [], 'power': []},
            {'pages': [], 'power': '24V'}, {'pages': [], 'front_pages': 'invalid'},
            {'pages': [], 'project_title': []}, {'pages': [{'kind': []}]},
            {'pages': [], 'project_title': '\ud800'},
            {'pages': [{'kind': 'fx5body', 'tag': '\ud800'}]},
        )]
        for text in cases:
            with self.subTest(text=text):
                candidate.write_text(text, encoding='utf-8')
                self.assertIn('error', self.api.open_project(str(candidate)))
                self.assertEqual(self.api._path, self.path)
                self.assertEqual((self.api._data, self.api._undo, self.api._redo,
                                  self.api._saved_data, self.api._index), before)
                self.assertTrue(self.api.is_dirty()['dirty'])
                self.assertEqual(candidate.read_text(encoding='utf-8'), text)
