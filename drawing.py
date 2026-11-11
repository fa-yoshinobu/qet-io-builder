"""QET描画の共通部品、ページ、座標と表の組立て。"""
import math
import re
import uuid
import xml.etree.ElementTree as ET
from renderers import connectors as CONN
from renderers.typography import PX_PER_PT, TEXT_MARGIN, text_w, wrap2, fit_font_size

FONT_FAMILY = "MS Gothic"

FONT = FONT_FAMILY + ",{size},-1,5,{weight},0,0,0,0,0"

COLLECTION = "embed://import/plc_io/"

BORDER_COLS, COL_SIZE = 20, 62     # 幅 1240(+区画帯20)。縦870との比 1.448 = A3横の印刷範囲に合わせ、上下左右の余白をそろえる

BORDER_ROWS, ROW_SIZE = 10, 80     # 高さ 800(+図枠 50) ≒ A3横の比率

ROW_Y0, ROW_PITCH = 90, 40         # 1点目の Y と行ピッチ

COM_Y = 740                        # COM 行の Y

LANE_BOTTOM_Y = 812                # P24/N24 レーンの下端(図面の下まで伸ばす)

UNIT_BOX_BOTTOM = 790              # 通信・リモートのページの機器の箱の下端(左下の記入欄の下端と同じ)

UNIT_BOX_W = 310                   # 特殊ユニット(通信・GOTオプション・リモート)の箱の幅。高さとともに全機種で同じにする

LANE_TOP_Y = 55                    # P/N レーン上端

HALF_W = BORDER_COLS * COL_SIZE // 2                  # 半分の幅(620)

HALVES = (0, HALF_W)                                  # 左半分 / 右半分の X オフセット

IN_X = dict(num=24, P=40, N=70, contact=150, tb=270, plc=330)  # 半分の中での位置

def u():
    return "{" + str(uuid.uuid4()) + "}"

def font(size=9, bold=False):
    return FONT.format(size=size, weight=75 if bold else 50)

STYLE = "line-style:normal;line-weight:normal;filling:none;color:black"

STYLE_FILL = "line-style:normal;line-weight:normal;filling:black;color:black"

