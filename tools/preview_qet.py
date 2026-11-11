""".qet をおおまかに PNG にする確認用ツール(QET を開かずにレイアウトを見るため)。
QET の自動配線は L 字で近似し、表題欄は名称だけを描く。正式な確認は QET の「PDFにエクスポート」で行う。
使い方: python tools/preview_qet.py 図面.qet 出力フォルダ [ページ(例 1,2,5-7 / all)] [倍率(既定0.8)]
必要: Pillow。日本語フォントは Noto Sans CJK(Linux)か MS ゴシック(Windows)を使う。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import os, re, math
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
# QET の図面は MS ゴシック(等幅・半角0.5em)。文字幅をそろえるため等幅のゴシックを優先する
_CANDIDATES = [("C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/msgothic.ttc"),
               ("/usr/local/share/fonts/bizud/BIZUDGothic-Regular.ttf", "/usr/local/share/fonts/bizud/BIZUDGothic-Bold.ttf"),
               ("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"),
               ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")]
FONT, FONTB = next((a, b) for a, b in _CANDIDATES if os.path.exists(a)) if any(os.path.exists(a) for a, _ in _CANDIDATES) else ("", "")
_fc = {}
def fnt(pt, bold=False, s=1.0):
    px = max(1, round(math.floor(pt * 96 / 72 + .5) * s))
    k = (px, bold)
    if k not in _fc:
        try: _fc[k] = ImageFont.truetype(FONTB if bold else FONT, px, index=0)
        except Exception: _fc[k] = ImageFont.load_default()
    return _fc[k]


def draw_text(im, dr, origin, text, pt, bold=False, s=1.0, width=-1,
              align='', rotation=0, margin=4, save_image=True, baseline_anchor=False):
    """Qtと同じ整数pixelのfontを輪郭で描く。小サイズの埋込bitmapは行高が異なる。"""
    factor = 16
    font = fnt(pt, bold, factor)
    metrics = fnt(768, bold).getmetrics()  # 1024pxで丸め誤差を除く
    px = math.floor(pt * 96 / 72 + .5)
    ascent, descent = (v / 1024 * px for v in metrics)
    pitch = ascent + descent
    lines = wrap_lines(dr, text, font, (width - 2 * margin) * factor) if width > 0 else text.split('\n')
    angle = math.radians(rotation)
    co, si = math.cos(angle), math.sin(angle)
    def point(x, y):
        return origin[0] + (x * co - y * si) * s, origin[1] + (x * si + y * co) * s
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        advance = dr.textlength(line, font=font) / factor
        x = (width - advance) / 2 if align == 'AlignHCenter' and width > 0 else margin
        if align == 'AlignRight' and width > 0:
            x = width - margin - advance
        baseline = (0 if baseline_anchor else margin + ascent) + index * pitch
        box = font.getbbox(line, anchor='ls')
        left, top, right, bottom = (box[0] / factor + x, box[1] / factor + baseline,
                                    box[2] / factor + x, box[3] / factor + baseline)
        corners = [point(a, b) for a, b in ((left, top), (right, top), (right, bottom), (left, bottom))]
        bounds = (min(p[0] for p in corners), min(p[1] for p in corners),
                  max(p[0] for p in corners), max(p[1] for p in corners))
        if hasattr(dr, 'record_text'):
            dr.record_text(line, bounds)
        if save_image and box[2] > box[0] and box[3] > box[1]:
            layer = Image.new('RGBA', (box[2] - box[0], box[3] - box[1]))
            ImageDraw.Draw(layer).text((-box[0], -box[1]), line, font=font, anchor='ls', fill='black')
            layer = layer.resize((max(1, round(layer.width / factor * s)),
                                  max(1, round(layer.height / factor * s))), Image.Resampling.LANCZOS)
            if rotation % 360:
                layer = layer.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
            im.paste(layer, (round(bounds[0]), round(bounds[1])), layer)
def parse_font(f):
    p = (f or "x,9,-1,5,50").split(",")
    try: return float(p[1]), int(p[4]) >= 75
    except Exception: return 9, False
ROT = {0: (1, 0, 0, 1), 1: (0, -1, 1, 0), 2: (-1, 0, 0, -1), 3: (0, 1, -1, 0)}
def tr(o, x, y):
    a, b, c, d = ROT[o]; return a * x + b * y, c * x + d * y

def wrap_lines(dr, text, font, width, pt=None):
    """QET(Qt)の折返しに近づける: 空白で区切って欄の幅に収め、区切れない語はそのまま(はみ出す)。
    Qt は等幅フォントの文字送りを整数の画素に丸めるので、その分だけ広く測る"""
    if pt:
        half = pt * 96 / 72 / 2
        width = width / (math.ceil(half) / half)
    out = []
    for para in text.split("\n"):
        # Qt と同じく空白と「/」の後(数字の前を除く)で折り返す
        words, line = re.split(r"(?<=/)(?=\D)| ", para), ""
        seps = re.findall(r"(?<=/)(?=\D)| ", para)
        for i, w in enumerate(words):
            sep = seps[i - 1] if i else ""
            cand = (line + sep + w) if line else w
            if line and dr.textlength(cand, font=font) > width:
                out.append(line); line = w
            else:
                line = cand
        out.append(line)
    return out


def render(path, outdir, pages=None, s=1.0, *, draw_factory=None):
    root = ET.parse(path).getroot()
    defs = {}
    for el in root.iter("element"):
        if el.get("name") and el.find("definition") is not None:
            defs[el.get("name")] = el.find("definition")
    if outdir is not None:
        os.makedirs(outdir, exist_ok=True)
    outs = []
    for pi, dg in enumerate(root.findall("diagram"), 1):
        if pages and pi not in pages: continue
        cols, cs = int(dg.get("cols")), float(dg.get("colsize")); rows, rs = int(dg.get("rows")), float(dg.get("rowsize"))
        W, H = int((20 + cols * cs + 10) * s), int((20 + rows * rs + 60) * s)
        im = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(im)
        P = lambda x, y: (x * s, y * s)
        dr.rectangle([P(0, 0), P(20 + cols * cs, 20 + rows * rs + 50)], outline="black")
        dr.rectangle([P(20, 20), P(20 + cols * cs, 20 + rows * rs)], outline="black")
        for i in range(cols):
            x = 20 + i * cs; dr.line([P(x, 0), P(x, 20)], fill="black"); dr.text(P(x + cs / 2 - 4, 4), str(i + 1), fill="black", font=fnt(7, s=s))
        for i in range(rows):
            y = 20 + i * rs; dr.line([P(0, y), P(20, y)], fill="black"); dr.text(P(6, y + rs / 2 - 6), "ABCDEFGHIJ"[i], fill="black", font=fnt(7, s=s))
        dr.text(P(700, 20 + rows * rs + 10), dg.get("title", ""), fill="black", font=fnt(10, s=s))
        if draw_factory is not None:
            dr = draw_factory(dr, dg, pi)
        terms = {}
        for e in dg.find("elements") or []:
            name = e.get("type").split("/")[-1]; d = defs.get(name)
            ex, ey, o = float(e.get("x")), float(e.get("y")), int(e.get("orientation", "0"))
            if d is None:
                if draw_factory is not None:
                    raise ValueError(f"p.{pi}: 部品定義がありません: {e.get('type')}")
                continue
            def Q(x, y): dx, dy = tr(o, float(x), float(y)); return P(ex + dx, ey + dy)
            desc = d.find("description")
            for g in desc:
                st = g.get("style", "")
                if g.tag == "line": dr.line([Q(g.get("x1"), g.get("y1")), Q(g.get("x2"), g.get("y2"))], fill="black", width=1)
                elif g.tag == "rect":
                    x, y, w, h = (float(g.get(k)) for k in ("x", "y", "width", "height"))
                    a, b = Q(x, y), Q(x + w, y + h); box = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
                    rr = float(g.get("rx") or 0) * s
                    fill = "black" if "filling:black" in st else "white" if "filling:white" in st else None
                    (dr.rounded_rectangle(box, rr, outline="black", fill=fill) if rr else dr.rectangle(box, outline="black", fill=fill))
                elif g.tag in ("circle", "ellipse"):
                    x, y = float(g.get("x")), float(g.get("y")); dd = float(g.get("diameter") or g.get("width")); hh = float(g.get("diameter") or g.get("height"))
                    a, b = Q(x, y), Q(x + dd, y + hh)
                    dr.ellipse([min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])], outline="black", fill="black" if "filling:black" in st else "white" if "filling:white" in st else None)
                elif g.tag == "text":
                    sz, bd = parse_font(g.get("font")); x, y = Q(g.get("x"), g.get("y"))
                    draw_text(im, dr, (x, y), g.get('text', ''), sz, bd, s,
                              rotation=float(g.get('rotation', '0')) - o * 90, margin=0,
                              save_image=outdir is not None, baseline_anchor=True)
                elif g.tag == "polygon":
                    pts, i = [], 1
                    while g.get(f"x{i}") is not None:
                        pts.append(Q(g.get(f"x{i}"), g.get(f"y{i}"))); i += 1
                    if len(pts) > 1:
                        if g.get('closed') == 'false':
                            dr.line(pts, fill='black', width=1)
                        else:
                            dr.polygon(pts, outline="black", fill="black" if "filling:black" in st else "white" if "filling:white" in st else None)
                elif g.tag == "terminal":
                    pass
            for t in desc.iter("terminal"):
                terms[(e.get("uuid"), t.get("uuid"))] = (ex + tr(o, float(t.get("x")), float(t.get("y")))[0], ey + tr(o, float(t.get("x")), float(t.get("y")))[1], t.get("orientation"))
            info = {i.get("name"): (i.text or "") for i in e.iter("elementInformation")}
            for t in e.iter("dynamic_elmt_text"):
                txt = t.findtext("text") or ""
                if t.get("text_from") == "ElementInfo": txt = info.get(t.findtext("info_name") or "", "")
                if not txt: continue
                sz, bd = parse_font(t.get("font")); x, y = Q(t.get("x"), t.get("y"))
                width = float(t.get('text_width', '-1'))
                draw_text(im, dr, (x, y), txt, sz, bd, s, width, t.get('Halignment'),
                          float(t.get('rotation', '0')) - o * 90, save_image=outdir is not None)
        for c in dg.find("conductors") or []:
            a = terms.get((c.get("element1"), c.get("terminal1"))); b = terms.get((c.get("element2"), c.get("terminal2")))
            if not a or not b: continue
            (x1, y1, o1), (x2, y2, _) = a, b
            mid = (x2, y1) if o1 in ("e", "w") else (x1, y2)
            dr.line([P(x1, y1), P(*mid), P(x2, y2)], fill="black", width=1)
            if c.get("num") and c.get("displaytext") == "1":
                if c.get('userx') is not None:
                    dr.text(P(float(c.get('userx'))+4,float(c.get('usery'))+4),c.get('num'),fill='blue',font=fnt(float(c.get('numsize','8')),s=s))
                else:
                    dr.text(P((x1 + x2) / 2, y1 - 12), c.get("num"), fill="blue", font=fnt(6, s=s))
        inputs = dg.find("inputs")
        for i in inputs if inputs is not None else []:
            sz, bd = parse_font(i.get("font"))
            draw_text(im, dr, P(float(i.get('x')), float(i.get('y'))), i.get('text', ''),
                      sz, bd, s, rotation=float(i.get('rotation', '0')), save_image=outdir is not None)
        for sh in dg.find("shapes") or []:
            x1, y1, x2, y2 = (float(sh.get(k)) for k in ("x1", "y1", "x2", "y2"))
            pen = sh.find("pen"); dash = pen is not None and pen.get("style", "") != "SolidLine"
            if sh.get("type") == "Rectangle": dr.rectangle([P(min(x1, x2), min(y1, y2)), P(max(x1, x2), max(y1, y2))], outline="gray" if dash else "black")
            else: dr.line([P(x1, y1), P(x2, y2)], fill="gray" if dash else "black")
        if outdir is not None:
            out = os.path.join(outdir, f"p{pi:03d}.png"); im.save(out); outs.append(out)
    return outs

def parse_pages(t):
    r = set()
    for part in t.split(","):
        if "-" in part: a, b = part.split("-"); r |= set(range(int(a), int(b) + 1))
        elif part: r.add(int(part))
    return r


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qet', help='入力 QET ファイル')
    parser.add_argument('output_dir', help='PNG の出力先フォルダー')
    parser.add_argument('pages', nargs='?', default=None,
                        type=lambda value: None if value == 'all' else parse_pages(value),
                        help='ページ指定（例: 1,2,5-7 / all、既定: all）')
    parser.add_argument('scale', nargs='?', type=float, default=0.8, help='描画倍率（既定: 0.8）')
    args = parser.parse_args(argv)
    if not math.isfinite(args.scale) or args.scale <= 0:
        parser.error('描画倍率は正の数で指定してください')
    for output in render(args.qet, args.output_dir, args.pages, args.scale):
        print(output)


if __name__ == '__main__':
    main()
