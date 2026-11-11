import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from pypdf import PdfReader, PdfWriter
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
        self.source.write_text('<project><diagram/></project>', encoding='utf-8')
        self.output = self.folder / 'drawing.pdf'
        self.output.write_bytes(b'previous PDF')
        self.enterContext(patch.object(pdf_export, 'find_qet', return_value='qelectrotech'))
        self.run = self.enterContext(patch.object(pdf_export.subprocess, 'run', side_effect=self.native))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def native(self, args, **kwargs):
        self.assertEqual(args[1], '--export-pdf')
        self.assertNotEqual(Path(args[3]), self.output)
        self.assertEqual(self.output.read_bytes(), b'previous PDF')
        self.assertTrue(Path(kwargs['env']['QET_SETTINGS_DIR']).is_dir())
        writer = PdfWriter()
        writer.add_blank_page(width=946, height=653)
        with open(args[3], 'wb') as handle:
            writer.write(handle)
        return subprocess.CompletedProcess(args, 0, '', '')

    def assert_preserved(self):
        self.assertEqual(self.output.read_bytes(), b'previous PDF')
        self.assertEqual(list(self.folder.glob('qet_pdf_*')), [])

    def test_native_output_replaced_only_after_a3_conversion(self):
        pdf_export.export(self.source, self.output)
        with self.output.open('rb') as handle:
            pages = PdfReader(handle).pages
            self.assertEqual(len(pages), 1)
            self.assertAlmostEqual(float(pages[0].mediabox.width), 1190.55)
            self.assertAlmostEqual(float(pages[0].mediabox.height), 841.89)
        self.assertEqual(list(self.folder.glob('qet_pdf_*')), [])

    def test_native_failure_timeout_and_missing_file_keep_existing_pdf(self):
        for failure in (OSError('not found'), subprocess.TimeoutExpired('QET', 1)):
            with self.subTest(failure=failure):
                self.run.side_effect = failure
                with self.assertRaises(type(failure)):
                    pdf_export.export(self.source, self.output)
                self.assert_preserved()
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 2, '', 'unsupported option')
        with self.assertRaisesRegex(RuntimeError, 'unsupported option'):
            pdf_export.export(self.source, self.output)
        self.assert_preserved()

    def test_page_mismatch_keeps_existing_pdf(self):
        self.source.write_text('<project><diagram/><diagram/></project>', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'PDF 1'):
            pdf_export.export(self.source, self.output)
        self.assert_preserved()

    def test_conversion_failure_keeps_existing_pdf(self):
        with patch.object(pdf_export, 'to_a3', side_effect=ValueError('invalid PDF')):
            with self.assertRaisesRegex(ValueError, 'invalid PDF'):
                pdf_export.export(self.source, self.output)
        self.assert_preserved()

    def test_requested_qet_path_is_not_silently_replaced_by_auto_detection(self):
        with patch.object(pdf_export, 'find_qet', self.find_qet), patch.object(pdf_export.shutil, 'which', return_value=None):
            with self.assertRaises(FileNotFoundError):
                pdf_export.find_qet('missing-explicit-qet')

    find_qet = staticmethod(pdf_export.find_qet if pdf_export else lambda: None)

    def test_catalog_failure_keeps_existing_manufacturer_pdf(self):
        from tools import catalog_qet
        destination = self.folder / 'keyence.pdf'
        destination.write_bytes(b'catalog old')
        with patch.object(catalog_qet, 'manufacturers', return_value={'keyence': {'unit_diagram': {'KV': {}}}}), \
             patch.object(catalog_qet, 'build_category', return_value=self.source), \
             patch.object(pdf_export, 'export', side_effect=RuntimeError('export failed')):
            with self.assertRaisesRegex(RuntimeError, 'export failed'):
                pdf_export.export_catalog('keyence', self.folder)
        self.assertEqual(destination.read_bytes(), b'catalog old')
        self.assertEqual(list(self.folder.glob('qet_catalog_*')), [])


if __name__ == '__main__':
    unittest.main()