class Symbol:
    """埋め込み要素(.elmt)の定義。端子の uuid は配線で参照する。"""

    def __init__(self, name, label_ja, width, height, hx, hy):
        self.name, self.label_ja = name, label_ja
        self.width, self.height, self.hx, self.hy = width, height, hx, hy
        self.parts = []      # (tag, attrs)
        self.terminals = {}  # key -> (uuid, orientation, x, y)
        self.dyn = []        # (info_name, x, y, size, bold)
        self.link_type = "simple"
        self.kinds = {}      # kindInformations(マスター/スレーブの種別)

    def line(self, x1, y1, x2, y2, thin=False):
        self.parts.append(("line", dict(x1=x1, y1=y1, x2=x2, y2=y2, end1="none", end2="none",
                                        length1="1.5", length2="1.5", antialias="false",
                                        style=STYLE.replace("line-weight:normal", "line-weight:thin") if thin else STYLE)))

    def rect(self, x, y, w, h):
        self.parts.append(("rect", dict(x=x, y=y, width=w, height=h, rx=0, ry=0,
                                        antialias="false", style=STYLE)))

    def circle(self, x, y, d, fill=False):
        self.parts.append(("circle", dict(x=x, y=y, diameter=d, antialias="true",
                                          style=STYLE_FILL if fill else STYLE)))

    def polygon(self, pts, fill=False, thin=False):
        """閉じた多角形。pts: [(x, y), …]"""
        attrs = {}
        for i, (x, y) in enumerate(pts, 1):
            attrs[f"x{i}"], attrs[f"y{i}"] = round(x, 2), round(y, 2)
        style = STYLE_FILL if fill else STYLE
        if thin:
            style = style.replace("line-weight:normal", "line-weight:thin")
        attrs.update(closed="true", antialias="true", style=style)
        self.parts.append(("polygon", attrs))

    def rrect(self, x, y, w, h, r=3):
        """角丸の四角"""
        self.parts.append(("rect", dict(x=x, y=y, width=w, height=h, rx=r, ry=r,
                                        antialias="true", style=STYLE)))

    def label(self, x, y, text, size=8, bold=False):
        from renderers.notes import drawing_text
        text = drawing_text(text)
        if not text:
            return
        self.parts.append(("text", dict(x=x, y=y, text=text, rotation=0, color="#000000",
                                        font=font(size, bold))))

    def dashed(self, x1, y1, x2, y2):
        self.parts.append(("line", dict(x1=x1, y1=y1, x2=x2, y2=y2, end1="none", end2="none",
                                        length1="1.5", length2="1.5", antialias="false",
                                        style="line-style:dashed;line-weight:thin;filling:none;color:black")))

    def terminal(self, key, orient, x, y):
        self.terminals[key] = (u(), orient, x, y)

    def dynamic(self, info, x, y, size=9, bold=False, valign="AlignTop"):
        self.dyn.append((info, x, y, size, bold, valign))

    def to_xml(self):
        el = ET.Element("element", name=self.name + ".elmt")
        d = ET.SubElement(el, "definition", type="element", version="0.100",
                          # QET は大きさ・基準点が整数でないと部品を読み込まない
                          width=str(math.ceil(self.width)), height=str(math.ceil(self.height)),
                          hotspot_x=str(round(self.hx)), hotspot_y=str(round(self.hy)), link_type=self.link_type)
        ET.SubElement(d, "uuid", uuid=u())
        names = ET.SubElement(d, "names")
        ET.SubElement(names, "name", lang="ja").text = self.label_ja
        ET.SubElement(names, "name", lang="en").text = self.name
        if self.kinds:
            ki = ET.SubElement(d, "kindInformations")
            for k, v in self.kinds.items():
                ET.SubElement(ki, "kindInformation", name=k, show="1").text = v
        ET.SubElement(d, "elementInformations")
        ET.SubElement(d, "informations").text = "PLC I/O 試作用シンボル(自作)"
        desc = ET.SubElement(d, "description")
        for tag, attrs in self.parts:
            ET.SubElement(desc, tag, {k: str(v) for k, v in attrs.items()})
        for info, x, y, size, bold, valign in self.dyn:
            cell = io_text_cell(self.name,info)
            t = ET.SubElement(desc, "dynamic_text", uuid=u(), x=str(x), y=str(y), z="5",
                              text_from="ElementInfo", Halignment="AlignLeft", Valignment=valign,
                              rotation="0", text_width="-1", keep_visual_rotation="false",
                              frame="false", font=font(size, bold))
            if cell:
                t.set('x',str(cell[0])); t.set('text_width',str(cell[1])); t.set('Halignment','AlignHCenter')
            ET.SubElement(t, "text")
            ET.SubElement(t, "info_name").text = info
        for key, (tu, orient, x, y) in self.terminals.items():
            ET.SubElement(desc, "terminal", uuid=tu, orientation=orient, x=str(x), y=str(y),
                          name="", type="Generic")
        return el

def draw_rj45(sym, x0, cy):
    CONN.draw(sym, 'rj45', x0, cy)

def draw_usb_minib(sym, x0, cy):
    CONN.draw(sym, 'usb_minib', x0, cy)

def draw_dsub9(sym, x0, cy, male=True):
    CONN.draw(sym, 'dsub9', x0, cy, 'male' if male else 'female')

def draw_minidin8(sym, x0, cy):
    CONN.draw(sym, 'minidin8', x0, cy, 'male')

def draw_coax(sym, x0, cy):
    CONN.draw(sym, 'coax_f', x0, cy)

def draw_optical(sym, x0, cy):
    CONN.draw(sym, 'optical', x0, cy)

