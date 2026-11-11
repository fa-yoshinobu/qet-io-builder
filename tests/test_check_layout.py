import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

from tools import check_layout, preview_qet


class LayoutCheckTest(unittest.TestCase):
    def test_preview_title_uses_outline_text_without_changing_hyphens(self):
        title = 'NX-HTC3510-5 高機能温度調節 (1/2)'
        root = ET.Element('project')
        ET.SubElement(root, 'diagram', title=title, cols='20', colsize='62',
                      rows='10', rowsize='80')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'title.qet'
            ET.ElementTree(root).write(path, encoding='utf-8')
            with patch.object(preview_qet, 'draw_text', wraps=preview_qet.draw_text) as draw:
                outputs = preview_qet.render(path, folder, s=0.8)
            self.assertEqual(len(outputs), 1)
            self.assertEqual(draw.call_args.args[3], title)
            self.assertEqual(draw.call_args.kwargs['s'], 0.8)

    def test_white_ellipse_hides_only_covered_line_segments(self):
        draw = check_layout.RecordingDraw(ImageDraw.Draw(Image.new('RGB', (100, 100))), (0, 0, 100, 100))
        draw.line([(0, 50), (100, 50)])
        draw.line([(50, 0), (50, 100)])
        draw.ellipse((40, 40, 60, 60), fill='white')
        self.assertEqual(set(draw.lines), {(0, 50, 40, 50), (60, 50, 100, 50),
                                           (50, 0, 50, 40), (50, 60, 50, 100)})

    def test_white_rectangle_preserves_exterior_lines_and_its_border(self):
        draw = check_layout.RecordingDraw(ImageDraw.Draw(Image.new('RGB', (100, 100))), (0, 0, 100, 100))
        draw.line([(0, 50), (100, 50)])
        draw.rectangle((40, 40, 60, 60), fill='white')
        self.assertIn((0, 50, 40, 50), draw.lines)
        self.assertIn((60, 50, 100, 50), draw.lines)
        self.assertIn((40, 40, 60, 40), draw.lines)
        draw.record_text('hidden line', (45, 45, 55, 55))
        self.assertEqual(draw.issues(), [])

    def test_records_text_overlap_frame_overflow_and_both_line_directions(self):
        draw = check_layout.RecordingDraw(ImageDraw.Draw(Image.new('RGB', (100, 100))), (0, 0, 100, 100))
        font = ImageFont.load_default()
        draw.text((20, 20), 'TEST', font=font)
        draw.text((21, 20), 'NEXT', font=font)
        draw.text((99, 20), 'OVERFLOW', font=font)
        _, (left, top, right, bottom) = draw.texts[0]
        draw.line([(left - 5, (top + bottom) / 2), (right + 5, (top + bottom) / 2)])
        draw.rectangle([(left + 2, top - 5), (right + 5, bottom + 5)])
        issues = draw.issues()
        self.assertEqual({issue.kind for issue in issues}, {'文字重なり', '枠外', '線横切り'})
        self.assertEqual(len([i for i in issues if i.kind == '線横切り' and i.text == 'TEST']), 2)

    def test_bounding_box_edges_are_allowed_to_touch(self):
        draw = check_layout.RecordingDraw(ImageDraw.Draw(Image.new('RGB', (100, 100))), (0, 0, 100, 100))
        draw.texts = [('A', (10, 10, 20, 20)), ('B', (20, 10, 30, 20))]
        draw.rectangle([(10, 10), (30, 20)])
        self.assertEqual(draw.issues(), [])

    def test_rotated_preview_bounds_are_checked(self):
        image = Image.new('RGB', (100, 100))
        draw = check_layout.RecordingDraw(ImageDraw.Draw(image), (0, 0, 100, 100))
        with patch.object(preview_qet, 'fnt', return_value=ImageFont.load_default()):
            preview_qet.draw_text(image, draw, (50, 50), 'ROTATED', 9,
                                  rotation=270, save_image=False)
        self.assertEqual(len(draw.texts), 1)
        _, (left, top, right, bottom) = draw.texts[0]
        self.assertGreater(bottom - top, right - left)
        draw.line([(left - 1, (top + bottom) / 2), (right + 1, (top + bottom) / 2)])
        self.assertTrue(any(issue.kind == '線横切り' for issue in draw.issues()))

    def test_cli_reports_problem_pages_and_checks_every_input(self):
        root = ET.Element('project')
        for number in range(2):
            page = ET.SubElement(root, 'diagram', cols='10', colsize='100', rows='5', rowsize='100', title=str(number))
            inputs = ET.SubElement(page, 'inputs')
            ET.SubElement(inputs, 'input', x='50', y='50', text='TEST')
            if number:
                ET.SubElement(inputs, 'input', x='50', y='50', text='CLASH')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'layout.qet'
            ET.ElementTree(root).write(path)
            output = io.StringIO()
            with patch.object(preview_qet, 'FONT', 'test'), patch.object(preview_qet, 'fnt', return_value=ImageFont.load_default()):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(check_layout.main([str(path), str(path)]), 1)
                self.assertEqual(len(output.getvalue().splitlines()), 2)
                self.assertIn('p.2', output.getvalue())
                root.remove(root[1])
                ET.ElementTree(root).write(path)
                self.assertEqual(check_layout.main([str(path)]), 0)


if __name__ == '__main__':
    unittest.main()
