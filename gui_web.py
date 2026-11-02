"""PLC・GOT 図面生成の画面(pywebview 版)。

  python gui_web.py            アプリの窓で開く(pip install pywebview が必要)
  python gui_web.py --browser  ブラウザで開く(pywebview なしで確認するとき)
"""
import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from webgui.api import Api  # noqa: E402

TITLE = 'PLC・GOT 図面生成'


class Dialogs:
    """pywebview のファイル選択。"""

    def __init__(self, webview):
        self.webview = webview
        self.window = None
        dialog = getattr(webview, 'FileDialog', None)
        self.kinds = ((dialog.OPEN, dialog.SAVE, dialog.FOLDER) if dialog else
                      (webview.OPEN_DIALOG, webview.SAVE_DIALOG, webview.FOLDER_DIALOG))

    @staticmethod
    def _first(result):
        if not result:
            return ''
        return result if isinstance(result, str) else result[0]

    def open_file(self, title, types, folder):
        return self._first(self.window.create_file_dialog(self.kinds[0], directory=folder, file_types=tuple(types)))

    def save_file(self, title, name, types, folder):
        return self._first(self.window.create_file_dialog(self.kinds[1], directory=folder, save_filename=name, file_types=tuple(types)))

    def folder(self, title, folder):
        return self._first(self.window.create_file_dialog(self.kinds[2], directory=folder))


def run_browser(port):
    from webgui.server import make_server
    server = make_server(Api(), port)
    url = f'http://127.0.0.1:{server.server_address[1]}/'
    print(TITLE, url, '(Ctrl+C で終了)')
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def run_window():
    try:
        import webview
    except ImportError:
        print('pywebview がありません。次のコマンドで入れてください:\n  python -m pip install pywebview')
        return 1
    dialogs = Dialogs(webview)
    api = Api(dialogs)
    window = webview.create_window(TITLE, str(ROOT / 'webgui' / 'static' / 'index.html'), js_api=api,
                                   width=1440, height=920, min_size=(1100, 700))
    dialogs.window = window

    def closing():
        if api.is_dirty().get('dirty'):
            return window.create_confirmation_dialog('確認', '保存していない変更を破棄して閉じますか？')
        return True

    window.events.closing += closing
    webview.start()
    return 0


def main():
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument('--browser', action='store_true', help='ブラウザで開く')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    if args.browser:
        run_browser(args.port)
        return 0
    return run_window()


if __name__ == '__main__':
    sys.exit(main())