def rotate90(sym, start, cx, cy):
    """sym.parts[start:] を (cx, cy) を中心に時計回りに 90° 回す(コネクタの向きを縦にするため)"""
    rot = lambda x, y: (cx - (y - cy), cy + (x - cx))
    for kind, a in sym.parts[start:]:
        if kind == "line":
            a["x1"], a["y1"] = rot(a["x1"], a["y1"]); a["x2"], a["y2"] = rot(a["x2"], a["y2"])
        elif kind == "rect":
            x, y = rot(a["x"], a["y"] + a["height"])          # 回したあとの左上
            a["x"], a["y"], a["width"], a["height"] = x, y, a["height"], a["width"]
        elif kind == "circle":
            r = a["diameter"] / 2
            x, y = rot(a["x"] + r, a["y"] + r)
            a["x"], a["y"] = x - r, y - r
        elif kind == "polygon":
            i = 1
            while f"x{i}" in a:
                a[f"x{i}"], a[f"y{i}"] = (round(v, 2) for v in rot(a[f"x{i}"], a[f"y{i}"])); i += 1

def box_symbol(name, label_ja, w, h, top, bottom):
    """左上の端子を原点にした箱。top/bottom: [(端子名, x)]。上端子は n、下端子は s"""
    sym = Symbol(name, label_ja, w, h + 10, 20, 5)
    sym.rect(-20, 0, w, h)
    for t, x in top:                     # 端子は ○ で描く
        sym.circle(x - 4, 0, 8)
        sym.terminal(t, "n", x, 0)
        sym.label(x - 4, 21, t, 8)
    for t, x in bottom:
        sym.circle(x - 4, h - 8, 8)
        sym.terminal(t, "s", x, h)
        sym.label(x + 7, h - 1, t, 8)   # 端子名は ○ の右(箱の中の形名・仕様の行と重ねない)
    sym.dynamic("label", -14, 26, 10, True)
    sym.dynamic("comment", -14, 44, 8, False)
    return sym

LANE = {"P": "P24", "N": "N24"}

def ctext(p, cx, cy, t, size, bold=False):
    """(cx, cy) を中心に文字を置く(MS ゴシックの文字幅と文字枠の余白から計算)"""
    w = text_w(t, size) + 2 * TEXT_MARGIN
    hgt = size * PX_PER_PT + 2 * TEXT_MARGIN
    p.text(round(cx - w / 2, 1), round(cy - hgt / 2, 1), t, size, bold)

VCENTER_SYMBOLS = {"plc_in", "plc_out", "fx_in", "fx_out", "fx_in_dual", "fx_out_dual"}   # 文字を上下中央ぞろえにする部品

def vcenter(size, lines=1):
    """行の中心(y=0)に文字の中心を合わせるための y。MS ゴシックの行の高さは 1em"""
    return round(-(2 * TEXT_MARGIN + lines * size * PX_PER_PT) / 2, 1)

def comment_value(r):
    """CSVの信号名。「|」で改行を指定できる(指定がなければ欄の幅で自動改行)"""
    return r["信号名"].strip().replace("|", "\n")

def comment_text(value, x, width, size, row_h):
    """1段でも2段でも同じ大きさで、行の高さの中央にそろえる"""
    n = min(value.count("\n") + 1, 2)
    return ("comment", x, vcenter(size, n), size, False)

ORIENT_NUM = dict(n=0, e=1, s=2, w=3)

def io_text_cell(key, info):
    if key.startswith('plc_in_mx_combined'):
        return {'auxiliary1': (4, 100), 'comment': (104, 150)}.get(info)
    if key.startswith('plc_in_unit_wide'):
        return {'auxiliary1':(4,45), 'label':(49,105), 'comment':(154,180)}.get(info)
    if key.startswith('plc_in_unit'):
        return {'auxiliary1':(4,45), 'label':(49,105), 'comment':(154,100)}.get(info)
    if key.startswith('plc_in'):
        return {'auxiliary1':(4,45), 'label':(49,55)}.get(info)
    if key.startswith('plc_out'):
        return {'label':(-104,55), 'auxiliary1':(-49,45)}.get(info)
    if key.startswith('fx_in') and info=='label':
        return (4,55)
    if key.startswith('fx_out') and info=='label':
        return (-59,55)
    return None

