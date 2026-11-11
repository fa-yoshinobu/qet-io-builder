"""QETが書き出したPDF(A4横)をA3横に拡大し、上下左右の余白が同じになるよう中央に置く。
使い方: python tools/pdf_to_a3.py [--drawing 1260x870] pdf/*.pdf   (ファイルを上書き。pypdf が必要)
図面の範囲は Ghostscript で測る。Ghostscript がなければ --drawing(図面の幅x高さ)から計算する
(QET の書き出しは 10mm の余白で図面を左上に寄せて縮小するので、図面の大きさから位置が決まる)。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import math
import re, shutil, subprocess
from pypdf import PdfReader, PdfWriter, Transformation
A3 = (1190.55, 841.89)
MIN_MARGIN = 28.35   # 10mm
QET_MARGIN = 28.35   # QET の PDF 書き出しの余白(10mm)


def gs_bboxes(path):
    executable = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if not executable:
        return None
    r = subprocess.run([executable, "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=bbox", path],
                       capture_output=True, text=True, check=True)
    return [tuple(map(float, m)) for m in re.findall(r"%%HiResBoundingBox: (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", r.stderr)]


def calc_bbox(page, drawing):
    """QET の書き出し位置を図面の大きさ(幅, 高さ)から計算する: 余白 10mm で左上に寄せて縮小"""
    W, H = float(page.mediabox.width), float(page.mediabox.height)
    dw, dh = drawing
    s = min((W - 2 * QET_MARGIN) / dw, (H - 2 * QET_MARGIN) / dh)
    return (QET_MARGIN, H - QET_MARGIN - s * dh, QET_MARGIN + s * dw, H - QET_MARGIN)


def to_a3(path, drawing=None, *, native=False):
    rd = PdfReader(path); wr = PdfWriter()
    # native --export-pdfは図枠をMediaBoxへ直接出す（旧GUI出力の10mm余白はない）。
    bb = [tuple(map(float, p.mediabox)) for p in rd.pages] if native else gs_bboxes(path)
    if bb is None:
        if not drawing:
            raise SystemExit("Ghostscript が見つかりません。--drawing 幅x高さ を指定してください(例 --drawing 1260x870)")
        bb = [calc_bbox(p, drawing) for p in rd.pages]
    if len(bb) != len(rd.pages):
        raise SystemExit(f"PDF の余白を全ページで測定できません: {path}")
    for page, (x0, y0, x1, y1) in zip(rd.pages, bb):
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            raise ValueError("PDFの図面サイズが不正です")
        s = (A3[0] - A3[1]) / (w - h) if w > h else 0      # 上下左右の余白が同じになる倍率
        if s <= 0 or (A3[1] - s * h) / 2 < MIN_MARGIN:     # 余白が狭すぎるときは最小余白で収める
            s = min((A3[0] - 2 * MIN_MARGIN) / w, (A3[1] - 2 * MIN_MARGIN) / h)
        tx = A3[0] / 2 - s * (x0 + x1) / 2
        ty = A3[1] / 2 - s * (y0 + y1) / 2
        page.add_transformation(Transformation().scale(s, s).translate(tx, ty))
        page.mediabox.lower_left = (0, 0); page.mediabox.upper_right = A3
        page.cropbox.lower_left = (0, 0); page.cropbox.upper_right = A3
        wr.add_page(page)
    with open(path, "wb") as f:
        wr.write(f)
    print(path, len(rd.pages), "pages")


def drawing_size(value):
    try:
        dimensions = tuple(float(v) for v in value.lower().split('x'))
        if len(dimensions) == 2 and all(math.isfinite(v) and v > 0 for v in dimensions):
            return dimensions
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('図面サイズは正の幅x高さで指定してください（例: 1260x870）')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drawing', type=drawing_size, metavar='幅x高さ', help='Ghostscript がない場合に使用する図面サイズ')
    parser.add_argument('pdf', nargs='+', help='A3 横へ調整する PDF（上書き）')
    args = parser.parse_args(argv)
    for path in args.pdf:
        to_a3(path, args.drawing)


if __name__ == '__main__':
    main()
