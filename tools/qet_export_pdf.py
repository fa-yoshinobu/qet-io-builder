"""QElectroTech の画面を自動で操作して .qet を PDF に書き出し、A3 横にそろえる(Windows 専用)。
QET にはコマンドラインの書き出し機能がないため、画面操作(UI オートメーション)で「PDFにエクスポート」を行う。

使い方: python tools/qet_export_pdf.py 図面.qet [出力.pdf]
  出力を省略すると .qet と同じ場所・同じ名前の .pdf。実行中の数十秒は QET が画面に出るので操作しないこと。
  書き出した図面は QET に開いたまま残す。
必要: pywinauto・pypdf(PDF出力.bat が足りなければ入れる)。QET は既定の場所か、環境変数 QET_EXE で指定。
"""
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pdf_to_a3 import to_a3   # noqa: E402

QET_CANDIDATES = [
    os.environ.get("QET_EXE", ""),
    r"C:\Program Files\QElectroTech\bin\qelectrotech.exe",
    r"C:\Program Files (x86)\QElectroTech\bin\qelectrotech.exe",
]


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def drawing_size(qet_path):
    """図面の幅・高さ(区画帯 + 図枠 + 表題欄)。A3 化で図面の位置を計算するのに使う"""
    root = ET.parse(qet_path).getroot()
    d = root.find("diagram")
    w = int(d.get("cols")) * float(d.get("colsize")) + 20
    h = int(d.get("rows")) * float(d.get("rowsize")) + 20
    grid = root.find(".//titleblocktemplate//grid")
    if grid is not None:
        h += sum(float(v) for v in grid.get("rows", "").split(";") if v.strip())
    return w, h


def wait(cond, timeout, step=0.3, what=""):
    end = time.time() + timeout
    while time.time() < end:
        r = cond()
        if r:
            return r
        time.sleep(step)
    raise SystemExit(f"時間切れ: {what}")


def find(desktop, **kw):
    try:
        w = desktop.window(**kw)
        return w if w.exists(timeout=0) else None
    except Exception:
        return None


def _export_pdf(qet_path, pdf_path):
    from pywinauto import Desktop
    from pywinauto.keyboard import send_keys

    exe = next((p for p in QET_CANDIDATES if p and os.path.exists(p)), None)
    if not exe:
        raise SystemExit("qelectrotech.exe が見つかりません。環境変数 QET_EXE に場所を指定してください。")
    desk = Desktop(backend="uia")
    name = os.path.basename(qet_path)

    log("QET を起動")
    subprocess.Popen([exe, qet_path])
    # 「バックアップを作成しますか?」が出たら いいえ。メイン画面にファイル名が出たら開けた
    def opened():
        for w in desk.windows():
            t = w.window_text()
            window = desk.window(handle=w.handle)
            btn = find(window, title_re="いいえ.*|No", control_type="Button") if "QElectroTech" not in t else None
            if btn:
                btn.click_input()
            if "QElectroTech" in t and name in t:
                return window
        return None
    main = wait(opened, 60, what="図面を開く")
    main.set_focus()
    time.sleep(2)

    log("ファイル > PDFにエクスポート")
    main.child_window(title_re="ファイル.*|File.*", control_type="MenuItem").click_input()
    item = wait(lambda: find(desk, title_re=".*PDF.*", control_type="MenuItem") or
                next((m for w in desk.windows() for m in w.descendants(control_type="MenuItem")
                      if "PDF" in m.window_text()), None), 10, what="PDF のメニュー")
    item.click_input()

    # 書き出しの確認画面(ページ一覧と「PDF にエクスポート」ボタン)
    def export_button():
        dialog = find(desk, process=main.process_id(),
                      auto_id="SingleApplication.ProjectPrintWindow", control_type="Window", top_level_only=False)
        if dialog:
            return find(dialog, auto_id="SingleApplication.ProjectPrintWindow.centralwidget.m_button_box.QPushButton",
                        title_re=".*PDF.*", control_type="Button")
        return None
    wait(export_button, 20, what="書き出し画面").click_input()

    # 保存先を入れる(Windows のファイル保存画面)
    def save_dialog():
        for w in desk.windows():
            if w.process_id() != main.process_id():
                continue
            window = desk.window(handle=w.handle)
            edit = find(window, auto_id="1001", control_type="Edit")
            if edit:
                return window, edit
        return None
    dlg, edit = wait(save_dialog, 20, what="保存画面")
    edit.set_edit_text(pdf_path)
    time.sleep(0.5)
    save = find(dlg, auto_id="1", control_type="Button")
    (save.click_input() if save else send_keys("{ENTER}"))

    log("書き出し中")
    last = [-1]
    def written():
        if not os.path.exists(pdf_path):
            return False
        size = os.path.getsize(pdf_path)
        done = size > 0 and size == last[0]
        last[0] = size
        return done
    wait(written, 120, step=1.0, what="PDF の書き出し")


def export(qet_path, pdf_path):
    pdf_path = os.path.abspath(pdf_path)
    with tempfile.TemporaryDirectory(dir=os.path.dirname(pdf_path), prefix="qet_pdf_") as folder:
        temporary = os.path.join(folder, "export.pdf")
        _export_pdf(qet_path, temporary)
        log("A3 横にそろえる")
        to_a3(temporary, drawing_size(qet_path))
        os.replace(temporary, pdf_path)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    qet = os.path.abspath(sys.argv[1])
    pdf = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.splitext(qet)[0] + ".pdf"
    export(qet, pdf)
    log(f"完了: {pdf}")


if __name__ == "__main__":
    main()