HEAD_X, HEAD_Y, NOTE_Y = 275, 24, 44  # 入出力以外のページの見出し: 機器の箱の左端の上(左は配線用に空ける)

def page_heading(p, title, note=None, x=HEAD_X):
    """入出力以外のページの見出し。位置と大きさを全ページでそろえる"""
    p.text(x, HEAD_Y, title, 10, True)
    if note:
        p.text(x, NOTE_Y, note, 8)

class Page:
    def __init__(self, symbols):
        self.sym = symbols
        self.elements = []
        self.conductors = []
        self.texts = []
        self.shapes = []
        self.placed = []      # (部品の種類, 要素, x, y)
        self._power_lane_labels = []

    def power_lane_label(self, x, label, size=8):
        """上端から始まる電源レーンを登録し、見出しを関連付ける。"""
        count = len(self.texts)
        ctext(self, x, 44, label, size, True)
        self._power_lane_labels.append((x, self.texts[-1] if len(self.texts) > count else None))

    def _remove_unused_power_lanes(self):
        """登録したレーンのうち、実部品への接続がないものだけを除く。"""
        nodes = {e.get('uuid') for key, e, _, _ in self.placed if key in ('node', 'junction')}
        graph = {}
        for wire in self.conductors:
            a, b = wire.get('element1'), wire.get('element2')
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
        remove = set()
        for x, label in self._power_lane_labels:
            pending = [e.get('uuid') for key, e, px, py in self.placed
                       if key in ('node', 'junction') and px == x and py == LANE_TOP_Y]
            connected = set()
            while pending:
                node = pending.pop()
                if node in connected:
                    continue
                connected.add(node)
                pending.extend(graph.get(node, set()) - connected)
            if connected <= nodes:
                remove.update(connected)
                if label in self.texts:
                    self.texts.remove(label)
        self.elements[:] = [e for e in self.elements if e.get('uuid') not in remove]
        self.placed[:] = [p for p in self.placed if p[1].get('uuid') not in remove]
        self.conductors[:] = [w for w in self.conductors
                              if w.get('element1') not in remove and w.get('element2') not in remove]

    def place(self, key, x, y, label="", comment="", prefix="", texts=(), infos=None, tag=""):
        if tag:
            infos = dict(infos or {}, manufacturer_reference=label)
            texts = [('manufacturer_reference' if t[0]=='label' else t[0], *t[1:]) for t in texts]
            texts.append(('label', 0, -18, 10, True))
            label = tag
        valign = "AlignVCenter" if key in VCENTER_SYMBOLS else "AlignTop"
        """texts: (info_name, x, y, size, bold) をインスタンスに配置"""
        sym = self.sym[key]
        e = ET.Element("element", type=COLLECTION + sym.name + ".elmt", uuid=u(),
                       x=str(x), y=str(y), z="10", orientation="0", prefix=prefix, freezeLabel="false")
        terms = ET.SubElement(e, "terminals")
        for i, (k, (tu, orient, tx, ty)) in enumerate(sym.terminals.items()):
            ET.SubElement(terms, "terminal", id=str(sum(len(el.findall('./terminals/terminal')) for el in self.elements) + i + 1),
                          orientation=str(ORIENT_NUM[orient]), x=str(tx), y=str(ty))
        ET.SubElement(e, "inputs")
        info_el = ET.SubElement(e, "elementInformations")
        for name, val in [("label", label), ("comment", comment)] + list((infos or {}).items()):
            ET.SubElement(info_el, "elementInformation", name=name, show="1").text = val
        dyn = ET.SubElement(e, "dynamic_texts")
        for tt in texts:
            info, tx, ty, size, bold = tt[:5]
            tw = tt[5] if len(tt) > 5 else -1          # 幅を決めると QElectroTech が折り返す
            cell = io_text_cell(key,info)
            if cell:
                tx,tw = cell
                value = str({'label':label,'comment':comment,**(infos or {})}.get(info,''))
                row_height = 32 if key.startswith('fx_') else ROW_PITCH
                size, lines = fit_font_size(value, tw, row_height, size)
                ty = vcenter(size, lines)
            t = ET.SubElement(dyn, "dynamic_elmt_text", uuid=u(), x=str(tx), y=str(ty),
                              text_from="ElementInfo", Halignment="AlignHCenter" if cell else "AlignLeft", Valignment=valign,
                              rotation="0", text_width=str(tw), keep_visual_rotation="false",
                              frame="false", font=font(size, bold))
            ET.SubElement(t, "text")
            ET.SubElement(t, "info_name").text = info
        ET.SubElement(e, "texts_groups")
        self.elements.append(e)
        self.placed.append((key, e, x, y))
        return (e.get("uuid"), sym, x, y)

    def wire(self, a, ta, b, tb, num="", show=False):
        (ua, sa, *_), (ub, sb, *_) = a, b
        c = ET.Element("conductor", {
            "element1": ua, "terminal1": sa.terminals[ta][0],
            "element2": ub, "terminal2": sb.terminals[tb][0],
            "x": "0", "y": "0", "type": "multi", "num": num,
            "displaytext": "1" if show else "0", "numsize": "8", "condsize": "1",
            "horizrotatetext": "0", "vertirotatetext": "270",
            "horizontal-alignment": "AlignTop", "vertical-alignment": "AlignRight",
            "onetextperfolio": "0", "freezeLabel": "false", "text_color": "#000000",
            "color": "#000000", "bicolor": "false", "color2": "#000000", "dash-size": "1",
            "formula": "", "function": "", "tension_protocol": "", "conductor_color": "",
            "conductor_section": "", "cable": "", "bus": "",
        })
        if show and num and (num in LANE.values() or re.fullmatch(r'[PN]\d+',num)):
            if sb.name.startswith(('plc_in','fx_in')) or (sb.name == 'module_pin' and sb.terminals[tb][1] == 'w'):
                _,_,tx,ty = sb.terminals[tb]
                endpoint_x,endpoint_y = b[2]+tx,b[3]+ty
                c.set('userx',str(round(endpoint_x-12-text_w(num,8)-2*TEXT_MARGIN,1)))
                c.set('usery',str(round(endpoint_y-8*PX_PER_PT-2*TEXT_MARGIN-2,1)))
                c.set('rotation','0')
            elif sa.name.startswith(('plc_out','fx_out')) or (sa.name=='tb_terminal' and sb.name=='junction'):
                _,_,tx,ty = sa.terminals[ta]
                c.set('userx',str(round(a[2]+tx+12,1)))
                c.set('usery',str(round(a[3]+ty-8*PX_PER_PT-2*TEXT_MARGIN-2,1)))
                c.set('rotation','0')
        # segment を書かない → QElectroTech が端子位置から自動で経路を作る
        self.conductors.append(c)

    def rect(self, x1, y1, x2, y2, dash=True, width=1.5):
        sh = ET.Element("shape", type="Rectangle", x1=str(x1), y1=str(y1), x2=str(x2), y2=str(y2),
                        z="0", rx="0", ry="0", closed="0", is_movable="1")
        ET.SubElement(sh, "pen", style="DashLine" if dash else "SolidLine", widthF=str(width), color="#000000")
        ET.SubElement(sh, "brush", style="NoBrush", color="#ffffff")
        self.shapes.append(sh)

    def stretch_boxes(self, top=52, bottom=None):
        """上端が top の機器の箱を、同じ下端(記入欄の下端と同じ高さ)まで伸ばす。
        ユニットごとに箱の高さが違うとでこぼこして見えるので、通信・リモートのページは高さをそろえる"""
        bottom = bottom or UNIT_BOX_BOTTOM
        for sh in self.shapes:
            if sh.get("type") == "Rectangle" and float(sh.get("y1")) == top and float(sh.get("y2")) < bottom:
                sh.set("y2", str(bottom))

    def extend_lanes(self, xs, bottom=None):
        """電源レーン(x の位置の縦線)を図面の下まで伸ばす"""
        bottom = bottom or LANE_BOTTOM_Y
        for x in xs:
            pts = [(y, e) for k, e, xx, y in self.placed if k == "junction" and xx == x]
            if not pts:
                continue
            y, e = max(pts, key=lambda t: t[0])
            if y >= bottom:
                continue
            last = (e.get("uuid"), self.sym["junction"], x, y)
            end = self.place("junction", x, bottom)
            self.wire(last, "s", end, "n")

    def finish(self):
        """3本以上の線がつながる所だけ点を打つ(線の端や曲がり角は点なし)"""
        self._remove_unused_power_lanes()
        deg = {}
        for c in self.conductors:
            for k in ("element1", "element2"):
                deg[c.get(k)] = deg.get(c.get(k), 0) + 1
        node_type = COLLECTION + "node.elmt"
        terminal_map = {self.sym["junction"].terminals[k][0]: self.sym["node"].terminals[k][0]
                        for k in "nesw"}
        for k, e, x, y in self.placed:
            if k == "junction" and deg.get(e.get("uuid"), 0) < 3:
                e.set("type", node_type)
                for c in self.conductors:
                    for element, terminal in (("element1", "terminal1"), ("element2", "terminal2")):
                        if c.get(element) == e.get("uuid"):
                            c.set(terminal, terminal_map[c.get(terminal)])

    def line(self, x1, y1, x2, y2, width=1.0, dash=False):
        sh = ET.Element("shape", type="Line", x1=str(x1), y1=str(y1), x2=str(x2), y2=str(y2),
                        z="0", rx="0", ry="0", closed="0", is_movable="1")
        ET.SubElement(sh, "pen", style="DashLine" if dash else "SolidLine", widthF=str(width), color="#000000")
        ET.SubElement(sh, "brush", style="NoBrush", color="#ffffff")
        self.shapes.append(sh)

    def text(self, x, y, s, size=9, bold=False):
        from renderers.notes import drawing_text
        s = drawing_text(s)
        if not s:
            return
        esc = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.texts.append(ET.Element("input", uuid=u(), x=str(x), y=str(y), rotation="0",
                                     text=esc, font=font(size, bold)))

