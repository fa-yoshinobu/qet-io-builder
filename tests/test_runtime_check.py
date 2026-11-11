import os
import subprocess
import sys
import unittest
from pathlib import Path


class RuntimeCheckTest(unittest.TestCase):
    def test_unsupported_python_stops_before_gui_and_tomllib_imports(self):
        root = Path(__file__).resolve().parents[1]
        for entry in ('gui_web.py', 'gen_io_page.py'):
            with self.subTest(entry=entry):
                command = ('import runpy, sys; sys.version_info = (3, 10, 0); '
                           f'runpy.run_path({entry!r}, run_name="__main__")')
                result = subprocess.run([sys.executable, '-c', command], cwd=root,
                                        capture_output=True, encoding='utf-8',
                                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Python 3.11以上が必要', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
