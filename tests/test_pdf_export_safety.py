import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from tools import qet_export_pdf as pdf_export
except ModuleNotFoundError as error:
    if error.name != 'pypdf':
        raise
    pdf_export = None


@unittest.skipIf(pdf_export is None, 'PDF出力用のpypdfが未インストール')
class PdfExportSafetyTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.source = self.folder / 'drawing.qet'
        self.source.write_text('<project><diagram cols="20" colsize="62" rows="10" rowsize="80"/></project>', encoding='utf-8')
        self.output = self.folder / 'drawing.pdf'
        self.output.write_bytes(b'previous PDF')
        self.exe = self.folder / 'qelectrotech.exe'
        self.exe.touch()
        self.ui = MagicMock()
        pywinauto = types.ModuleType('pywinauto')
        pywinauto.Desktop = MagicMock(return_value=self.ui)
        keyboard = types.ModuleType('pywinauto.keyboard')
        keyboard.send_keys = MagicMock()
        self.enterContext(patch.dict(sys.modules, {'pywinauto': pywinauto, 'pywinauto.keyboard': keyboard}))
        self.enterContext(patch.object(pdf_export, 'QET_CANDIDATES', [str(self.exe)]))
        self.enterContext(patch.object(pdf_export.time, 'sleep'))
        self.real_find, self.real_wait = pdf_export.find, pdf_export.wait
        self.enterContext(patch.object(pdf_export, 'find', return_value=self.ui))
        self.enterContext(patch.object(pdf_export, 'wait', side_effect=self.wait))
        self.launch = self.enterContext(patch.object(pdf_export.subprocess, 'Popen'))
        self.run = self.enterContext(patch.object(pdf_export.subprocess, 'run'))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def wait(self, condition, timeout, step=0.3, what=''):
        if what == '保存画面':
            return self.ui, self.ui
        if what == 'PDF の書き出し':
            temporary = Path(self.ui.set_edit_text.call_args.args[0])
            self.assertNotEqual(temporary, self.output)
            self.assertEqual(self.output.read_bytes(), b'previous PDF')
            temporary.write_bytes(b'new PDF')
            self.assertFalse(condition())
            self.assertTrue(condition())
        return self.ui

    def assert_cleaned(self):
        self.assertEqual(list(self.folder.glob('qet_pdf_*')), [])
        self.run.assert_not_called()

    def test_replaces_pdf_only_after_conversion_and_leaves_qet_open(self):
        def convert(path, drawing):
            self.assertEqual(self.output.read_bytes(), b'previous PDF')
            self.assertEqual(drawing, (1260, 820))
            Path(path).write_bytes(b'A3 PDF')

        with patch.object(pdf_export, 'to_a3', side_effect=convert) as conversion:
            pdf_export.export(str(self.source), str(self.output))
        self.assertEqual(self.output.read_bytes(), b'A3 PDF')
        conversion.assert_called_once()
        self.assert_cleaned()

    def test_start_failure_keeps_existing_pdf(self):
        self.launch.side_effect = OSError('QET could not start')
        with patch.object(pdf_export, 'to_a3') as conversion:
            with self.assertRaisesRegex(OSError, 'could not start'):
                pdf_export.export(str(self.source), str(self.output))
        self.assertEqual(self.output.read_bytes(), b'previous PDF')
        conversion.assert_not_called()
        self.assert_cleaned()

    def test_conversion_failure_keeps_existing_pdf(self):
        with patch.object(pdf_export, 'to_a3', side_effect=ValueError('invalid PDF')):
            with self.assertRaisesRegex(ValueError, 'invalid PDF'):
                pdf_export.export(str(self.source), str(self.output))
        self.assertEqual(self.output.read_bytes(), b'previous PDF')
        self.assert_cleaned()

    def test_ui_timeout_keeps_existing_pdf(self):
        pdf_export.wait.side_effect = SystemExit('UI timeout')
        with patch.object(pdf_export, 'to_a3') as conversion:
            with self.assertRaisesRegex(SystemExit, 'UI timeout'):
                pdf_export.export(str(self.source), str(self.output))
        self.assertEqual(self.output.read_bytes(), b'previous PDF')
        conversion.assert_not_called()
        self.assert_cleaned()

    def test_cli_keeps_default_and_explicit_output_paths(self):
        for args, output in (([str(self.source)], self.output),
                             ([str(self.source), str(self.folder / 'other.pdf')], self.folder / 'other.pdf')):
            with self.subTest(args=args), patch.object(sys, 'argv', ['qet_export_pdf.py', *args]), \
                    patch.object(pdf_export, 'export') as export, patch.object(pdf_export, 'to_a3') as conversion:
                pdf_export.main()
                export.assert_called_once_with(str(self.source), str(output))
                conversion.assert_not_called()

    def test_uses_window_specs_and_confirmation_dialog_not_toolbar(self):
        self.enterContext(patch.object(pdf_export, 'find', self.real_find))
        self.enterContext(patch.object(pdf_export, 'wait', self.real_wait))
        missing = MagicMock()
        missing.exists.return_value = False
        specs = [MagicMock() for _ in range(4)]
        main, unrelated, confirmation, save = specs
        wrappers = []
        for handle, process, title in ((1, 10, 'QElectroTech drawing.qet'),
                                       (2, 20, 'Other Save As'),
                                       (3, 10, 'Export'), (4, 10, 'Save As')):
            wrapper = MagicMock(spec=['handle', 'window_text', 'process_id', 'descendants'])
            wrapper.handle = handle
            wrapper.window_text.return_value = title
            wrapper.process_id.return_value = process
            wrappers.append(wrapper)
        main.process_id.return_value = 10
        self.ui.windows.return_value = wrappers
        toolbar = MagicMock()
        toolbar.window_text.return_value = 'PDF にエクスポート'
        toolbar.click_input.side_effect = AssertionError('toolbar must not be clicked')
        wrappers[0].descendants.return_value = [toolbar]
        menu, confirm_button, edit, save_button = (MagicMock() for _ in range(4))
        for spec in specs:
            spec.window.return_value = missing
        confirmation.window.side_effect = lambda **kw: (
            confirm_button if kw.get('auto_id') ==
            'SingleApplication.ProjectPrintWindow.centralwidget.m_button_box.QPushButton'
            and kw.get('title_re') == '.*PDF.*' else missing)
        save.window.side_effect = lambda **kw: {'1001': edit, '1': save_button}.get(kw.get('auto_id'), missing)

        def window(**kw):
            if 'handle' in kw:
                return specs[kw['handle'] - 1]
            if kw.get('auto_id') == 'SingleApplication.ProjectPrintWindow' and kw.get('process') == 10:
                self.assertFalse(kw['top_level_only'])
                return confirmation
            if kw.get('control_type') == 'MenuItem':
                return menu
            return missing

        self.ui.window.side_effect = window
        temporary = self.folder / 'native.pdf'
        save_button.click_input.side_effect = lambda: temporary.write_bytes(b'native PDF')
        pdf_export._export_pdf(str(self.source), str(temporary))
        main.child_window.assert_called_once()
        confirm_button.click_input.assert_called_once()
        toolbar.click_input.assert_not_called()
        unrelated.window.assert_not_called()
        edit.set_edit_text.assert_called_once_with(str(temporary))
        self.assertEqual(temporary.read_bytes(), b'native PDF')


if __name__ == '__main__':
    unittest.main()