IN_TEXTS = [("auxiliary1", 10, vcenter(9), 9, False),    # ピン番号
            ("label", 56, vcenter(10), 10, True),         # アドレス
            ("comment", 110, vcenter(8), 8, False)]       # 用途

OUT_TEXTS = [("comment", -228, vcenter(8), 8, False),    # 用途
             ("label", -98, vcenter(10), 10, True),       # アドレス
             ("auxiliary1", -44, vcenter(9), 9, False)]   # ピン番号

OUT_X = dict(num=24, plc=276, tb=320, load=385, P=432, N=454, ref=462)  # 出力: レーンの外に参照欄

def page_note(p, pg, pw):
    """図面の注記は入れない(中継端子台の番号が未確認の箇所は「?」で示す)"""
    return

def lane_labels(p, X):
    p.power_lane_label(X["P"], LANE["P"])
    p.power_lane_label(X["N"], LANE["N"])

def output_lane_labels(p, left_x, left_name, right_x, right_name):
    gap = right_x-left_x
    size = next((s for s in (8,7,6) if (text_w(left_name,s)+text_w(right_name,s))/2+6 <= gap),6)
    p.power_lane_label(left_x, left_name, size)
    p.power_lane_label(right_x, right_name, size)

def is_slot_unit(kind, model):
    return kind in ('qcomm','iqrcomm','qbody','iqrbody','qanalog','iqranalog','qmixed','iqrmixed') or str(model).upper().startswith(('Q','R'))

