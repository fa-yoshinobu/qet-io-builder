""".qet をおおまかに PNG にする確認用ツール(QET を開かずにレイアウトを見るため)。
QET の自動配線は L 字で近似し、表題欄は名称だけを描く。正式な確認は QET の「PDFにエクスポート」で行う。
使い方: python tools/preview_qet.py 図面.qet 出力フォルダ [ページ(例 1,2,5-7 / all)] [倍率(既定0.8)]
必要: Pillow。日本語フォントは Noto Sans CJK(Linux)か MS ゴシック(Windows)を使う。"""
import sys, os, re, math
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
    px = max(6, int(pt * 96 / 72 * s))
    k = (px, bold)
    if k not in _fc:
        try: _fc[k] = ImageFont.truetype(FONTB if bold else FONT, px, index=0)
        except Exception: _fc[k] = ImageFont.load_default()
    return _fc[k]
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


def render(path, outdir, pages=None, s=1.0):
    root = ET.parse(path).getroot()
    defs = {}
    for el in root.iter("element"):
        if el.get("name") and el.find("definition") is not None:
            defs[el.get("name")] = el.find("definition")
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
        terms = {}
        for e in dg.find("elements") or []:
            name = e.get("type").split("/")[-1]; d = defs.get(name)
            ex, ey, o = float(e.get("x")), float(e.get("y")), int(e.get("orientation", "0"))
            if d is None: continue
            def Q(x, y): dx, dy = tr(o, float(x), float(y)); return P(ex + dx, ey + dy)
            desc = d.find("description")
            for g in desc:
                st = g.get("style", "")
                if g.tag == "line": dr.line([Q(g.get("x1"), g.get("y1")), Q(g.get("x2"), g.get("y2"))], fill="black", width=1)
                elif g.tag == "rect":
                    x, y, w, h = (float(g.get(k)) for k in ("x", "y", "width", "height"))
                    a, b = Q(x, y), Q(x + w, y + h); box = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
                    rr = float(g.get("rx") or 0) * s
                    fill = "black" if "filling:black" in st else None
                    (dr.rounded_rectangle(box, rr, outline="black", fill=fill) if rr else dr.rectangle(box, outline="black", fill=fill))
                elif g.tag in ("circle", "ellipse"):
                    x, y = float(g.get("x")), float(g.get("y")); dd = float(g.get("diameter") or g.get("width")); hh = float(g.get("diameter") or g.get("height"))
                    a, b = Q(x, y), Q(x + dd, y + hh)
                    dr.ellipse([min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])], outline="black", fill="black" if "filling:black" in st else None)
                elif g.tag == "text":
                    sz, bd = parse_font(g.get("font")); x, y = Q(g.get("x"), g.get("y"))
                    dr.text((x, y - sz * 96 / 72 * s), g.get("text", ""), fill="black", font=fnt(sz, bd, s))
                elif g.tag == "polygon":
                    pts, i = [], 1
                    while g.get(f"x{i}") is not None:
                        pts.append(Q(g.get(f"x{i}"), g.get(f"y{i}"))); i += 1
                    if len(pts) > 1:
                        if g.get('closed') == 'false':
                            dr.line(pts, fill='black', width=1)
                        else:
                            dr.polygon(pts, outline="black", fill="black" if "filling:black" in st else None)
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
                lines = wrap_lines(dr, txt, fnt(sz, bd, s), (width - 8) * s, sz) if width > 0 else txt.split("\n")
                for li, line in enumerate(lines):
                    offset=4*s
                    if t.get('Halignment')=='AlignHCenter' and width>0:
                        offset=(width*s-dr.textlength(line,font=fnt(sz,bd,s)))/2
                    dr.text((x + offset, y + 4 * s + li * sz * 1.35 * s), line, fill="black", font=fnt(sz, bd, s))
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
        for i in dg.find("inputs") or []:
            # 独立テキストも動的テキストと同じく、文字枠の余白(4)の内側に描かれる
            sz, bd = parse_font(i.get("font"))
            for li, line in enumerate(i.get("text", "").split("\n")):
                dr.text(P(float(i.get("x")) + 4, float(i.get("y")) + 4 + li * sz * 1.35), line, fill="black", font=fnt(sz, bd, s))
        for sh in dg.find("shapes") or []:
            x1, y1, x2, y2 = (float(sh.get(k)) for k in ("x1", "y1", "x2", "y2"))
            pen = sh.find("pen"); dash = pen is not None and pen.get("style", "") != "SolidLine"
            if sh.get("type") == "Rectangle": dr.rectangle([P(min(x1, x2), min(y1, y2)), P(max(x1, x2), max(y1, y2))], outline="gray" if dash else "black")
            else: dr.line([P(x1, y1), P(x2, y2)], fill="gray" if dash else "black")
        out = os.path.join(outdir, f"p{pi:03d}.png"); im.save(out); outs.append(out)
    return outs

def parse_pages(t):
    r = set()
    for part in t.split(","):
        if "-" in part: a, b = part.split("-"); r |= set(range(int(a), int(b) + 1))
        elif part: r.add(int(part))
    return r
if __name__ == "__main__":
    pages = parse_pages(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != "all" else None
    s = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
    for o in render(sys.argv[1], sys.argv[2], pages, s): print(o)
