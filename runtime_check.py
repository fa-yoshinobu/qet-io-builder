"""依存モジュールを読み込む前のPythonバージョン確認。"""
import sys


def require_python():
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11以上が必要です。新しいPythonで起動してください。')


if __name__ == '__main__':
    require_python()