def identity_cells(p, config, x, width, top, bottom):
    p.identity_headers = True
    rack = is_slot_unit(config.get('kind',''),config['model'])
    number = str(config.get('slot','') if rack else config.get('unit_no',config.get('slot','')))
    cuts=(x,x+width*0.33,x+width*0.57,x+width)
    values=(('スロットNo. ' if rack else 'ユニットNo. ')+number,config.get('tag',''),config['model'])
    if (config.get('kind') == 'terminal_block' or config.get('cable_layout')) and not number and text_w(values[1],6)>cuts[2]-cuts[1]-8:
        # ケーブルの両端の完全なタグはページ下にも表示する。空のユニットNo.欄を長いタグに使う。
        cuts=(x,cuts[2],x+width)
        tag=values[1]
        max_width=cuts[1]-x-8
        if text_w(tag,6)>max_width:
            while text_w(tag+'…',6)>max_width:
                tag=tag[:-1]
            tag+='…'
        values=(tag,config['model'])
    for i,value in enumerate(values):
        cell_width=cuts[i+1]-cuts[i]-8
        size=next((s for s in (8,7,6) if text_w(value,s)<=cell_width),6)
        ctext(p,(cuts[i]+cuts[i+1])/2,(top+bottom)/2,wrap2(value,cell_width,size),size,True)
        if i:
            p.line(cuts[i],top,cuts[i],bottom,width=0.5)

def unit_identity_header(p, config, x, width, top=34, bottom=52):
    p.rect(x,top,x+width,bottom,dash=False,width=1)
    identity_cells(p,config,x,width,top,bottom)

def io_table_header(p, config, x, width, columns, labels=('端子','アドレス','用途')):
    """IO表の上端にスロット・タグ・形名をまとめ、列見出しを表につなぐ。"""
    p.io_table_header = True
    p.rect(x, 34, x+width, 70, dash=False, width=1)
    p.line(x, 52, x+width, 52, width=0.5)
    identity_cells(p,config,x,width,34,52)
    for dx in columns:
        p.line(x+dx,52,x+dx,70,width=0.5)
    edges=(0,*columns,width)
    for i,label in enumerate(labels):
        ctext(p,x+(edges[i]+edges[i+1])/2,61,label,7)

FX_IN_X = dict(num=24, outer=45, inner=72, contact=160, plc=275)  # 入力半分: 左にレーン

FX_OUT_X = dict(num=24, plc=294, load=398, inner=446, outer=466, ref=474)  # 出力半分: レーンの外に参照欄

FX_IN_TEXTS = [("label", 10, vcenter(10), 10, True)]          # 用途は comment_text() で2段対応

FX_OUT_TEXTS = [("label", -52, vcenter(10), 10, True)]

TABLE_X0, TABLE_Y0, TABLE_ROW = 60, 110, 30

def table(p, x0, y0, cols, rows, head_size=9, body_size=9):
    """cols: [(見出し, 幅)], rows: [[値…]]。罫線は図形の線で描く"""
    width = sum(w for _, w in cols)
    n = len(rows) + 1
    for i in range(n + 1):
        p.line(x0, y0 + i * TABLE_ROW, x0 + width, y0 + i * TABLE_ROW, 1.5 if i in (0, 1, n) else 0.8)
    x = x0
    for _, w in cols:
        p.line(x, y0, x, y0 + n * TABLE_ROW, 1.5 if x == x0 else 0.8)
        x += w
    p.line(x, y0, x, y0 + n * TABLE_ROW, 1.5)
    x = x0
    for (h, w) in cols:
        p.text(x + 6, y0 + 6, h, head_size, True)
        x += w
    for ri, r in enumerate(rows, 1):
        x = x0
        for (_, w), v in zip(cols, r):
            p.text(x + 6, y0 + ri * TABLE_ROW + 6, str(v), body_size)
            x += w
