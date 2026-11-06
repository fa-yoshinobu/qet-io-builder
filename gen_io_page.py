#!/usr/bin/env python3
"""
I/OリストCSVから QElectroTech のプロジェクト(.qet)を生成する試作スクリプト。

ページ構成は project.json の "pages" で指定する(1ページ = 32点ユニット1台)。
- 入力(RX41C4 想定、プラスコモン):
    P/N ─ 接点 ─ 中継端子 ─ [ピン│Xアドレス│用途]   (配線はユニットの左から入る)
- 出力(RY41NT2P 想定、シンク):
    [用途│Yアドレス│ピン] ─ 中継端子 ─ 負荷 ─ P/N   (配線はユニットの右から出る)
左半分に先頭16点、右半分に後半16点。

使い方:
    python3 gen_io_page.py project.json out.qet

ユニット側のピン・端子番号は機種別定義から入る。
中継端子台の番号が空欄の場合は「?」と表示し、未設定であることを図面上で明示する。
"""
import copy
import csv
import io
import json
import math
import os
import re
import sys
import uuid
from datetime import date
import xml.etree.ElementTree as ET
from xml.dom import minidom

# 図面の文字は MS ゴシック(Windows 標準・等幅: 半角 = 全角の半分)。
# 図枠・線番・参照表示の文字は QElectroTech 本体の設定(図面のフォント)で決まる
FONT_FAMILY = "MS Gothic"
FONT = FONT_FAMILY + ",{size},-1,5,{weight},0,0,0,0,0"
COLLECTION = "embed://import/plc_io/"


def project_config(config=None):
    """GUI新規作成・CLI・直接生成で共通のプロジェクト既定値。指定済みの値は維持する。"""
    if config is not None and not isinstance(config, dict):
        raise ValueError('プロジェクト設定はオブジェクトにしてください')
    result = {key: '' for key in ('project_title', 'company', 'customer', 'machine', 'drawing_no',
                                  'revision', 'author', 'checker', 'approver')}
    result.update(date=date.today().strftime('%Y%m%d'), power={'P': '+24V', 'N': '0V'}, front_pages=True)
    result.update(config or {})
    if not isinstance(result['power'], dict):
        raise ValueError('power（電源設定）はオブジェクトにしてください')
    result['power'] = {'P': '+24V', 'N': '0V', **result['power']}
    return result

# ---------------------------------------------------------------- レイアウト
BORDER_COLS, COL_SIZE = 20, 62     # 幅 1240(+区画帯20)。縦870との比 1.448 = A3横の印刷範囲に合わせ、上下左右の余白をそろえる
BORDER_ROWS, ROW_SIZE = 10, 80     # 高さ 800(+図枠 50) ≒ A3横の比率
ROW_Y0, ROW_PITCH = 90, 40         # 1点目の Y と行ピッチ
COM_Y = 740                        # COM 行の Y
LANE_BOTTOM_Y = 812                # P24/N24 レーンの下端(図面の下まで伸ばす)
UNIT_BOX_BOTTOM = 790              # 通信・リモートのページの機器の箱の下端(左下の記入欄の下端と同じ)
UNIT_BOX_W = 310                   # 特殊ユニット(通信・GOTオプション・リモート)の箱の幅。高さとともに全機種で同じにする
LANE_TOP_Y = 55                    # P/N レーン上端

# ---------------------------------------------------------------- ピン配置
# 出典: 三菱電機 MELSEC iQ-R Installation Manual for Digital Input and Output
#       Modules (Art.no. 294687, Version B) の外部配線図
# 40ピンコネクタ: 先頭16点 = B20〜B5、後半16点 = A20〜A5
def _pins_32(prefix):
    m = {}
    for i in range(16):
        m[f"{prefix}{i:X}"] = f"B{20 - i}"
        m[f"{prefix}{16 + i:X}"] = f"A{20 - i}"
    return m


# iQ-R / Q の入出力ユニットは parts/plc/mitsubishi 以下で定義する。
TB16 = [f"TB{i}" for i in range(1, 17)]
PINS32 = [f"B{20 - i}" for i in range(16)] + [f"A{20 - i}" for i in range(16)]
PIN_PRESETS = {"TB16": TB16, "PINS32": PINS32}


def io_unit(model):
    m = model.upper().replace(" ", "")
    if m not in IO_UNITS:
        raise SystemExit(f"未対応のユニットです: {model}(対応: {', '.join(IO_UNITS)})")
    return IO_UNITS[m]


def configured_unit(uc):
    if uc.get("_mixed_io"):
        return {"qmixed": Q_MIXED, "iqrmixed": IQR_MIXED, "remotemixed": REMOTE_MIXED}[uc["kind"]][uc["model"].upper()][uc["_mixed_io"] + "put"]
    return io_unit(uc["model"])


def unit_addrs(uc):
    """ユニットのアドレス一覧(16進)。uc: ページ設定(model, start)"""
    unit = configured_unit(uc)
    prefix = "X" if unit["io"] == "in" else "Y"
    start = int(str(uc.get("start", "0")), 16)
    return [f"{prefix}{start + i:X}" for i in range(unit["points"])]


IO_COLUMNS = {"in": ("アドレス", "信号名", "機器番号", "接点", "線番", "備考"),
              "out": ("アドレス", "信号名", "機器番号", "負荷", "形式", "線番", "備考")}


def blank_io_rows(uc):
    """CSV未指定のときの行。アドレスだけを入れ、信号名などは空欄にする(構成から先に図面を作るため)"""
    columns = IO_COLUMNS[configured_unit(uc)["io"]]
    return [dict(dict.fromkeys(columns, ""), アドレス=address) for address in unit_addrs(uc)]


def iqr_units(pg, rows):
    """iQ-R/Q のページに載るユニット [(設定, 行)]。right があれば右半分に別ユニット"""
    if pg["kind"] in ("qmixed", "iqrmixed", "remotemixed"):
        base = int(str(pg.get("start", "0")), 16)
        spec = {"qmixed": Q_MIXED, "iqrmixed": IQR_MIXED, "remotemixed": REMOTE_MIXED}[pg["kind"]][pg["model"].upper()]
        return [(dict(pg, _mixed_io=direction, csv=pg.get(direction + "put_csv", ""),
                      start=f"{base + spec[direction + 'put']['start_offset']:X}"), rows[direction])
                for direction in ("in", "out")]
    out = [(pg, rows)]
    if pg.get("right"):
        out.append((pg["right"], pg["_right_rows"]))
    return out

# 入力ページ: 左右とも同じ向き(P/N → 接点 → 中継端子 → ユニット部)
HALF_W = BORDER_COLS * COL_SIZE // 2                  # 半分の幅(620)
HALVES = (0, HALF_W)                                  # 左半分 / 右半分の X オフセット
IN_X = dict(num=24, P=40, N=70, contact=150, tb=270, plc=330)  # 半分の中での位置


def u():
    return "{" + str(uuid.uuid4()) + "}"


def font(size=9, bold=False):
    return FONT.format(size=size, weight=75 if bold else 50)


# ------------------------------------------------------------ シンボル定義
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


# ------------------------------------------------------------ コネクタの絵(正面図)
# 絵は renderers/connectors.py の共通部品。ここでは本体の箱の中に描くときの呼び出し名を残す
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # ツールから読み込まれたときも renderers を見つける
from renderers import connectors as CONN
from renderers.analog import channel_rows, extra_rows, readonly_symbol


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


def build_symbols():
    s = {}
    # a接点(横向き)
    a = Symbol("contact_a", "a接点(横)", 40, 20, 20, 10)
    a.line(-20, 0, -8, 0); a.line(-8, 0, 9, -7); a.line(8, 0, 20, 0); a.line(8, 0, 8, -4)
    a.terminal("w", "w", -20, 0); a.terminal("e", "e", 20, 0)
    s["contact_a"] = a
    # b接点(横向き)
    b = Symbol("contact_b", "b接点(横)", 40, 20, 20, 10)
    b.line(-20, 0, -8, 0); b.line(-8, 0, 11, -8); b.line(8, 0, 20, 0); b.line(8, 0, 8, -9)
    b.terminal("w", "w", -20, 0); b.terminal("e", "e", 20, 0)
    s["contact_b"] = b
    # クロスリファレンス用: リレー接点(スレーブ)。形は通常の接点と同じ
    for src, key, state in (("contact_a", "relay_contact_a", "NO"), ("contact_b", "relay_contact_b", "NC")):
        r = Symbol(key, f"リレー接点 {state}(横)", 40, 20, 20, 10)
        r.parts = list(s[src].parts)
        r.terminal("w", "w", -20, 0); r.terminal("e", "e", 20, 0)
        r.link_type = "slave"
        r.kinds = {"type": "simple", "state": state, "number": "1"}
        s[key] = r
    # 中継端子(A6TBXY36 の1端子)
    t = Symbol("tb_terminal", "中継端子", 20, 20, 10, 10)
    t.circle(-3, -3, 6)
    t.terminal("w", "w", -3, 0); t.terminal("e", "e", 3, 0)
    s["tb_terminal"] = t
    # PLC入力ユニット部 1点分: 左から「ピン│アドレス│用途」、配線は左から入る
    pc = Symbol("plc_in", "PLC入力ユニット1点(ピン/アドレス/用途)", 260, 40, 0, 20)
    pc.rect(4, -20, 250, 40)
    pc.line(49, -20, 49, 20); pc.line(104, -20, 104, 20)
    pc.terminal("t", "w", 4, 0)
    s["plc_in"] = pc
    for info, dx, size, bold in (("auxiliary1", 10, 9, False), ("label", 56, 10, True), ("comment", 110, 8, False)):
        pc.dynamic(info, dx, vcenter(size), size, bold, "AlignVCenter")
    # PLC出力ユニット部 1点分: 左から「用途│アドレス│ピン」、配線は右から出る
    po = Symbol("plc_out", "PLC出力ユニット1点(用途/アドレス/ピン)", 260, 40, 260, 20)
    po.rect(-234, -20, 230, 40)
    po.line(-104, -20, -104, 20); po.line(-49, -20, -49, 20)
    po.terminal("t", "e", -4, 0)
    s["plc_out"] = po
    for info, dx, size, bold in (("comment", -228, 8, False), ("label", -98, 10, True), ("auxiliary1", -44, 9, False)):
        po.dynamic(info, dx, vcenter(size), size, bold, "AlignVCenter")
    # FX5U用: コモンは枠の並びと COM 行で示すので欄は2つ。入力 [アドレス│用途]、出力 [用途│アドレス]
    fi = Symbol("fx_in", "FX入力1点(アドレス/用途)", 270, 32, 0, 16)
    fi.rect(4, -16, 260, 32)
    fi.line(59, -16, 59, 16)
    fi.terminal("t", "w", 4, 0)
    s["fx_in"] = fi
    fo = Symbol("fx_out", "FX出力1点(用途/アドレス)", 270, 32, 270, 16)
    fo.rect(-264, -16, 260, 32)
    fo.line(-59, -16, -59, 16)
    fo.terminal("t", "e", -4, 0)
    s["fx_out"] = fo
    # 雛形の文字: 上下中央ぞろえ。手で置いた部品も、コメントを2段にすると自動で中央に寄る
    fi.dynamic("label", 10, vcenter(10), 10, True, "AlignVCenter")
    fi.dynamic("comment", 64, vcenter(8), 8, False, "AlignVCenter")
    earth = Symbol("earth", "接地", 20, 20, 10, 2)
    earth.line(0, 0, 0, 8); earth.line(-8, 8, 8, 8); earth.line(-5, 11, 5, 11); earth.line(-2, 14, 2, 14)
    earth.terminal("n", "n", 0, 0)
    s["earth"] = earth
    pin = Symbol("module_pin", "ユニット端子", 190, 24, 0, 12)
    pin.circle(0, -4, 8); pin.terminal('t', 'w', 0, 0)
    pin.dynamic('label', 14, -7, 8); pin.dynamic('comment', 72, -7, 8)
    s['module_pin'] = pin
    # 通信コネクタ(正面から見た絵、共通部品)。端子は左に1つ(ケーブル1本ぶん)
    for name, kind, gender in (('module_rj45', 'rj45', ''), ('module_coax', 'coax_f', ''), ('module_optical', 'optical', ''),
                               ('module_dsub', 'dsub9', 'male'), ('module_dsub_f', 'dsub9', 'female'),
                               ('module_minidin', 'minidin8', 'male')):
        CONN.symbol(s, Symbol, kind, gender, name=name)
    fo.dynamic("comment", -258, vcenter(8), 8, False, "AlignVCenter")
    fo.dynamic("label", -52, vcenter(10), 10, True, "AlignVCenter")
    # 負荷: コイル(リレー・電磁接触器・電磁弁)
    lc = Symbol("load_coil", "負荷 コイル(横)", 40, 20, 20, 10)
    lc.rect(-12, -7, 24, 14); lc.line(-20, 0, -12, 0); lc.line(12, 0, 20, 0)
    lc.terminal("w", "w", -20, 0); lc.terminal("e", "e", 20, 0)
    s["load_coil"] = lc
    # リレーコイル(マスター): 接点の参照表を QElectroTech が自動で付ける
    rc = Symbol("relay_coil", "リレーコイル(横)", 40, 20, 20, 10)
    rc.parts = list(lc.parts)
    rc.terminal("w", "w", -20, 0); rc.terminal("e", "e", 20, 0)
    rc.link_type = "master"
    rc.kinds = {"type": "coil"}
    s["relay_coil"] = rc
    # 負荷: 表示灯
    ll = Symbol("load_lamp", "負荷 表示灯(横)", 40, 20, 20, 10)
    ll.circle(-8, -8, 16); ll.line(-6, -6, 6, 6); ll.line(-6, 6, 6, -6)
    ll.line(-20, 0, -8, 0); ll.line(8, 0, 20, 0)
    ll.terminal("w", "w", -20, 0); ll.terminal("e", "e", 20, 0)
    s["load_lamp"] = ll
    # 接続点
    j = Symbol("junction", "接続点", 10, 10, 5, 5)
    j.circle(-2, -2, 4, fill=True)
    for o in "nesw":
        j.terminal(o, o, 0, 0)
    s["junction"] = j
    # 点なしの接続点(線の端・曲がり角用)
    nd = Symbol("node", "接続点(点なし)", 10, 10, 5, 5)
    nd.line(-2, 0, 2, 0)
    for o in "nesw":
        nd.terminal(o, o, 0, 0)
    s["node"] = nd
    # 2極ブレーカ(横向き、極間 50)
    cb = Symbol("breaker_2p", "2極ブレーカ(横)", 40, 70, 20, 10)
    for dy in (0, 50):
        cb.line(-20, dy, -8, dy); cb.line(-8, dy, 9, dy - 7); cb.line(8, dy, 20, dy)
        cb.line(5, dy - 3, 11, dy + 3); cb.line(5, dy + 3, 11, dy - 3)
        cb.terminal(f"w{dy}", "w", -20, dy); cb.terminal(f"e{dy}", "e", 20, dy)
    cb.dashed(0, -3, 0, 47)
    s["breaker_2p"] = cb
    # 電源を受ける機器の箱(FX5U本体電源部 / DC24V電源)
    s["fx5u_power"] = box_symbol("fx5u_power", "FX5U 電源端子部", 200, 80,
                                 top=[("L", 0), ("N", 40), ("⏚", 80)],
                                 bottom=[("24+", 0), ("0V", 40)])
    # DC電源タイプの本体電源端子([+][-]、FX5UC は電源コネクタ 1/2/3)。サービス電源はない
    s["fx5_power_dc"] = box_symbol("fx5_power_dc", "FX5 電源端子部(DC)", 200, 80,
                                   top=[("+", 0), ("-", 40), ("⏚", 80)], bottom=[])
    # サーキットプロテクタ1極(縦)
    cp = Symbol("cp_1p", "サーキットプロテクタ1極(縦)", 30, 50, 10, 5)
    cp.line(0, 0, 0, 12); cp.line(0, 12, 8, 28); cp.line(0, 28, 0, 40)
    cp.line(-3, 9, 3, 15); cp.line(-3, 15, 3, 9)
    cp.terminal("n", "n", 0, 0); cp.terminal("s", "s", 0, 40)
    s["cp_1p"] = cp
    s["psu_24v"] = box_symbol("psu_24v", "DC24V電源", 160, 80,
                              top=[("L", 0), ("N", 40), ("⏚", 80)],
                              bottom=[("+V", 0), ("-V", 40)])
    for key, supply, service in (("iqr_ac", "AC", False), ("iqr_ac_24", "AC", True), ("iqr_dc", "DC", False)):
        s[key] = iqr_power_symbol(key, supply, service)
    # CPU は形名だけ(電池・USB・SD などは欄外の表に書き、幅を広げない)
    for lan_on in (False, True):
        for usb_on in (False, True):
            key = "iqr_cpu" + ("_lan" if lan_on else "") + ("_usb" if usb_on else "")
            s[key] = iqr_cpu_symbol(key, lan_on, usb_on)
    return s


def iqr_cpu_symbol(key, lan_on, usb_on, h=380, joined=False):
    """Q / iQ-R の CPU。配線するのは LAN だけ: Ethernet 付きは RJ-45 を描き、下へ線を出す端子を付ける。
    USB は絵だけ(配線しない)。電池・SD などは欄外の表に書く。h: ユニットの高さ"""
    c = Symbol(key, "iQ-R CPU", 80, h + 4 if lan_on else h, 10, 5)
    if joined:
        # 一体のネットワーク部との内部境界は、構成ページ側で点線を描く。
        c.line(-10, 0, 70, 0); c.line(-10, 0, -10, h); c.line(-10, h, 70, h)
    else:
        c.rect(-10, 0, 80, h)
    # 実機と同じく縦向き(90° 回す)
    if usb_on:
        n = len(c.parts)
        draw_usb_minib(c, 16, h - 112)
        rotate90(c, n, 30, h - 112)
        c.label(round(30 - text_w("USB (Mini-B)", 7) / 2, 1), h - 134, "USB (Mini-B)", 7)   # 箱の中央
    if lan_on:
        n = len(c.parts)
        draw_rj45(c, 10, h - 45)
        rotate90(c, n, 30, h - 45)
        c.label(round(30 - text_w("Ethernet", 7) / 2, 1), h - 72, "Ethernet", 7)
        c.terminal("lan", "s", 30, h - 25)
    c.dynamic("label", -6, 20, 9, True)
    return c


def iqr_netpart_symbol(key, ports, w, h=380):
    """RnENCPU のネットワーク部(RJ71EN71 相当、CPU の右の1スロット)。RJ-45 を縦向きに並べ、下へ線を出す端子を付ける"""
    c = Symbol(key, "iQ-R CPU ネットワーク部", w, h + 4, 0, 0)
    cx = w / 2
    pitch = 75 if h >= 300 else 52                     # 2段構成(ユニットが低い)ときは詰める
    for i, port in enumerate(reversed(ports)):          # 上から P1、P2 の順に見えるよう下から置く
        y = h - 45 - i * pitch
        n = len(c.parts)
        draw_rj45(c, cx - 20, y)
        rotate90(c, n, cx, y)
        c.label(round(cx - text_w(port, 7) / 2, 1), y - 27, port, 7)
        c.terminal(port.lower(), "s", cx, y + 20)
    return c


def iqr_power_symbol(key, supply, service, h=380, labels=None, additional_terminals=None):
    """iQ-R 電源ユニット。端子は実機の端子台と同じ順に左側に並べ、左から配線する
    (出典: BCN-P5999-0188-F 主端子台は上から ERR → FG → LG → 電源入力)。h: ユニットの高さ"""
    iqps = Symbol(key, "iQ-R 電源", 70, h, 10, 5)
    iqps.rect(-10, 0, 70, h)                # ベースに差した形(縦長)。幅は端子名が入るだけ
    power = [("ac1", "AC"), ("ac2", "AC")] if supply == "AC" else [("dcplus", "+24V"), ("dcminus", "24G")]
    pins = [("err1", "ERR"), ("err2", "ERR"), ("fg", "FG"), ("lg", "LG")] + power + \
           ([("+24V", "+24V"), ("24G", "24G")] if service else [])
    pins += [(item['key'],item['label']) for item in (additional_terminals or [])]
    step = min(30, (h - 70) / len(pins))
    for i, (name, text) in enumerate(pins):
        if labels and i < len(labels):
            text = labels[i]
        y = round(50 + i * step, 1)
        # 端子は ○ で描く(入出力ユニットの端子と同じ)
        iqps.circle(-10, y - 4, 8); iqps.terminal(name, "w", -10, y)
        iqps.label(4, y + 4, text, 8)
    iqps.dynamic("label", 0, 20, 10, True)
    return iqps


def fx5_body_symbol(key, ac, analog, rs485, service, service_pairs=1, power_connector=False, board_supported=True, board_spec=None):
    """用途ごとに端子を分け、配線を左側から引き出す。"""
    power = [("L", "電源 L"), ("N", "電源 N"), ("⏚", "接地")] if ac else [("+", "電源 +24V"), ("-", "電源 0V"), ("⏚", "接地")]
    if power_connector:
        power = [("1", "電源 +24V (赤)"), ("2", "電源 0V (黒)"), ("3", "接地 (緑)")]
    sections = [
        ("電源入力（コネクタ）" if power_connector else "電源入力", power, 3),
        ("センサ電源出力", ([("24V", "+24V"), ("0V", "0V")] +
                       ([("24V_2", "+24V"), ("0V_2", "0V")] if service_pairs == 2 else [])) if service else [], 4),
        ("本体アナログ入出力", [("V1+", "入力 CH1 (+)"), ("V2+", "入力 CH2 (+)"),
          ("V- IN", "入力 CH1/CH2 (-)"), ("V+ OUT", "出力 CH1 (+)"), ("V- OUT", "出力 CH1 (-)")] if analog else [], 5),
        ("RS-485", [("RDA", "RXD+"), ("RDB", "RXD-"), ("SDA", "TXD+"),
                    ("SDB", "TXD-"), ("SG", "GND")] if rs485 else [], 5),
        ("Ethernet", [("RJ-45", "RJ-45")], 4),
    ]
    # 全機種で同じ配置にする(利用者の指示: 共通化できる簡略図)。端子のない欄は空けておく
    top = 52
    height = top + sum(20 + 24 * capacity for _, _, capacity in sections) + 15
    cpu = Symbol(key, "FX5本体 電源・アナログ・通信", 350, height, 20, 5)
    cpu.section_names = [h.split("（")[0] for h, pins, _ in sections if pins]
    cpu.rect(-20, 0, 350, height)
    if board_supported and board_spec:
        cpu.rect(175, 52, 155, 268)
        cpu.label(183, 68, "拡張ボード", 8, True)
        cpu.dynamic("auxiliary10", 183, 80, 8)
        if board_spec:
            for i, port in enumerate(board_spec['ports']):
                connector = board_spec['connection'] in ('D-sub 9pin オス', 'MINI-DIN 8pin メス')
                y = (130 if board_spec['connection'] == 'D-sub 9pin オス' else 190) if connector else 155 + i * 21
                wire_start = 318 if board_spec['connection'] == 'D-sub 9pin オス' else 309 if connector else 330 if board_spec['connection'] == '端子台' else 338
                if board_spec['connection'] == '端子台':
                    cpu.circle(322, y - 4, 8)
                elif not connector:
                    cpu.rect(330, y - 4, 8, 8)
                cpu.terminal('board:' + str(i), 'e', wire_start, y)
                if not connector:
                    label_x = 295 if len(port) <= 5 else 210
                    if board_spec['connection'] == '端子台':
                        label_x = 316 - text_w(port, 8)
                    cpu.label(label_x, y + 4, port, 8)
                    signal = board_spec.get('signal_labels', {}).get(port)
                    if signal:
                        cpu.label(185 if len(signal) > 6 else 245, y + 4, signal, 7 if len(signal) > 6 else 8)
            if board_spec['connection'] == 'D-sub 9pin オス':
                draw_dsub9(cpu, 226, 130, male=True)
                cpu.label(231, 175, 'D-sub 9pin オス', 7)
                signals = board_spec['connector']['signals']
                for row in range(10):
                    y = 184 + row * 13
                    cpu.rect(183, y, 140, 13)
                    cpu.line(211, y, 211, y + 13, thin=True)
                    cpu.label(188, y + 10, str(row) if row else 'No.', 7)
                    cpu.label(219, y + 10, signals.get(str(row), 'NC') if row else '信号', 7)
            elif board_spec['connection'] == 'MINI-DIN 8pin メス':
                draw_minidin8(cpu, 265, 190)
                cpu.label(220, 235, 'MINI-DIN 8pin メス', 7)
    for heading, pins, capacity in sections:
        box_height = 20 + 24 * capacity
        if pins:
            right = 310 if heading == "Ethernet" else 155
            cpu.line(-20, top, right, top, thin=True)
            cpu.line(-20, top + box_height, right, top + box_height, thin=True)
            cpu.line(right, top, right, top + box_height, thin=True)
            cpu.label(-4 if heading == "Ethernet" else 4, top + 15, heading, 8, True)
        if heading == "Ethernet":
            y = top + 44
            cpu.terminal("RJ-45", "w", 0, y)
            draw_rj45(cpu, 0, y)
            cpu.label(5, y + 38, "RJ-45", 8)
            cpu.line(65, top, 65, top + box_height, thin=True)
            cpu.status_y = top + 8
            top += box_height
            continue
        for i, (name, description) in enumerate(pins):
            y = top + 23 + i * 24
            cpu.circle(-20, y - 4, 8)
            cpu.terminal(name, "w", -20, y)
            cpu.label(-6, y + 4, {"V- IN": "V-", "V+ OUT": "V+", "V- OUT": "V-", "24V_2": "24V", "0V_2": "0V"}.get(name, name), 8)
            if description != name:
                cpu.label(48, y + 4, description, 8)
        top += box_height
    cpu.dynamic("auxiliary4", 75, cpu.status_y, 8)
    cpu.dynamic("auxiliary2", 135, cpu.status_y, 8)
    cpu.dynamic("auxiliary3", 135, cpu.status_y + 19, 8)
    cpu.dynamic("auxiliary5", 75, cpu.status_y + 38, 8)
    cpu.dynamic("auxiliary1", 135, cpu.status_y + 38, 8)
    sd_in_board = board_spec and board_spec['connection'] == 'SDカードスロット'
    cpu.dynamic("auxiliary6", 183 if sd_in_board else 75, 125 if sd_in_board else cpu.status_y + 57, 8)
    cpu.dynamic("auxiliary7", 227 if sd_in_board else 135, 125 if sd_in_board else cpu.status_y + 57, 7 if sd_in_board else 8)
    cpu.dynamic("auxiliary8", 227 if sd_in_board else 135, 144 if sd_in_board else cpu.status_y + 76, 7 if sd_in_board else 8)
    cpu.dynamic("label", 10, 26, 10, True)
    return cpu


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


# ------------------------------------------------------------ 区分参照(コイル ⇔ 接点)
# 位置は「ページ-区画」(例 5-C16 = 5ページ、C行・16列の升目)。
#   コイル側: レーンの外の「コイル接点」欄に、a/b の2行 × 極の列の表を置き、使った接点の位置を書く
#   接点側  : 接点の左上に (コイルの位置) を書く
# リレーの形式は出力CSVの「形式」列、なければ project.json の relay_default。
# 形式ごとの極は project.json の relay_types で上書きできる。
DEFAULT_RELAY_TYPES = {}  # parts/control以下の標準記号向け機種定義からuse_unitsで設定する。

COIL_KINDS = {"RY", "MC", "CR", "KM", "R", "リレー"}
XREF = {"devices": set(), "count": {}, "types": {}, "relay_type": {}}
LINES = {"n": 0, "coil": {}, "contacts": []}


def xref_reset(devices):
    XREF["devices"] = set(devices)   # count / relay_type は xref_devices() が入れる
    LINES["n"] = 0
    LINES["coil"] = {}
    LINES["contacts"] = []


def line_no(p, x, y):
    """行の通し番号(区分参照では図面に書かない)"""
    LINES["n"] += 1
    return LINES["n"]


ZONE_ROWS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ZONE = {"col_start": 1}
# DC電源の線の名前(レーンの見出し・線番・コモンの接続先に使う)。project.json の power.P_name / power.N_name で変更可
LANE = {"P": "P24", "N": "N24"}


def zone(page_no, x, y):
    """図面の升目(行=英字、列=数字)。QElectroTech の枠の区画と同じ数え方"""
    # 枠の左に行見出し(幅20)、上に列見出し(高さ20)があるので、その分を引く。
    # 列番号の始まり(0 か 1)は QElectroTech 本体の設定に合わせる(project.json の zone_col_start)
    col = int((x - 20) // COL_SIZE) + ZONE["col_start"]
    return f"{page_no}-{ZONE_ROWS[int((y - 20) // ROW_SIZE)]}{col}"


def contact_key(dev, ab):
    return "contact_b" if ab == "b" else "contact_a"


def load_key(dev, load):
    load = load.strip().upper()
    if load in LAMP_KINDS:
        return "load_lamp"
    if dev and dev in XREF["devices"]:
        return "relay_coil"
    return "load_coil"


def coil_texts(kind, y, ref_dx):
    """リレーコイル: 機器番号をコイルの上と「コイル接点」欄の先頭に書く"""
    if kind == "relay_coil":
        return [("label", -24, y, 8, True)]
    return [("label", -24, y, 8, True)]


REF_LINE = 11
REF_WN, REF_WC = 34, 26   # 参照表: 機器番号欄の幅、1極の欄の幅


def is_relay_row(r):
    return load_key(r["機器番号"].strip(), r.get("負荷", "")) == "relay_coil"


def row_ys(rows, y, pitch, last=None):
    """各行の Y。コイル接点欄でリレーの欄(機器番号+全極)が重ならないよう、必要な行だけ下げる。
    last: 直前のリレー欄の (Y, 極数)。戻り値: (Yのリスト, 次の行のY, last)"""
    ys = []
    for r in rows:
        if is_relay_row(r):
            if last is not None:
                y = max(y, last[0] + 26)          # 表は2行(24)なので通常は下げない
            last = (y, XREF["count"].get(r["機器番号"].strip(), 1))
        ys.append(y)
        y += pitch
    return ys, y, last


def register_coil(p, dev, n, ref_x, y, coil_x):
    if dev in XREF["devices"]:
        LINES["coil"][dev] = (p, n, ref_x, y, coil_x)
        pending = getattr(p, "ref_pending", {})
        if ref_x in pending:
            _write_ref_header(p, ref_x, pending.pop(ref_x))


def register_contact(p, dev, ab, n, x, y):
    if dev:
        LINES["contacts"].append((p, dev, ab, n, x, y))


def ctext(p, cx, cy, t, size, bold=False):
    """(cx, cy) を中心に文字を置く(MS ゴシックの文字幅と文字枠の余白から計算)"""
    w = text_w(t, size) + 2 * TEXT_MARGIN
    hgt = size * PX_PER_PT + 2 * TEXT_MARGIN
    p.text(round(cx - w / 2, 1), round(cy - hgt / 2, 1), t, size, bold)


# 中継端子台(コネクタ→端子台変換ユニット)の端子名。出典: MELSEC iQ-R I/O Module User's Manual
# (SH-081247ENG) 付録1 A6TBXY36 各部の名称: 端子は 0〜F・10〜1F(ユニットの何点目か、16進)と 24V・0V。
# 24V は ユニットの B1/B2、0V は A1/A2 につながる(接続図より)。
RELAY_TB = {
    "A6TBXY36": {"point": lambda i: f"{i % 32:X}", "pins": {"B1": "24V", "B2": "24V", "A1": "0V", "A2": "0V"}},
}


def tb_label(uc, i=None, pin=None):
    """中継端子の名前。i: ユニットの何点目(0〜)、pin: ユニット側の端子(COM・電源の行)。
    中継端子台の形名がわからないときは空欄(QET で記入)"""
    tb = RELAY_TB.get(str(uc.get("relay", "")).strip().upper())
    if not tb:
        return ""
    if pin is not None:
        return tb["pins"].get(str(pin).strip().upper(), "")
    return tb["point"](i)


def ref_header(p, ref_x, y):
    """「コイル接点」の見出し。参照表を描くコイルがあるときだけ出す(register_coil で書く)"""
    if not hasattr(p, "ref_pending"):
        p.ref_pending = {}
    p.ref_pending[ref_x] = y


def _write_ref_header(p, ref_x, y):
    """「コイル接点」の見出し。右半分は参照表と同じく図枠の右端に寄せる"""
    t = "コイル接点"
    x = ref_x if ref_x <= HALF_W else 20 + BORDER_COLS * COL_SIZE - 4 - text_w(t, 7) - 2 * TEXT_MARGIN
    p.text(round(x, 1), y, t, 7)


def write_references(page_no):
    """全ページの番号が決まったあとで、極の割り当てと参照を書く。page_no: Page → ページ番号。
    戻り値: エラーのリスト"""
    errs, used = [], {}
    for p, dev, ab, n, x, y in LINES["contacts"]:
        if dev not in LINES["coil"]:
            continue
        rt = XREF["types"][XREF["relay_type"][dev]]
        k = len(used.setdefault(dev, []))
        if k >= len(rt["poles"]):
            errs.append(f"{dev}({XREF['relay_type'][dev]}): 接点が {len(rt['poles'])} 極を超えています"
                        f"({zone(page_no(p), x, y)})")
            continue
        used[dev].append((k, ab, zone(page_no(p), x, y)))
        if rt.get('contacts'):
            contact = rt['contacts'][k]
            p.text(x - 25, y + 7, '/'.join(contact['common']), 6)
            p.text(x + 16, y + 7, '/'.join(contact['nc' if ab == 'b' else 'no']), 6)
        cp, _, _, cy, cx = LINES["coil"][dev]                           # コイル本体の位置
        p.text(x - 74, y - 25, f"({zone(page_no(cp), cx, cy)})", 7)   # 接点の左上: コイルの位置
    for dev, (p, n, ref_x, y, _) in LINES["coil"].items():
        rtn = XREF["relay_type"][dev]
        np_ = len(XREF["types"][rtn]["poles"])
        coil = XREF['types'][rtn].get('coil')
        if coil:
            cx = LINES['coil'][dev][4]
            p.text(cx - 30, y + 7, coil['terminals'][0], 6)
            p.text(cx + 20, y + 7, coil['terminals'][1], 6)
        # [機器番号/形式 │ a/b │ 極1 … 極n]。2行(a・b)でコイルの行の中に収まる
        x0, y0, wn, wl, wc, h = ref_x, y - 12, REF_WN, 10, REF_WC, 12
        width = wn + wl + wc * np_
        if ref_x > HALF_W:                          # 右半分は図枠の右端に寄せる
            x0 = 20 + BORDER_COLS * COL_SIZE - 4 - width
        right = x0 + width
        for i in range(3):
            p.line(x0, y0 + i * h, right, y0 + i * h, 0.6)
        for xx in [x0, x0 + wn, x0 + wn + wl] + [x0 + wn + wl + wc * j for j in range(1, np_ + 1)]:
            p.line(xx, y0, xx, y0 + 2 * h, 0.6)
        # 文字はすべて升目の中央にそろえる
        ctext(p, x0 + wn / 2, y0 + h / 2, dev, 7, True)
        ctext(p, x0 + wn / 2, y0 + h * 1.5, rtn, 6)
        ctext(p, x0 + wn + wl / 2, y0 + h / 2, "a", 7)
        ctext(p, x0 + wn + wl / 2, y0 + h * 1.5, "b", 7)
        for k, ab, zn in used.get(dev, []):
            ctext(p, x0 + wn + wl + wc * k + wc / 2, y0 + h * (0.5 if ab == "a" else 1.5), zn, 6)
    return errs


def xref_devices(pages_rows, cfg):
    """コイル(出力の負荷がリレー類)と、入力の接点の両方に出てくる機器番号。形式と極数も決める"""
    XREF["types"] = dict(DEFAULT_RELAY_TYPES, **cfg.get("relay_types", {}))
    default = cfg.get("relay_default", "MY4N")
    coils, contacts, rtype = set(), set(), {}
    output_devices = {}
    for page_index, (pg, rows) in enumerate(pages_rows, 1):
        if pg["kind"] in ("power", "fx5analog", "iqranalog", "qanalog", "remoteanalog", "qcomm", "iqrcomm", "fxcomm", "fx5body", "iqrbody", "qbody", "remotebody", "remoteiolink", "gotbody", "gotoption", "remotepulse", "mxbody", "mxio", "inverter") or rows is None:
            continue
        if pg["kind"] in ("fx5u", "fx5ext"):
            outs, ins = rows["out"], rows["in"]
        else:
            outs, ins = [], []
            for uc, urows in iqr_units(pg, rows):
                (ins if configured_unit(uc)["io"] == "in" else outs).extend(urows)
        for r in outs:
            d = r["機器番号"].strip()
            if d:
                location = f"ページ設定{page_index} {pg.get('model', '')} {r.get('アドレス', '')}".strip()
                if d in output_devices:
                    raise SystemExit(f"出力の機器番号重複: {d} ({output_devices[d]} / {location})")
                output_devices[d] = location
            if r.get("負荷", "").strip().upper() in COIL_KINDS and d:
                coils.add(d)
                rtype[d] = (r.get("形式") or "").strip() or default
        for r in ins:
            if r["機器番号"].strip():
                contacts.add(r["機器番号"].strip())
    devs = coils & contacts
    XREF["relay_type"] = {}
    XREF["count"] = {}
    for d in devs:
        t = rtype[d]
        if t not in XREF["types"]:
            raise SystemExit(f"{d}: リレー形式 {t} が relay_types にありません")
        XREF["relay_type"][d] = t
        XREF["count"][d] = len(XREF["types"][t]["poles"])
    return devs


# ------------------------------------------------------------ IOコメント(2段)
PX_PER_PT = 96 / 72   # QElectroTech は 96dpi 換算でポイントを図面の単位にする


VCENTER_SYMBOLS = {"plc_in", "plc_out", "fx_in", "fx_out", "fx_in_dual", "fx_out_dual"}   # 文字を上下中央ぞろえにする部品
TEXT_MARGIN = 4      # QElectroTech の文字枠の余白(上下それぞれ)


def vcenter(size, lines=1):
    """行の中心(y=0)に文字の中心を合わせるための y。MS ゴシックの行の高さは 1em"""
    return round(-(2 * TEXT_MARGIN + lines * size * PX_PER_PT) / 2, 1)


def text_w(t, size):
    """MS ゴシックの文字幅(全角 = 1em、半角 = 0.5em)。半角カナも 0.5em"""
    em = size * PX_PER_PT
    return sum(em * (0.5 if (ord(c) < 0x2000 or 0xFF61 <= ord(c) <= 0xFF9F) else 1.0) for c in t)


def comment_value(r):
    """CSVの信号名。「|」で改行を指定できる(指定がなければ欄の幅で自動改行)"""
    return r["信号名"].strip().replace("|", "\n")


def wrap2(value, width, size):
    """欄の幅を超える行を折り返す(最大2段)"""
    if "\n" not in value and text_w(value, size) <= width:
        return value
    out = []
    for line in value.split("\n"):
        cur = ""
        for c in line:
            if cur and text_w(cur + c, size) > width:
                out.append(cur)
                cur = c
            else:
                cur += c
        out.append(cur)
    if len(out) > 2:
        out = out[:1] + ["".join(out[1:])]
    return "\n".join(out)


def comment_text(value, x, width, size, row_h):
    """1段でも2段でも同じ大きさで、行の高さの中央にそろえる"""
    n = min(value.count("\n") + 1, 2)
    return ("comment", x, vcenter(size, n), size, False)


# ------------------------------------------------------------ 図面の組み立て
ORIENT_NUM = dict(n=0, e=1, s=2, w=3)


def io_text_cell(key, info):
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
                max_size = size
                for size in dict.fromkeys((max_size,9,8,7,6)):
                    if size>max_size:
                        continue
                    # Qtの等幅フォントのピクセル丸めを考慮し、実際の折返し行数に合わせる。
                    pixel_ratio=math.ceil(size*PX_PER_PT/2)/(size*PX_PER_PT/2)
                    lines=sum(max(1,math.ceil(text_w(line,size)*pixel_ratio/(tw-2*TEXT_MARGIN))) for line in value.split('\n'))
                    row_height=32 if key.startswith('fx_') else ROW_PITCH
                    # 折り返せる位置(空白・「/」の後)の無い記号(24VDC_1 など)は、途中で切れないよう1行に収まる大きさにする
                    single='\n' not in value and not re.search(r'\s|/(?=\D)',value.strip())
                    if single and lines>1 and size>6:
                        continue
                    if lines<=2 and lines*size*PX_PER_PT+2*TEXT_MARGIN<=row_height:
                        break
                ty = vcenter(size,min(lines,2))
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
LAMP_KINDS = {"PL", "L", "LAMP", "表示灯"}


def page_note(p, pg, pw):
    """図面の注記は入れない(中継端子台の番号が未確認の箇所は「?」で示す)"""
    return


def lane_labels(p, X):
    ctext(p, X["P"], 44, LANE["P"], 8, True)      # 線の真上に中央ぞろえ
    ctext(p, X["N"], 44, LANE["N"], 8, True)


def output_lane_labels(p, left_x, left_name, right_x, right_name):
    gap = right_x-left_x
    size = next((s for s in (8,7,6) if (text_w(left_name,s)+text_w(right_name,s))/2+6 <= gap),6)
    ctext(p,left_x,44,left_name,size,True)
    ctext(p,right_x,44,right_name,size,True)


def iqr_halves(pg, rows):
    """ページの半分ごとに (ユニット設定, その半分の行, ユニット内の何番目の半分, 1点目の番号)"""
    halves = []
    for uc, urows in iqr_units(pg, rows):
        unit = configured_unit(uc)
        per_half = 8 if unit.get('paired_com_pins') else 16
        halves += [(uc, urows[i:i + per_half], i // per_half, i) for i in range(0, unit["points"], per_half)]
    return halves


def is_slot_unit(kind, model):
    return kind in ('qcomm','iqrcomm','qbody','iqrbody','qanalog','iqranalog','qmixed','iqrmixed') or str(model).upper().startswith(('Q','R'))


def identity_cells(p, config, x, width, top, bottom):
    p.identity_headers = True
    rack = is_slot_unit(config.get('kind',''),config['model'])
    number = str(config.get('slot','') if rack else config.get('unit_no',config.get('slot','')))
    cuts=(x,x+width*0.33,x+width*0.57,x+width)
    values=(('スロットNo. ' if rack else 'ユニットNo. ')+number,config.get('tag',''),config['model'])
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


def iqr_input_half(p, off, uc, rows, h, base):
    unit = configured_unit(uc)
    X = {k: v + off for k, v in IN_X.items()}
    pin_title = '端子' if unit.get('terminal_block') or unit['points']<32 else 'ピン'
    io_table_header(p,uc,X['plc']+4,250,(45,100),(pin_title,'アドレス','用途'))
    p.text(X["tb"] - 18, 46, uc.get("tb_name", "TB"), 8, True)
    voltage = str(uc.get("input_voltage", unit.get("input_voltages", [""])[0]))
    lanes = {"P": "P" + voltage, "N": "N" + voltage} if voltage else LANE
    ctext(p, X["P"], 44, lanes["P"], 8, True)
    ctext(p, X["N"], 44, lanes["N"], 8, True)

    common_lane = "N" if unit.get("input_common") == "negative" else "P"
    contact_lane = "P" if common_lane == "N" else "N"
    p_top = p.place("junction", X[common_lane], LANE_TOP_Y)
    prev_n = p.place("junction", X[contact_lane], LANE_TOP_Y)
    for i, r in enumerate(rows):
        y = ROW_Y0 + ROW_PITCH * (2 if unit.get('paired_com_pins') else 1) * i
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        ab = "b" if r.get("接点", "").strip().lower() == "b" else "a"
        n = line_no(p, X["num"], y)
        nj = p.place("junction", X[contact_lane], y)
        p.wire(prev_n, "s", nj, "n")
        prev_n = nj
        ct = p.place(contact_key(dev, ab), X["contact"], y, label=dev, texts=[("label", -24, -27, 8, True)])
        register_contact(p, dev, ab, n, X["contact"], y)
        tb = p.place("tb_terminal", X["tb"], y, label=r.get("端子台番号", "").strip() or tb_label(uc, base + i),
                     texts=[("label", -10, -22, 7, False)])
        cv = wrap2(comment_value(r), 136, 8)
        pin = r.get("コネクタピン", "").strip() or unit["pins"][base + i]
        plc = p.place("plc_in", X["plc"], y, label=addr, comment=cv, infos={"auxiliary1": pin},
                      texts=IN_TEXTS[:2] + [comment_text(cv, 108, 142, 8, ROW_PITCH)])
        p.wire(nj, "e", ct, "w")
        p.wire(ct, "e", tb, "w", num=r.get("線番", "").strip() or addr, show=True)
        p.wire(tb, "e", plc, "t")

        if unit.get('paired_com_pins'):
            label = unit['paired_com_labels'][base + i]
            lane = 'P' if label == 'COM A' else 'N'
            cy = y + ROW_PITCH
            common = p.place('plc_in', X['plc'], cy, label=label, comment='コモン',
                             infos={'auxiliary1':unit['paired_com_pins'][base+i]}, texts=IN_TEXTS)
            tb_com = p.place('tb_terminal',X['tb'],cy,label='',texts=[('label',-10,-22,7,False)])
            j = p.place('junction',X[lane],cy)
            previous = p_top if lane == common_lane else prev_n
            p.wire(previous,'s',j,'n')
            if lane == common_lane: p_top=j
            else: prev_n=j
            p.wire(j,'e',tb_com,'w',num=lanes[lane])
            p.wire(tb_com,'e',common,'t',num=lanes[lane],show=True)

    if unit.get('paired_com_pins'):
        if h == 0:
            for k, (label,pin,lane) in enumerate(unit['paired_power_terminals']):
                y = COM_Y + k * ROW_PITCH
                plc = p.place('plc_in',X['plc'],y,label=label,comment='外部電源',infos={'auxiliary1':pin},texts=IN_TEXTS)
                j = p.place('junction',X[lane],y)
                previous = p_top if lane == common_lane else prev_n
                p.wire(previous,'s',j,'n')
                if lane == common_lane: p_top=j
                else: prev_n=j
                p.wire(j,'e',plc,'t',num=lanes[lane],show=True)
        p.extend_lanes([X['P'],X['N']])
        return

    if unit.get("manual_input_power"):
        if not unit.get('extra_terminals'):
            p.text(X["plc"] + 5, COM_Y + 12, unit.get("manual_input_note", "入力電源は構成ページを参照"), 8)
        p.extend_lanes([X["P"], X["N"]])
        return
    # 一つの端子しかない32点機種は、同一端子を左右に重複して描かない。
    if unit["points"] == 32 and len(unit["common"]) == 1 and h == 1:
        p.extend_lanes([X["P"], X["N"]])
        return
    coms = unit["common"] if unit.get("common_group_points") == 8 or unit.get("show_all_commons") else [unit["common"][min(h, len(unit["common"]) - 1)]]
    terminals = [("COM", pin, common_lane) for pin in coms]
    if unit.get("input_power_pin"):
        terminals.append(("V+", unit["input_power_pin"], "P"))
    for i, (label, pin, lane) in enumerate(terminals):
        label = unit.get('terminal_names', {}).get(pin, label)
        y = COM_Y + i * ROW_PITCH
        line_no(p, X["num"], y)
        pj = p.place("junction", X[lane], y)
        previous = p_top if lane == common_lane else prev_n
        p.wire(previous, "s", pj, "n")
        if lane == common_lane: p_top = pj
        else: prev_n = pj
        tb = p.place("tb_terminal", X["tb"], y, label=tb_label(uc, pin=pin),
                     texts=[("label", -14, -22, 7, False)])
        plc = p.place("plc_in", X["plc"], y, label=label, comment='外部電源' if label == 'V+' else 'コモン',
                      infos={"auxiliary1": pin}, texts=IN_TEXTS)
        p.wire(pj, "e", tb, "w", num=lanes[lane])
        p.wire(tb, "e", plc, "t", num=lanes[lane], show=True)
    p.extend_lanes([X["P"], X["N"]])


def iqr_output_half(p, off, uc, rows, h, base):
    """シンク: 負荷は P24 から、V+ → P24、COM → N24。リレー: 負荷は N24 へ、COM → P24"""
    unit = configured_unit(uc)
    if unit["out"] == "independent_relay":
        return iqr_independent_relay_half(p, off, uc, rows, base)
    X = {k: v + off for k, v in OUT_X.items()}
    sink = unit["out"] == "sink"
    load_lane, other_lane = ("P", "N") if sink else ("N", "P")   # 内側(X["P"])が負荷側のレーン
    pin_title = '端子' if unit.get('terminal_block') or unit['points']<32 else 'ピン'
    io_table_header(p,uc,X['plc']-234,230,(130,185),('用途','アドレス',pin_title))
    ref_header(p, X["ref"], 46)
    p.text(X["tb"] - 18, 46, uc.get("tb_name", "TB"), 8, True)
    output_lane_labels(p,X['P'],LANE[load_lane],X['N'],LANE[other_lane])

    prev_in = p.place("junction", X["P"], LANE_TOP_Y)      # 負荷側のレーン
    prev_out = p.place("junction", X["N"], LANE_TOP_Y)     # 反対側のレーン
    ys, _, _ = row_ys(rows, ROW_Y0, ROW_PITCH)
    if unit.get('paired_com_pins'):
        ys = [ROW_Y0 + ROW_PITCH * 2 * i for i in range(len(rows))]
    if ys[-1] > COM_Y - 40:                       # 入りきらなければ間隔を広げない
        ys = [ROW_Y0 + ROW_PITCH * i for i in range(len(rows))]
    for i, (r, y) in enumerate(zip(rows, ys)):
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        kind = load_key(dev, r.get("負荷", ""))
        cv = wrap2(comment_value(r), 116, 8)
        pin = r.get("コネクタピン", "").strip() or unit["pins"][base + i]
        plc = p.place("plc_out", X["plc"], y, label=addr, comment=cv, infos={"auxiliary1": pin},
                      texts=[comment_text(cv, -228, 122, 8, ROW_PITCH)] + OUT_TEXTS[1:])
        tb = p.place("tb_terminal", X["tb"], y, label=r.get("端子台番号", "").strip() or tb_label(uc, base + i),
                     texts=[("label", -10, -22, 7, False)])
        ld = p.place(kind, X["load"], y, label=dev, infos={"auxiliary1": dev},
                     texts=coil_texts(kind, -27, X["ref"] - X["load"]))
        register_coil(p, dev, line_no(p, X["num"], y), X["ref"], y, X["load"])
        p.wire(plc, "t", tb, "w")
        p.wire(tb, "e", ld, "w", num=r.get("線番", "").strip() or addr, show=True)
        if unit.get('paired_com_pins'):
            # 出力ごとの COM 端子(負荷電源の分配端子。内部で電源端子につながる)。負荷は Y とこの端子の間につなぐ
            cy = y + ROW_PITCH
            label = unit.get('paired_com_labels', ['COM'] * unit['points'])[base+i]
            common = p.place('plc_out', X['plc'], cy, label=label, comment='コモン',
                             infos={'auxiliary1': unit['paired_com_pins'][base + i]}, texts=OUT_TEXTS)
            common_tb = p.place('tb_terminal', X['tb'], cy, label='', texts=[('label', -12, -22, 7, False)])
            p.wire(common, 't', common_tb, 'w')
            # 右向き端子同士を1本で結ぶ。折り返し用のダミー端子は段差・短い枝線の原因になる。
            p.wire(ld, 'e', common_tb, 'e')
        else:
            pj = p.place("junction", X["P"], y)
            p.wire(prev_in, "s", pj, "n")
            prev_in = pj
            p.wire(ld, "e", pj, "w")

    # 電源・コモンの行: (表示, 端子, つなぐレーン)
    vplus = unit.get("vplus", "")
    com = unit["com"]
    if isinstance(vplus, list): vplus = vplus[h if unit.get("common_by_half") else h // 2]
    if isinstance(com, list): com = com[h if unit.get("common_by_half") else h // 2]
    if unit["out"] == "source":
        com_rows = [("COM", vplus, "P"), ("0V", com, "N")] if unit["points"] <= 16 else (
            [("COM", vplus, "P")] if h % 2 == 0 else [("0V", com, "N")])
        com_rows = [row for row in com_rows if row[1]]
    elif sink:
        com_rows = []
        if vplus and (unit.get("common_by_half") or unit["points"] <= 16 or h % 2 == 0):
            com_rows.append(("V+", vplus, "P"))
        if com and (unit.get("common_by_half") or unit["points"] <= 16 or h % 2 == 1):
            com_rows.append(("COM", com, "N"))
    else:
        com_rows = [("COM", unit["com"], "P")] if unit["com"] else []
    if unit.get('paired_com_pins') and h:
        com_rows = []
    elif unit.get('paired_com_pins'):
        com_rows = unit.get('paired_power_terminals', [('DC24V', vplus, 'P'), ('DC24G', com, 'N')])
    if unit.get("manual_output_note"):
        p.text(X["plc"] - 230, COM_Y + 12, unit["manual_output_note"], 8)
    if sum(len(pin.split('/')) for _, pin, _ in com_rows) <= 2:
        com_rows = [(lab, part, lane) for lab, pin, lane in com_rows for part in pin.split('/') if part]
    for k, (lab, pin, lane) in enumerate(com_rows):
        lab = unit.get('terminal_names', {}).get(pin, lab)
        y = COM_Y + ROW_PITCH * k          # 2行(V+ と COM)のときは下に続けて並べる
        line_no(p, X["num"], y)
        key = 'plc_out'
        contacts = pin.split('/')
        if len(contacts) > 1:
            key = 'plc_out_common_' + str(len(contacts))
            if key not in p.sym:
                s = copy.deepcopy(p.sym['plc_out']); s.name = key
                s.terminals = {k: (u(), o, x, y) for k, (_, o, x, y) in s.terminals.items()}
                for ti in range(1, len(contacts)):
                    dy = ti * 10
                    s.circle(-10, dy - 3, 6)
                    s.terminal('t' + str(ti + 1), 'e', -4, dy)
                p.sym[key] = s
        plc = p.place(key, X["plc"], y, label=lab, comment='外部電源' if lab in ('V+', '0V', 'DC24V', 'DC24G') else 'コモン',
                      infos={"auxiliary1": pin}, texts=OUT_TEXTS)
        tb = p.place("tb_terminal", X["tb"], y, label=tb_label(uc, pin=pin), texts=[("label", -12, -22, 7, False)])
        p.wire(plc, "t", tb, "w")
        if lane == load_lane:
            j = p.place("junction", X["P"], y)
            p.wire(prev_in, "s", j, "n")
            prev_in = j
        else:
            j = p.place("junction", X["N"], y)
            p.wire(prev_out, "s", j, "n")
            prev_out = j
        p.wire(tb, "e", j, "w", num=LANE[lane], show=True)
    p.extend_lanes([X["P"], X["N"]])


def iqr_independent_relay_half(p, off, uc, rows, base):
    """各接点の両端を別々に表示し、外部側のみ配線する。"""
    unit = configured_unit(uc)
    X = {k: v + off for k, v in OUT_X.items()}
    io_table_header(p,uc,X['plc']-234,230,(130,185),('用途','アドレス','端子'))
    p.text(X["tb"] - 18, 46, uc.get("tb_name", "TB"), 8, True)
    ref_header(p, X["ref"], 46)
    output_lane_labels(p,X['P'],LANE['N'],X['N'],LANE['P'])
    prev_n = p.place("junction", X["P"], LANE_TOP_Y)
    prev_p = p.place("junction", X["N"], LANE_TOP_Y)
    for i, r in enumerate(rows):
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        y = ROW_Y0 + i * ROW_PITCH * 2
        p.rect(X["plc"] - 106, y - 15, X["plc"] + 24, y + ROW_PITCH + 15, dash=False)
        feed = p.place("plc_out", X["plc"], y, label=addr, comment="外部電源",
                       infos={"auxiliary1": unit["feed_pins"][base + i]}, texts=OUT_TEXTS)
        ftb = p.place("tb_terminal", X["tb"], y, label="", texts=[("label", -10, -22, 7, False)])
        pj = p.place("junction", X["N"], y)
        p.wire(prev_p, "s", pj, "n"); prev_p = pj
        p.wire(feed, "t", ftb, "w"); p.wire(ftb, "e", pj, "w", num=LANE["P"], show=True)
        y += ROW_PITCH
        cv = wrap2(comment_value(r), 116, 8)
        plc = p.place("plc_out", X["plc"], y, label=addr, comment=cv,
                      infos={"auxiliary1": unit["pins"][base + i]},
                      texts=[comment_text(cv, -228, 122, 8, ROW_PITCH)] + OUT_TEXTS[1:])
        tb = p.place("tb_terminal", X["tb"], y, label=r.get("端子台番号", "").strip() or tb_label(uc, base + i),
                     texts=[("label", -10, -22, 7, False)])
        kind = load_key(dev, r.get("負荷", ""))
        ld = p.place(kind, X["load"], y, label=dev, infos={"auxiliary1": dev},
                     texts=coil_texts(kind, -27, X["ref"] - X["load"]))
        register_coil(p, dev, line_no(p, X["num"], y), X["ref"], y, X["load"])
        nj = p.place("junction", X["P"], y)
        p.wire(prev_n, "s", nj, "n"); prev_n = nj
        p.wire(plc, "t", tb, "w"); p.wire(tb, "e", ld, "w", num=r.get("線番", "").strip() or addr, show=True)
        p.wire(ld, "e", nj, "w")
    p.extend_lanes([X["P"], X["N"]])


def build_iqr_page(rows, pg, cfg, symbols, halves=None):
    p = Page(symbols)
    for (uc, hrows, h, base), off in zip(halves if halves is not None else iqr_halves(pg, rows), HALVES):
        unit = configured_unit(uc)
        if unit["io"] == "in":
            iqr_input_half(p, off, uc, hrows, h, base)
        else:
            iqr_output_half(p, off, uc, hrows, h, base)
        if h == 0:
            X = {k:v+off for k,v in (IN_X if unit['io']=='in' else OUT_X).items()}
            for i, (pin, name) in enumerate(unit.get('extra_terminals', [])):
                y = ROW_Y0 + ROW_PITCH * (len(hrows) + i)
                key, texts = ('plc_in', IN_TEXTS) if unit['io']=='in' else ('plc_out', OUT_TEXTS)
                terminal = p.place(key, X['plc'], y, label=name,
                                   comment='コモン' if name.startswith('COM') else '外部電源',
                                   infos={'auxiliary1':pin}, texts=texts)
                tb = p.place('tb_terminal', X['tb'], y, label=tb_label(uc, pin=pin),
                             texts=[('label',-12,-22,7,False)])
                if unit['io']=='in':
                    p.wire(tb,'e',terminal,'t')
                else:
                    p.wire(terminal,'t',tb,'w')
    return p


build_input_page = build_output_page = build_iqr_page


# ============================================================ FX5U(本体ねじ端子台)
# 入出力アドレスは8進数(X0〜X7, X10〜X17 …)。本体の端子名 = アドレス。
# 入力は全点 S/S 共通。出力はコモンごとに区切る。
# confirmed=False の確認状況は機種定義で管理する
def octal(prefix, n):
    return [f"{prefix}{oct(i)[2:]}" for i in range(n)]


def _groups(spec):
    """spec: [(コモン番号, 先頭8進, 点数)] → [(番号, [Yアドレス…])]"""
    out = []
    for no, start, n in spec:
        base = int(start, 8)
        out.append((no, [f"Y{oct(base + k)[2:]}" for k in range(n)]))
    return out


# ============================================================ ユニット定義の読み込み
# PLC・HMIの機種ごとの定義をparts以下から集める。
UNITS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts")


def read_unit_definitions(path=UNITS_DIR):
    """機種別ファイルを集め、重複や不正な定義を拒否する。"""
    categories = ("kv_io", "inverter", "remote_pulse", "mx_cpu", "mx_io", "remote_mixed", "remote_io", "remote_analog", "remote_iolink", "iqr_mixed", "q_mixed", "iqr_q", "fx5_cpu", "fx5_ext", "fx5_analog", "fx5_comm", "fx5_board", "iqr_cpu", "iqr_power", "iqr_base", "iqr_analog", "iqr_comm", "q_cpu", "q_power", "q_base", "q_analog", "q_comm", "got_body", "got_option", "power_supply", "standard_device")
    categories = ("unit_diagram",) + categories
    d = {category: {} for category in categories}
    if not os.path.isdir(path):
        raise ValueError(f"機種定義フォルダがありません: {path}")
    for root, _, files in os.walk(path):
        for name in sorted(files):
            if not name.lower().endswith(".json"):
                continue
            file = os.path.join(root, name)
            with open(file, encoding="utf-8-sig") as f:
                item = json.load(f)
            if not isinstance(item, dict) or item.get("category") not in d or not isinstance(item.get("model"), str) or not item["model"].strip() or not isinstance(item.get("definition"), dict):
                raise ValueError(f"機種定義が不正です: {file}")
            category, model = item["category"], item["model"].upper()
            if model in d[category]:
                raise ValueError(f"機種定義が重複しています: {model} ({file})")
            definition = item["definition"]
            if category == "fx5_cpu" and (len(definition.get("variants", [])) != 1 or
                    (definition.get("base", "") + definition["variants"][0]).upper() != model):
                raise ValueError(f"CPUのbaseとvariantsが形名と一致しません: {file}")
            if category == "fx5_ext" and definition.get("variants") != [""]:
                raise ValueError(f"増設機種のvariantsは空文字1件にしてください: {file}")
            d[category][model] = definition
    if not any(d.values()):
        raise ValueError(f"機種定義がありません: {path}")
    return d


def _checked_signal_pins(model, spec):
    pins = spec['pins']
    pins = list(PIN_PRESETS[pins]) if isinstance(pins, str) else list(pins)
    if len(pins) != spec['points']:
        raise SystemExit(f"機種定義: {model} の pins の数({len(pins)})が points({spec['points']})と合いません")
    seen_pins = set()
    for pin in pins:
        if not isinstance(pin, str) or not pin.strip():
            raise ValueError(f"機種定義: {model} の信号端子は空でない文字列にしてください")
        normalized = pin.strip().upper()
        if normalized in seen_pins:
            raise ValueError(f"機種定義: {model} の信号端子が重複しています: {pin}")
        seen_pins.add(normalized)
    return pins


def load_units(path=UNITS_DIR):
    """機種別JSONを読み、内部形式に変換する。"""
    d = read_unit_definitions(path)
    io_units = {}
    for model, u in {**d.get("iqr_q", {}), **d.get("remote_io", {})}.items():
        u = dict(u)
        u['pins'] = _checked_signal_pins(model, u)
        io_units[model.upper()] = u
    for category in ('q_mixed', 'iqr_mixed', 'remote_mixed'):
        for model, spec in d[category].items():
            for direction in ('input', 'output'):
                spec[direction]['pins'] = _checked_signal_pins(f'{model} {direction}', spec[direction])
    cpus = {m.upper(): dict(inputs=s["inputs"], groups=_groups([tuple(x) for x in s["outputs"]]),
                            confirmed=s.get("confirmed", False), base=s.get("base", m).upper(),
                            variants=[v.upper() for v in s.get("variants", [])],
                            in_common=s.get("in_common", "S/S"), series=s.get("series", ""),
                            battery_supported=s.get("battery_supported"), usb_port=s.get("usb_port"),
                            analog=s.get("analog"), rs485=s.get("rs485"), service=s.get("service"),
                            physical_io=s.get("physical_io", {}))
            for m, s in d.get("fx5_cpu", {}).items()}
    exts = {m.upper(): dict(inputs=s["inputs"], groups=[tuple(x) for x in s["outputs"]],
                            confirmed=s.get("confirmed", False),
                            in_common=s.get("in_common", "S/S"), sink_only=s.get("sink_only", False),
                            variants=[v.upper() for v in s.get("variants", [])], physical_io=s.get("physical_io", {}))
            for m, s in d.get("fx5_ext", {}).items()}
    # 長い形名を先に照合する(FX5-16EY が FX5-16EX などに誤って当たらないように)
    cpus = dict(sorted(cpus.items(), key=lambda kv: -len(kv[0])))
    exts = dict(sorted(exts.items(), key=lambda kv: -len(kv[0])))
    boards = {**d['fx5_board'], **{m: s for m, s in d['fx5_comm'].items() if s.get('form') == 'board'}}
    from renderers.unit_diagrams import validate
    for model, spec in d["unit_diagram"].items():
        validate(model, spec)
    return io_units, cpus, exts, d["fx5_analog"], d["iqr_cpu"], d["iqr_power"], d["iqr_base"], d["iqr_analog"], d["q_cpu"], d["q_power"], d["q_base"], d["q_analog"], d["q_comm"], d["iqr_comm"], d["fx5_comm"], d["q_mixed"], d["iqr_mixed"], d["remote_mixed"], boards, d["remote_analog"], d["remote_iolink"], d["got_body"], d["got_option"], d["standard_device"], d["remote_pulse"], d["mx_cpu"], d["mx_io"], d["inverter"], d["kv_io"], d["unit_diagram"]


def use_units(path=UNITS_DIR):
    global IO_UNITS, FX5U_SPECS, FX5_EXT_SPECS, FX5_ANALOG_SPECS, IQR_CPU, IQR_POWER, IQR_BASE, IQR_ANALOG, Q_CPU, Q_POWER, Q_BASE, Q_ANALOG, Q_COMM, IQR_COMM, FX5_COMM, Q_MIXED, IQR_MIXED, REMOTE_MIXED, FX5_BOARDS, REMOTE_ANALOG, REMOTE_IOLINK, GOT_BODY, GOT_OPTION, STANDARD_DEVICES, REMOTE_PULSE, MX_CPU, MX_IO, INVERTERS, KV_IO, UNIT_DIAGRAMS, DEFAULT_RELAY_TYPES
    IO_UNITS, FX5U_SPECS, FX5_EXT_SPECS, FX5_ANALOG_SPECS, IQR_CPU, IQR_POWER, IQR_BASE, IQR_ANALOG, Q_CPU, Q_POWER, Q_BASE, Q_ANALOG, Q_COMM, IQR_COMM, FX5_COMM, Q_MIXED, IQR_MIXED, REMOTE_MIXED, FX5_BOARDS, REMOTE_ANALOG, REMOTE_IOLINK, GOT_BODY, GOT_OPTION, STANDARD_DEVICES, REMOTE_PULSE, MX_CPU, MX_IO, INVERTERS, KV_IO, UNIT_DIAGRAMS = load_units(path)
    MX_IO = {**MX_CPU, **MX_IO}
    DEFAULT_RELAY_TYPES = {model: {"poles": list(range(1, len(spec["contacts"]) + 1)), "contacts": spec["contacts"], "coil": spec["coil"]}
                           for model, spec in STANDARD_DEVICES.items() if spec.get("device_type") == "relay"}


use_units()


def fx_spec(pg):
    """FX5 のページ設定から、入力アドレス・出力グループ・出力方式を決める"""
    m = pg["model"].upper().replace(" ", "")
    kind = "source" if "/ESS" in m or "/DSS" in m else ("relay" if ("R/" in m or m.endswith("R")) else "sink")
    if pg["kind"] == "fx5ext":
        key = next((k for k, e in FX5_EXT_SPECS.items() if m.startswith(k) and m[len(k):] in e["variants"]), None)
        if key is None:
            raise SystemExit(f"未対応の増設ユニットです: {pg['model']}(対応: {', '.join(FX5_EXT_SPECS)})")
        e = FX5_EXT_SPECS[key]
        if e["variants"] and m[len(key):] not in e["variants"]:
            raise SystemExit(f"未対応の増設ユニットです: {pg['model']}"
                             f"(対応: {', '.join(key + v for v in e['variants'])})")
        xs, ys0 = int(str(pg.get("x_start", "0")), 8), int(str(pg.get("y_start", "0")), 8)
        inputs = [f"X{oct(xs + i)[2:]}" for i in range(e["inputs"])]
        groups, k = [], 0
        for no, n in e["groups"]:
            groups.append((no, [f"Y{oct(ys0 + k + i)[2:]}" for i in range(n)]))
            k += n
        return dict(key=key, kind=kind, inputs=inputs, groups=groups, confirmed=e["confirmed"],
                    in_common=e["in_common"], sink_only=e["sink_only"], physical_io=e["physical_io"])
    key, var = fx_cpu_lookup(m)
    if key is None:
        raise SystemExit(f"未対応の機種です: {pg['model']}\n対応する形名: {', '.join(fx_cpu_models())}")
    sp = FX5U_SPECS[key]
    return dict(key=key, kind=fx_out_kind(var), power=fx_power(var), inputs=octal("X", sp["inputs"]),
                groups=sp["groups"], confirmed=sp["confirmed"], in_common=sp["in_common"], physical_io=sp["physical_io"])


def fx_cpu_models():
    """FX5本体の登録形名をすべて返す"""
    return [sp["base"] + v for sp in FX5U_SPECS.values() for v in sp["variants"]]


def fx_cpu_lookup(m):
    """形名 → (定義キー, variant)。base + variant と完全一致したものだけ"""
    for k, sp in FX5U_SPECS.items():
        for v in sp["variants"]:
            if m == sp["base"] + v:
                return k, v
    return None, None


def fx_out_kind(var):
    """'R/ES' → relay、'T/DSS' → source、'T/D' → sink"""
    if var.startswith("R"):
        return "relay"
    return "source" if "SS" in var.split("/", 1)[-1] else "sink"


def fx_power(var):
    """'/ES' 'ESS' → AC、'/D' '/DS' '/DSS' → DC"""
    return "AC" if var.split("/", 1)[-1].startswith("E") else "DC"


def model_power(model):
    """電源ページ用。FX5 本体の形名なら AC/DC を返す(わからなければ AC)"""
    _, var = fx_cpu_lookup(model.upper().replace(" ", ""))
    return fx_power(var) if var else "AC"


FX_PITCH, FX_Y0, FX_GAP, FX_YMAX = 32, 86, 10, 745
FX_IN_X = dict(num=24, outer=45, inner=72, contact=160, plc=275)  # 入力半分: 左にレーン
FX_OUT_X = dict(num=24, plc=294, load=398, inner=446, outer=466, ref=474)  # 出力半分: レーンの外に参照欄
FX_IN_TEXTS = [("label", 10, vcenter(10), 10, True)]          # 用途は comment_text() で2段対応
FX_OUT_TEXTS = [("label", -52, vcenter(10), 10, True)]


def fx_model_info(model):
    """'FX5U-32MR/ES' → (系列キー, 出力方式)(本体用)"""
    sp = fx_spec({"kind": "fx5u", "model": model})
    return sp["key"], sp["kind"]


def fx_signal_symbol(p, pg, io):
    key = 'fx_' + io
    if fx_spec(pg).get('physical_io', {}).get(io + 'put_signal_contacts', 1) == 2:
        dual = key + '_dual'
        if dual not in p.sym:
            s = copy.deepcopy(p.sym[key])
            s.name = dual
            s.terminals = {k: (u(), orient, x, y) for k, (_, orient, x, y) in s.terminals.items()}
            circle_x = 4 if io == 'in' else -10
            s.circle(circle_x, -3, 6)
            s.circle(circle_x, 7, 6)
            if io == 'in':
                s.dyn = [(name, x + 6 if name == 'label' else x, *rest) for name, x, *rest in s.dyn]
            s.terminal('t2', 'w' if io == 'in' else 'e', 4 if io == 'in' else -4, 10)
            p.sym[dual] = s
        return dual
    return key


def fx_input_commons(pg, rows):
    spec = fx_spec(pg)
    physical = spec.get('physical_io', {}).get('input_commons')
    if not physical:
        return []
    base = int(str(pg.get('x_start', '0')), 8) if pg['kind'] == 'fx5ext' else 0
    addresses = {int(r['アドレス'].strip()[1:], 8) - base for r in rows}
    return [c for c in physical if any(int(c['start'], 8) <= a < int(c['start'], 8) + c['points'] for a in addresses)]


def fx_input_half(p, off, rows, pg, cfg, show_ss, mode):
    """入力の半分: 外側レーン ─ (接点 ─ [S/S│X│用途])。sink: 接点→N、S/S→P"""
    X = {k: v + off for k, v in FX_IN_X.items()}
    sw_lane, ss_lane = ("N", "P") if mode == "sink" else ("P", "N")
    lane_x = {sw_lane: X["inner"], ss_lane: X["outer"]}
    pw = cfg["power"]
    for name, x in lane_x.items():
        ctext(p, x, 44, LANE[name], 8, True)
    io_table_header(p,pg,X['plc']+4,260,(55,),('アドレス','用途'))

    prev = p.place("junction", X["inner"], LANE_TOP_Y)
    ss_top = p.place("junction", X["outer"], LANE_TOP_Y)
    y = FX_Y0
    for r in rows:
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        kind = contact_key(dev, r.get("接点", "").strip().lower())
        j = p.place("junction", X["inner"], y)
        p.wire(prev, "s", j, "n")
        prev = j
        ct = p.place(kind, X["contact"], y, label=dev, texts=[("label", -24, -25, 8, True)])
        n = line_no(p, X["num"], y)
        register_contact(p, dev, "b" if r.get("接点", "").strip().lower() == "b" else "a", n, X["contact"], y)
        cv = wrap2(comment_value(r), 190, 8)
        key = fx_signal_symbol(p, pg, "in")
        label_texts = [(name, x + 6 if key.endswith('_dual') else x, *rest) for name, x, *rest in FX_IN_TEXTS]
        plc = p.place(key, X["plc"], y, label=addr, comment=cv,
                      texts=label_texts + [comment_text(cv, 64, 196, 8, FX_PITCH)])
        p.wire(j, "e", ct, "w")
        p.wire(ct, "e", plc, "t", num=r.get("線番", "").strip() or addr, show=True)
        y += FX_PITCH
    physical = fx_input_commons(pg, rows)
    if physical or show_ss:
        y += FX_GAP
        commons = physical or [{'name': fx_spec(pg).get('in_common', 'S/S'), 'contacts': 1}]
        previous = ss_top
        for common in commons:
            for contact in range(common['contacts']):
                line_no(p, X['num'], y)
                sj = p.place('junction', X['outer'], y)
                p.wire(previous, 's', sj, 'n')
                previous = sj
                cm = 'コモン'
                plc = p.place('fx_in', X['plc'], y, label=common['name'], comment=cm,
                              texts=FX_IN_TEXTS + [('comment', 64, vcenter(8), 8, False)])
                p.wire(sj, 'e', plc, 't', num=LANE[ss_lane], show=False)
                y += FX_PITCH
    p.extend_lanes([X["inner"], X["outer"]])


def fx_output_half(p, off, groups, pg, cfg, kind, relay_com_to):
    """出力の半分: ([用途│Y│COMn] ─ 負荷) ─ レーン。グループごとに COM 行。グループの間は少し空ける"""
    X = {k: v + off for k, v in FX_OUT_X.items()}
    if kind == "sink":
        load_lane, com_lane, com_fmt = "P", "N", "COM{}"
    elif kind == "source":
        load_lane, com_lane, com_fmt = "N", "P", "+V{}"
    else:
        com_lane = relay_com_to
        load_lane = "N" if com_lane == "P" else "P"
        com_fmt = "COM{}"
    pw = cfg["power"]
    output_lane_labels(p,X['inner'],LANE[load_lane],X['outer'],LANE[com_lane])
    io_table_header(p,pg,X['plc']-264,260,(205,),('用途','アドレス'))

    prev_l = p.place("junction", X["inner"], LANE_TOP_Y)
    prev_c = p.place("junction", X["outer"], LANE_TOP_Y)
    y, last = FX_Y0, None
    ref_header(p, X["ref"], 46)
    for gi, (no, rows) in enumerate(groups):
        com = com_fmt.format(no)
        ys, y_com, last = row_ys(rows, y, FX_PITCH, last)
        y_top = ys[0] - FX_PITCH // 2 - 3
        for r, y in zip(rows, ys):
            addr = r["アドレス"].strip().upper()
            dev = r["機器番号"].strip()
            lk = load_key(dev, r.get("負荷", ""))
            cv = wrap2(comment_value(r), 190, 8)
            plc = p.place(fx_signal_symbol(p, pg, "out"), X["plc"], y, label=addr, comment=cv,
                          texts=FX_OUT_TEXTS + [comment_text(cv, -258, 196, 8, FX_PITCH)])
            ld = p.place(lk, X["load"], y, label=dev, infos={"auxiliary1": dev},
                         texts=coil_texts(lk, -25, X["ref"] - X["load"]))
            register_coil(p, dev, line_no(p, X["num"], y), X["ref"], y, X["load"])
            j = p.place("junction", X["inner"], y)
            p.wire(prev_l, "s", j, "n")
            prev_l = j
            p.wire(plc, "t", ld, "w", num=r.get("線番", "").strip() or addr, show=True)
            p.wire(ld, "e", j, "w")
        y = y_com
        # 同名でも物理的な接続口はそれぞれ描く。
        physical = next((c for c in fx_spec(pg).get('physical_io', {}).get('output_commons', []) if c['group'] == no), {})
        count = physical.get('contacts', 1)
        for contact in range(count):
            line_no(p, X['num'], y)
            cj = p.place('junction', X['outer'], y)
            p.wire(prev_c, 's', cj, 'n')
            prev_c = cj
            cm = 'コモン'
            plc = p.place('fx_out', X['plc'], y, label=physical.get('name', com), comment=cm,
                          texts=FX_OUT_TEXTS + [('comment', -258, vcenter(8), 8, False)])
            p.wire(plc, 't', cj, 'w', num=LANE[com_lane], show=False)
            y += FX_PITCH
        y += FX_GAP
    p.extend_lanes([X["inner"], X["outer"]])


def fx_pack(groups, rows_by_addr, physical=None):
    """出力グループを半分ずつに詰める(グループは分割しない)"""
    halves, cur = [], []
    y, last = FX_Y0, None
    for no, addrs in groups:
        rows = [rows_by_addr[a] for a in addrs]
        _, com_y, last2 = row_ys(rows, y, FX_PITCH, last)     # このグループの COM 行の Y
        extra = (next((c['contacts'] for c in (physical or {}).get('output_commons', []) if c['group'] == no), 1) - 1) * FX_PITCH
        if cur and com_y + extra > FX_YMAX:
            halves.append(cur)
            cur = []
            _, com_y, last2 = row_ys(rows, FX_Y0, FX_PITCH, None)
        cur.append((no, rows))
        last, y = last2, com_y + extra + FX_PITCH + FX_GAP
    if cur:
        halves.append(cur)
    return halves



def fx_split_inputs(rows):
    """入力を半ページずつに分ける(半分に入るのは20点まで)"""
    if len(rows) <= 20:
        return [rows] if rows else []
    return [rows[i:i + 16] for i in range(0, len(rows), 16)]


def build_fx5u_pages(pg, cfg, symbols, in_rows, out_rows):
    sp = fx_spec(pg)
    kind = sp["kind"]
    mode = pg.get("input_mode", "sink")
    relay_to = pg.get("relay_com_to", "P")
    by_addr = {r["アドレス"].strip().upper(): r for r in out_rows}
    out_halves = fx_pack(sp["groups"], by_addr, sp.get("physical_io")) if sp["groups"] else []
    in_halves = fx_split_inputs(in_rows) if in_rows else []
    name = pg.get("title_prefix", "PLC" if pg["kind"] == "fx5u" else pg["model"] + " ")

    def rng(rows):
        return f"{rows[0]['アドレス'].strip()}〜{rows[-1]['アドレス'].strip()}"

    pages = []
    # 入力・出力がそれぞれ半分に収まれば1ページにまとめる
    if len(in_halves) + len(out_halves) <= 2 and len(in_halves) <= 1 and len(out_halves) <= 1:
        p = Page(symbols)
        parts = []
        if in_halves:
            fx_input_half(p, 0, in_rows, pg, cfg, True, mode)
            parts.append(rng(in_rows))
        if out_halves:
            fx_output_half(p, HALF_W if in_halves else 0, out_halves[0], pg, cfg, kind, relay_to)
            parts.append(rng(out_rows))
        label = "入出力" if in_halves and out_halves else ("入力" if in_halves else "出力")
        pages.append((f"{name}{label} {'・'.join(parts)}", p))
        return pages
    for start in range(0, len(in_halves), 2):
        p = Page(symbols)
        segment = in_halves[start:start + 2]
        for i, hr in enumerate(segment):
            fx_input_half(p, HALF_W * i, hr, pg, cfg, start == 0 and i == 0, mode)
        pages.append((f"{name}入力 {rng(segment[0] + segment[-1])}", p))
    # 出力ページ: グループ単位で左右に詰め、入りきらなければ次ページ
    for i in range(0, len(out_halves), 2):
        p = Page(symbols)
        fx_output_half(p, 0, out_halves[i], pg, cfg, kind, relay_to)
        if i + 1 < len(out_halves):
            fx_output_half(p, HALF_W, out_halves[i + 1], pg, cfg, kind, relay_to)
        segs = out_halves[i:i + 2]
        first, last = segs[0][0][1][0]["アドレス"].strip(), segs[-1][-1][1][-1]["アドレス"].strip()
        pages.append((f"{name}出力 {first}〜{last}", p))
    return pages


def fx_single_half(pg, in_rows, out_rows):
    """入力だけ・出力だけで半分に収まるユニットなら、その描き方を返す(左右に2台並べるため)"""
    if pg["kind"] != "fx5ext" or (in_rows and out_rows):
        return None
    if in_rows:
        return ("in", in_rows) if len(fx_split_inputs(in_rows)) == 1 else None
    if not out_rows:
        return None
    sp = fx_spec(pg)
    halves = fx_pack(sp["groups"], {r["アドレス"].strip().upper(): r for r in out_rows}, sp.get("physical_io")) if sp["groups"] else []
    return ("out", halves[0]) if len(halves) == 1 else None


def fx_draw_single_half(p, off, pg, cfg, single):
    """fx_single_half() の結果を半分(off)に描く。戻り値: 図面名称に使う文字"""
    sp = fx_spec(pg)
    io, data = single
    if io == "in":
        fx_input_half(p, off, data, pg, cfg, True, pg.get("input_mode", "sink"))
        first, last = data[0]["アドレス"].strip(), data[-1]["アドレス"].strip()
        return f"{pg['model']} 入力 {first}〜{last}"
    fx_output_half(p, off, data, pg, cfg, sp["kind"], pg.get("relay_com_to", "P"))
    first, last = data[0][1][0]["アドレス"].strip(), data[-1][1][-1]["アドレス"].strip()
    return f"{pg['model']} 出力 {first}〜{last}"


def fx_expected(pg):
    sp = fx_spec(pg)
    return sp["inputs"], [a for _, addrs in sp["groups"] for a in addrs]


def slot_summary(module, is_q):
    """スロットの箱に書く種類と点数(例 入力32点、アナログ入力4ch、CC-Link IE)"""
    if module in IO_UNITS and IO_UNITS[module].get("io"):
        u = IO_UNITS[module]
        return ("入力" if u["io"] == "in" else "出力") + f"{u['points']}点"
    mixed = Q_MIXED if is_q else IQR_MIXED
    if module in mixed:
        spec = mixed[module]
        return f"入力{spec['input']['points']}点\n出力{spec['output']['points']}点"
    analog = Q_ANALOG if is_q else IQR_ANALOG
    if module in analog:
        dirs = set(analog[module]["channels"])
        kind = "入力" if dirs == {"入力"} else "出力" if dirs == {"出力"} else "入出力"
        return f"アナログ{kind} {len(analog[module]['channels'])}ch"
    comm = Q_COMM if is_q else IQR_COMM
    if module in comm:
        return comm[module]["network"]
    return ""


# 先頭アドレスの自動割付(GX Works の既定と同じく、スロット順に詰めて割り付ける)
EMPTY_SLOT_POINTS = 16      # 空きスロットの点数(ページ設定 empty_slot_points で変更)
INTELLI_POINTS = {"analog": 16, "comm": 32}   # アナログは16点、通信・インテリユニットは32点として数える


def slot_definition(module, is_q):
    for definitions in ((Q_ANALOG, Q_COMM) if is_q else (IQR_ANALOG, IQR_COMM)):
        if module in definitions:
            return definitions[module]
    return {}


def slot_points(module, is_q, empty_points):
    """スロットが使う点数と、アドレスの種類(X / Y / X/Y)。空きは empty_points"""
    if not module:
        return empty_points, ""
    if module in IO_UNITS and IO_UNITS[module].get("io"):
        u = IO_UNITS[module]
        return u["points"], "X" if u["io"] == "in" else "Y"
    mixed = Q_MIXED if is_q else IQR_MIXED
    if module in mixed:
        m = mixed[module]
        return max(m["input"]["points"], m["output"]["points"]), "X/Y"
    spec = slot_definition(module, is_q)
    if spec.get("occupied_io_points"):
        return spec["occupied_io_points"], "X/Y"
    if module in (Q_ANALOG if is_q else IQR_ANALOG):
        return INTELLI_POINTS["analog"], "X/Y"
    return INTELLI_POINTS["comm"], "X/Y"


IQR_IO_LIMIT = 4096   # iQ-R の入出力点数(X/Y 0〜FFF)


def slot_assignments(pg):
    """iQ-R / Q 構成のスロットごとの先頭XY。各段の module_starts(16進。空欄は自動)の指定を優先し、
    指定の無いスロットは前のスロットの次から詰める(GX Works の割付と同じ考え方)。指定値は直さない。
    戻り値: (段ごとのスロット一覧, 入力エラー, 警告)。スロットは {start, points, head, manual, reserved, module, tag, slot_no, net}"""
    is_q = pg["kind"] == "qbody"
    cpus, bases = (Q_CPU, Q_BASE) if is_q else (iqr_cpu_positions(), IQR_BASE)
    cpu = str(pg.get("model", "")).upper()
    try:
        empty_points = int(pg.get("empty_slot_points", EMPTY_SLOT_POINTS))
    except (TypeError, ValueError):
        empty_points = EMPTY_SLOT_POINTS
    stages, errors, warnings, ranges = [], [], [], []
    address, slot_no = 0, 0
    for s, (stage, base, _, modules) in enumerate(body_stages(pg)):
        config = pg if s == 0 else pg["extensions"][s - 1]
        starts = config.get("module_starts", [])
        tags = config.get("module_tags", [])
        if not isinstance(starts, list) or any(not isinstance(v, str) for v in starts):
            errors.append(f"{stage}の先頭XY(module_starts)は文字列の配列で指定してください")
            starts = []
        slots = []
        netpart = cpus.get(cpu, {}).get("network_part") if s == 0 else None
        offset = netpart.get("slots", 1) if netpart else 0
        for i in range(bases.get(base, {}).get("slots", 0)):
            if i < offset:
                points = netpart.get("points", 32)
                slots.append({"start": address, "points": points, "head": "X/Y", "manual": False, "reserved": False,
                              "module": "", "tag": "", "slot_no": slot_no, "net": True})
                ranges.append((address, address + points - 1, f"スロット{slot_no}(ネットワーク部)"))
                address += points
                slot_no += 1
                continue
            j = i - offset
            module = str(modules[j]).upper() if j < len(modules) and modules[j] else ""
            previous = str(modules[j - 1]).upper() if j and j - 1 < len(modules) and modules[j - 1] else ""
            reserved = slot_definition(previous, is_q).get("slots", 1) == 2
            points, head = (0, "") if reserved else slot_points(module, is_q, empty_points)
            given = starts[j].strip() if j < len(starts) else ""
            manual = bool(given)
            if manual:
                try:
                    value = int(given, 16)
                    if value < 0:
                        raise ValueError
                except ValueError:
                    errors.append(f"スロット{slot_no}の先頭XYは16進数で指定してください: {given}")
                    value = address
                if reserved:
                    warnings.append(f"スロット{slot_no}は2スロットユニットの占有部のため、先頭XYの指定は使われません")
                    manual = False
                else:
                    address = value
                    if value % 16:
                        warnings.append(f"スロット{slot_no}の先頭XY {given} は16点(10h)単位ではありません")
            label = f"スロット{slot_no}({module or ('占有' if reserved else '空き')})"
            if points:
                ranges.append((address, address + points - 1, label))
            tag = str(tags[j]).strip() if module and j < len(tags) and tags[j] else ""
            slots.append({"start": address, "points": points, "head": head, "manual": manual, "reserved": reserved,
                          "module": module, "tag": tag, "slot_no": slot_no, "net": False})
            address += points
            slot_no += 1
        stages.append(slots)
    ranges.sort()
    for (a0, a1, la), (b0, b1, lb) in zip(ranges, ranges[1:]):
        if b0 <= a1:
            warnings.append(f"{la} と {lb} のXYが重なっています({b0:03X}〜{min(a1, b1):03X})")
    limit = cpus.get(cpu, {}).get("io_points") if is_q else IQR_IO_LIMIT
    if limit and ranges and max(r[1] for r in ranges) >= limit:
        last = max(ranges, key=lambda r: r[1])
        warnings.append(f"{last[2]} のXY(〜{last[1]:03X})がCPUの入出力点数 {limit}点(〜{limit - 1:03X})を超えています")
    return stages, errors, warnings


def page_start_warnings(pages):
    """入出力ページの先頭アドレスが、構成ページで同じ形名・タグのスロットの先頭XYと違うときの警告。"""
    warnings = []
    slots = []
    for pg in pages:
        if pg.get("kind") in ("iqrbody", "qbody"):
            try:
                stages, _, _ = slot_assignments(pg)
            except (KeyError, TypeError, AttributeError):
                continue
            slots += [slot for stage in stages for slot in stage if slot["module"]]
    for pg in pages:
        if pg.get("kind") not in ("input", "output", "qmixed", "iqrmixed") or not pg.get("model"):
            continue
        model, tag = str(pg["model"]).upper(), str(pg.get("tag", "")).strip()
        matches = [s for s in slots if s["module"] == model and (not tag or s["tag"] == tag)]
        if len(matches) != 1:
            continue
        try:
            start = int(str(pg.get("start", "0")), 16)
        except ValueError:
            continue
        if start != matches[0]["start"]:
            name = tag or model
            warnings.append(f"{name} のページの先頭アドレス {start:X} が構成のスロット{matches[0]['slot_no']}({matches[0]['start']:X})と違います")
    return warnings


def body_stages(pg):
    """基本ベースと増設ベースの並び: [(段の名前, ベース形名, 電源形名 or "", ユニットの並び)]"""
    stages = [("基本", pg["base_model"].upper(), pg["power_model"].upper(), pg.get("modules", []))]
    for i, ext in enumerate(pg.get("extensions", []), 1):
        stages.append((f"増設{i}段", ext["base_model"].upper(), str(ext.get("power_model", "")).upper(),
                       ext.get("modules", [])))
    return stages


def cpu_option_error(pg, spec):
    """CPUで確認済みの装着可否と型式候補を検証する。"""
    if str(pg.get('model', '')).startswith('MXR'):
        if pg.get('power_model') == 'R62P' and (pg['model'].startswith('MXR500') or pg.get('base_model') not in ('R33B', 'R35B')):
            return 'このMX-R・基本ベースの組合せではR62Pを使用できません'
    batteryless = pg.get('batteryless', '要確認')
    if batteryless not in ('有', '無', '要確認'):
        return 'バッテリレスは有・無・要確認から選んでください'
    if batteryless == '有':
        if not spec.get('batteryless_supported'):
            return 'このCPUにはバッテリレスオプションを装着できません'
        if pg.get('memory_cassette') == '有':
            return 'バッテリレスと拡張SRAMは同時に装着できません'
    for key,title in (('sd_card','SDカード'),('memory_card','メモリカード'),('memory_cassette','拡張SRAM')):
        state=pg.get(key,'要確認')
        if state not in ('有','無','要確認'):
            return title+'は有・無・要確認から選んでください'
        model=pg.get(key+'_model','')
        if not isinstance(model,str):
            return title+'の型式は文字列で指定してください'
        model=model.strip()
        if spec.get(key+'_supported') is not True and (state=='有' or model):
            return title+'はこのCPUに装着できません'
        candidates=spec.get(key+'_models',[])
        if key=='sd_card':
            # SDは自由入力も残すが、他CPU専用と確認済みの純正型式は流用しない。
            known={m for cpu in (*Q_CPU.values(),*IQR_CPU.values()) for m in cpu.get('sd_card_models',[])}
            if model.upper() in known and model.upper() not in candidates:
                return title+'の型式がこのCPUの対応候補にありません'
        elif model and model not in candidates:
            return title+'の型式がこのCPUの対応候補にありません'
    if 'battery_models' in spec:
        model=pg.get('battery_model','')
        if not isinstance(model,str):
            return 'バッテリの型式は文字列で指定してください'
        if model.strip() and model.strip() not in spec['battery_models']:
            return 'バッテリの型式がこのCPUの対応候補にありません'
    return ''


def iqr_cpu_positions():
    return {**IQR_CPU, **{m: s for m, s in IQR_COMM.items() if s.get('mount_position') == 'cpu_slot'}}


def build_iqr_body_page(pg, symbols):
    """iQ-R / Q の電源・CPU・ベースとスロットを、実機の並びに近い形で描く。
    増設ベースがあれば段ごとに下へ並べる(1ページ2段まで。入らなければ次のページ)。戻り値: [(名称, ページ)]"""
    is_q = pg["kind"] == "qbody"
    series = "MELSEC-Q" if is_q else "MX-R" if pg["model"].upper().startswith("MXR") else "iQ-R"
    cpus, powers, bases = (Q_CPU, Q_POWER, Q_BASE) if is_q else (iqr_cpu_positions(), IQR_POWER, IQR_BASE)
    stages = body_stages(pg)
    per_page = 1 if len(stages) == 1 else 2
    MH = 380 if per_page == 1 else 190          # ユニットの高さ(電源・CPU・スロットで共通)
    TOP, RX, SLOT_W = 80, 205, 73               # RX: ベースの左端(電源の端子は左へ出るので、その左は配線用に空ける)
    ROW_H = MH + 40 + 34                        # 1段の高さ(ベースの枠 + 段の見出し)
    centered = lambda t, size, cx: round(cx - text_w(t, size) / 2 - TEXT_MARGIN, 1)
    empty_points = int(pg.get("empty_slot_points", EMPTY_SLOT_POINTS))
    cpu = pg["model"].upper()

    def power_symbol(model):
        power = powers[model]
        base = "iqr_dc" if power["supply"] == "DC" else ("iqr_ac_24" if power["service_24v"] else "iqr_ac")
        key = f"{base}_{model}_{MH}" if power.get("terminal_labels_top_to_bottom") else (base if MH == 380 else f"{base}_{MH}")
        if key not in symbols:
            symbols[key] = iqr_power_symbol(key, power["supply"], power["service_24v"], MH, power.get("terminal_labels_top_to_bottom"), power.get('additional_terminals'))
        return key

    def cpu_symbol():
        if cpu.startswith('MXR'):
            from renderers.controllers import mxr_symbol
            key = f'mxr_cpu_{MH}'
            if key not in symbols:
                symbols[key] = mxr_symbol(key, MH)
            return key
        if cpus[cpu].get('module_role') == 'remote_head':
            key = f'iqr_remote_head_{MH}'
            if key not in symbols:
                # CPU と同じ幅・位置(電源との間に隙間を作らない)。中身は箱の中央(x=30)にそろえる
                head = Symbol(key, 'リモートヘッド', 80, MH, 10, 0)
                head.rect(-10, 0, 80, MH)
                for i in range(2):
                    draw_rj45(head, 10, 65 + i * 50)
                head.rect(14, 160, 32, 12)
                symbols[key] = head
            return key
        key = "iqr_cpu" + ("_lan" if cpus[cpu]["ethernet"] else "") + ("_usb" if cpus[cpu]["usb_port"] else "")
        joined = bool(cpus[cpu].get("network_part"))
        if joined:
            key += "_en"
        if MH != 380 or joined:
            key += f"_{MH}" if MH != 380 else ""
            if key not in symbols:
                symbols[key] = iqr_cpu_symbol(key, cpus[cpu]["ethernet"], cpus[cpu]["usb_port"], MH, joined)
        return key

    assignments, _, _ = slot_assignments(pg)
    pages, slot_no, address, used = [], 0, 0, set()
    for start in range(0, len(stages), per_page):
        p = Page(symbols)
        chunk = stages[start:start + per_page]
        title = f"{series} ユニット構成" + (f" ({start // per_page + 1}/{(len(stages) + per_page - 1) // per_page})"
                                          if len(stages) > per_page else "")
        page_heading(p, f"{series} ユニット構成  ベース: " + "・".join(st[1] for st in stages) if start == 0 else title, x=RX)
        # 入出力ページと同じ位置に P24/N24 のレーン(電源・ERR などを QET で配線するため)
        for name, lx in (("P", FX_IN_X["outer"]), ("N", FX_IN_X["inner"])):
            ctext(p, lx, 44, LANE[name], 8, True)
            p.place("junction", lx, LANE_TOP_Y)
        p.extend_lanes([FX_IN_X["outer"], FX_IN_X["inner"]])
        slot_boxes = []
        for r, (stage, base_model, power_model, modules) in enumerate(chunk):
            y0 = TOP + r * ROW_H + (24 if per_page > 1 else 0)
            slots = bases[base_model]["slots"]
            x = RX + 10                                  # ユニットを左から隙間なく並べる
            units_x0 = x
            if per_page > 1:
                p.text(RX, y0 - 22, f"{stage}  {base_model}", 9, True)
            if power_model:
                stage_config = pg if stage == '基本' else pg['extensions'][start+r-1]
                p.place(power_symbol(power_model), x + 10, y0 + 20, label=power_model, tag=stage_config.get('power_tag',''),
                        texts=[("label", centered(power_model, 10, 25), 20, 10, True)])
                x += 70
            netpart = None
            if stage == "基本":
                p.place(cpu_symbol(), x + 10, y0 + 20, label=cpu, tag=pg.get('tag',''), texts=[("label", centered(cpu, 9, 30), 20, 9, True)])
                x += 80
                netpart = cpus[cpu].get("network_part")      # RnENCPU: CPU の右のネットワーク部がスロット0を占める
            p.rect(RX, y0, x + slots * SLOT_W + 10, y0 + MH + 40, dash=False)
            stage_config = pg if stage == '基本' else pg['extensions'][start+r-1]
            if stage_config.get('base_tag'):
                p.text(RX+10, y0+MH+25, stage_config['base_tag'], 9, True)
            offset = netpart.get("slots", 1) if netpart else 0
            for i in range(slots):
                sx, sy = round(x + i * SLOT_W, 1), y0 + 20
                address = assignments[start + r][i]["start"]
                j = i - offset
                module = modules[j].upper() if j >= 0 and j < len(modules) and modules[j] else ""
                previous = modules[j - 1].upper() if j > 0 and j - 1 < len(modules) and modules[j - 1] else ""
                current_spec, previous_spec = slot_definition(module, is_q), slot_definition(previous, is_q)
                power_front = bool(current_spec.get('power_ports') and current_spec.get('slot_io_points') == [16, 32])
                network_back = bool(previous_spec.get('power_ports') and previous_spec.get('slot_io_points') == [16, 32])
                if i < offset:
                    p.line(sx, sy, sx + SLOT_W, sy, width=1.0)
                    p.line(sx, sy + MH, sx + SLOT_W, sy + MH, width=1.0)
                    p.line(sx, sy, sx, sy + MH, width=1.5, dash=True)
                    if i == offset - 1:
                        p.line(sx + SLOT_W, sy, sx + SLOT_W, sy + MH, width=1.5)
                elif power_front or network_back:
                    p.line(sx, sy, sx + SLOT_W, sy, width=1.5)
                    p.line(sx, sy + MH, sx + SLOT_W, sy + MH, width=1.5)
                    if power_front:
                        p.line(sx, sy, sx, sy + MH, width=1.5)
                    else:
                        p.line(sx, sy, sx, sy + MH, width=1.5, dash=True)
                        p.line(sx + SLOT_W, sy, sx + SLOT_W, sy + MH, width=1.5)
                else:
                    p.rect(sx, sy, sx + SLOT_W, sy + MH, dash=False)
                cx = sx + SLOT_W / 2
                ctext(p, cx, sy + 16, f"{slot_no}", 9, True)
                p.line(sx, sy + 30, sx + SLOT_W, sy + 30, width=0.5)
                if i < offset:
                    # ネットワーク部(CPU と一体。RJ71EN71 相当)。ポート P1・P2 は下へ配線する
                    ports = netpart.get('ports_by_slot', [netpart['ports']])[i] if netpart.get('ports_by_slot') else netpart['ports']
                    key = f"iqr_netpart_{MH}_" + '_'.join(ports)
                    if key not in symbols:
                        symbols[key] = iqr_netpart_symbol(key, ports, SLOT_W, MH - 30)
                    p.place(key, sx, sy + 30)
                    points = netpart.get("points", 32)
                    if MH >= 300:
                        ctext(p, cx, sy + 52, netpart.get("names_by_slot", ["ネットワーク部"] * offset)[i], 7, True)
                        if netpart.get("equivalent"):
                            ctext(p, cx, sy + 72, f"{netpart['equivalent']}相当", 7)
                        ctext(p, cx, sy + 93, f"X/Y{address:03X}〜", 7)
                        ctext(p, cx, sy + 107, f"X/Y{address + points - 1:03X}", 7)
                    else:                                    # 2段構成: 低いので2行にまとめる
                        ctext(p, cx, sy + 42, netpart.get("names_by_slot", ["ネットワーク部"] * offset)[i], 7, True)
                        ctext(p, cx, sy + 56, f"X/Y{address:03X}〜{address + points - 1:03X}", 6)
                    address += points
                    slot_no += 1
                    continue
                reserved = slot_definition(previous, is_q).get("slots", 1) == 2
                display_module = previous if network_back else '' if power_front else module
                name = '外部供給電源' if power_front else display_module or ("占有" if reserved else "空き")
                size = next((z for z in (9, 8, 7, 6) if text_w(name, z) <= SLOT_W - 12), 6)   # 隣のスロットに掛からないよう余白を取る
                ctext(p, cx, sy + 52, name, size, bool(display_module) or power_front)
                tags = stage_config.get('module_tags', [])
                tag_index = j - 1 if network_back else j
                tag = tags[tag_index].strip() if display_module and tag_index < len(tags) and tags[tag_index] else ''
                if display_module and tag:
                    ctext(p, cx, sy + MH - 46, tag, 9, True)
                info = slot_summary(display_module, is_q) if display_module else ""
                info_size = next((z for z in (8, 7, 6)
                                  if all(text_w(line, z) <= SLOT_W - 4
                                         for line in wrap2(info, SLOT_W - 8, z).split('\n'))), 6)
                lines = wrap2(info, SLOT_W - 8, info_size).split('\n') if info else []
                for k, part in enumerate(lines):
                    ctext(p, cx, sy + 72 + k * 15, part, info_size)
                # 先頭アドレス(16進)。占有スロットはアドレスを使わない
                points, kind = (0, "") if reserved else slot_points(module, is_q, empty_points)
                if power_front:
                    points = 0
                elif network_back:
                    address = assignments[start + r][i - 1]['start'] + previous_spec['slot_io_points'][0]
                    points, kind = previous_spec['slot_io_points'][1], 'X/Y'
                if points:
                    for k, label in enumerate((f"{kind}{address:03X}〜", f"{kind}{address + points - 1:03X}")):
                        ctext(p, cx, sy + MH - 84 + k * 14, label, 7)
                    address += points
                if display_module:
                    slot_boxes.append((display_module, tag, cx, sy + MH - 24))
                slot_no += 1
        if start == 0:
            # CPU に関すること(電池・SD・メモリカセット)は欄外の表に書く(USB・Ethernet は CPU の箱に絵で描く)
            def option_value(key, supported):
                if supported is False:
                    return '搭載不可'
                state=pg.get(key,'要確認')
                model=pg.get(key+'_model','')
                if key == 'battery' and cpu.startswith('MXR') and not model:
                    model = cpus[cpu]['battery_type']
                return state+(' ('+model+')' if model and state in ('有','装着') else '')
            info_rows = [["バッテリ", option_value('battery',cpus[cpu].get('battery_supported'))]]
            if cpus[cpu].get('batteryless_supported'):
                value = pg.get('batteryless', '要確認')
                info_rows.append(['バッテリレス', value + (' (' + cpus[cpu]['batteryless_model'] + ')' if value == '有' else '')])
            if cpus[cpu].get("cc_link_ie"):
                info_rows.append([cpus[cpu].get("network_type", "CC-Link IE"), "あり"])
            info_rows += [["SDメモリカード",option_value('sd_card',cpus[cpu].get('sd_card_supported',False))]]
            if cpus[cpu].get('memory_card_supported'):
                info_rows.append(['メモリカード',option_value('memory_card',True)])
            info_rows.append(['メモリカセット',option_value('memory_cassette',cpus[cpu].get('memory_cassette_supported',False))])
            ty = 790 - (len(info_rows) + 1) * TABLE_ROW          # 図枠の左下に置く
            p.text(RX, ty - 24, "CPUの設定/オプション", 9, True)
            table(p, RX, ty, [("項目", 140), ("内容", 180)], info_rows)
            note = f"※先頭アドレスは空きスロット{empty_points}点・アナログ16点・通信ユニット32点として自動で割り付けた値"
            p.text(RX + 360, 790 - 16, note, 8)

        def post(pages_rows, page_of, p=p, slot_boxes=slot_boxes):
            """タグがあれば形名と組で照合し、未指定時は同形名の登場順に対応させる。"""
            for module, tag, cx, ty in slot_boxes:
                for other, _ in pages_rows:
                    if other is pg:
                        continue
                    identities = [(other.get(m, ''), other.get(t, ''))
                                  for m, t in (('model', 'tag'), ('left_model', 'left_tag'), ('right_model', 'right_tag'))]
                    identities.append((other.get('right', {}).get('model', ''), other.get('right', {}).get('tag', '')))
                    for index, (model, other_tag) in enumerate(identities):
                        identity = (id(other), index)
                        if identity in used or str(model).upper() != module or (tag and tag != str(other_tag).strip()):
                            continue
                        n = page_of(other)
                        if n:
                            used.add(identity)
                            ctext(p, cx, ty, f"→ {n}頁", 8, True)
                        break
                    else:
                        continue
                    break
        if start == 0:
            from renderers import settings
            settings.draw(p, settings.fields(model=cpu, values=pg), pg, RX + 360, RX + 680, bottom=750)
        p.post = post
        pages.append((pg.get("title", title), p))
    return pages


def build_fx5_body_page(pg, symbols):
    """本体の電源・内蔵アナログ・通信を接続可能なQET端子で描く。"""
    p = Page(symbols)
    spec = FX5U_SPECS[pg["model"].upper()]
    battery = pg.get("battery", "要確認" if spec["battery_supported"] else "搭載不可")
    usb = "あり" if spec["usb_port"] else "なし"
    power = model_power(pg["model"])
    module_board = next((m.upper() for m in pg.get('modules', []) if FX5_COMM[m.upper()]['form'] == 'board'), '')
    board = pg.get('board_model', '') or module_board
    key = "fx5_body_" + pg["model"].upper().replace("/", "_").replace("-", "_") + '_' + board.replace('-', '_')
    if key not in symbols:
        pairs = 2 if pg["model"].upper().startswith(("FX5U-64", "FX5U-80")) else 1
        connector = pg["model"].upper().startswith("FX5UC-")
        symbols[key] = fx5_body_symbol(key, power == "AC", spec["analog"], spec["rs485"], spec["service"], pairs,
                                       connector, not connector, FX5_BOARDS.get(board))
    sym = symbols[key]
    BX = 300                                  # 本体の左上。端子は左へ出るので、レーンとの間を配線用に空ける
    if spec["battery_supported"]:
        battery_first = ("■" if battery == "装着" else "□") + " 有 (FX3U-32BL)"
        battery_second = ("■" if battery == "非装着" else "□") + " 無"
    else:
        battery_first = "■ 装着不可"
        battery_second = ""
    usb_choice = "■ " + ("有 (Mini-B)" if spec["usb_port"] else "無")
    sd_card = pg.get("sd_card", "要確認")
    sd_model = pg.get("sd_card_model", "").strip()
    sd_first = ("■" if sd_card == "有" else "□") + " 有 (" + (sd_model or "　　　") + ")"
    sd_second = ("■" if sd_card == "無" else "□") + " 無"
    sd_available = not pg['model'].upper().startswith('FX5S-') or board == 'FX5-SDCD'
    sd_in_board = board == 'FX5-SDCD'
    board_label = board if board and board != 'なし' else '型式：'
    module_tags = pg.get('module_tags', [])
    board_tag = pg.get('board_tag', '') or next((module_tags[i] for i,m in enumerate(pg.get('modules', []))
                                                if m.upper()==board and i<len(module_tags)), '')
    unit_identity_header(p,pg,BX-20,350)
    cpu = p.place(key, BX, 52, label=pg.get('tag',''), comment="バッテリ: " + battery,
            infos={"auxiliary1": usb_choice, "auxiliary2": battery_first, "auxiliary3": battery_second,
                   "auxiliary4": "バッテリ", "auxiliary5": "USBポート",
                   "auxiliary6": "SD CARD" if sd_available else "", "auxiliary7": sd_first if sd_available else "", "auxiliary8": sd_second if sd_available else "",
                   "auxiliary10": board_label, "auxiliary11": board_tag, 'manufacturer_reference':pg['model'], 'auxiliary13':'CPU',
                   "description": "USBポート: " + usb},
            texts=[("auxiliary13", 10, 26, 10, True), ("auxiliary4", 75, sym.status_y, 8, False),
                   ("auxiliary2", 135, sym.status_y, 8, False),
                   ("auxiliary3", 135, sym.status_y + 19, 8, False),
                   ("auxiliary5", 75, sym.status_y + 38, 8, False),
                   ("auxiliary1", 135, sym.status_y + 38, 8, False),
                   ("auxiliary6", 183 if sd_in_board else 75, 125 if sd_in_board else sym.status_y + 57, 8, False),
                   ("auxiliary7", 227 if sd_in_board else 135, 125 if sd_in_board else sym.status_y + 57, 7 if sd_in_board else 8, False),
                   ("auxiliary8", 227 if sd_in_board else 135, 144 if sd_in_board else sym.status_y + 76, 7 if sd_in_board else 8, False)] +
                  ([] if board not in FX5_BOARDS else
                   [("auxiliary11", 183, 100, 8, True), ("auxiliary10", 183, 80, 8, False)]))
    # 入出力ページと同じ位置に P24/N24 のレーンを置く(電源・センサ電源などを QET で配線するため)
    for name, lx in (("P", FX_IN_X["outer"]), ("N", FX_IN_X["inner"])):
        ctext(p, lx, 44, LANE[name], 8, True)
        p.place("junction", lx, LANE_TOP_Y)
    p.extend_lanes([FX_IN_X["outer"], FX_IN_X["inner"]])
    # 端子は QET でそのまま配線できるので、行き先の決まらない線は引き出さない
    # 右側にユニット構成の表(本体の入出力・増設・アナログ・通信と、そのページ番号)を置く
    adapters = [(m, module_tags[i] if i<len(module_tags) else '') for i,m in enumerate(pg.get('modules', []))
                if FX5_COMM[m.upper()]['form'] != 'board']

    def post(pages_rows, page_of):
        rows = [(pg["model"], "本体", "")]
        rows += [((tag+'  ' if tag else '')+m, "通信 " + FX5_COMM[m.upper()].get('network', ''), "") for m,tag in adapters]
        for other, _ in pages_rows:
            k = other["kind"]
            if k == "fx5u":
                if other['model'].upper() != pg['model'].upper():
                    continue
                if pg.get('tag', '').strip() and other.get('tag', '').strip() != pg['tag'].strip():
                    continue
                rows.append((other["model"], "本体の入出力", page_of(other)))
            elif k == "fx5ext":
                sp = fx_spec(other)
                n_out = sum(len(g) for _, g in sp["groups"])
                what = "・".join(t for t in ((f"入力{len(sp['inputs'])}点" if sp["inputs"] else ""),
                                             (f"出力{n_out}点" if n_out else "")) if t)
                rows.append((other["model"], "増設 " + what, page_of(other)))
            elif k == "fx5analog":
                rows.append((other["model"], f"アナログ {len(FX5_ANALOG_SPECS[other['model'].upper()]['channels'])}ch", page_of(other)))
            elif k == "fxcomm":
                for side in ("left_model", "right_model"):
                    if other.get(side):
                        rows.append((other[side], "通信 " + FX5_COMM[other[side].upper()].get('network', ''), page_of(other)))
        if len(rows) <= 1:
            return
        cols = [("形名", 130), ("内容", 170), ("頁", 40)]
        # 図枠の右下に置く(拡張ボードの端子は右へ配線するので、本体の右は空けておく)
        TX = 20 + BORDER_COLS * COL_SIZE - 10 - sum(w for _, w in cols)
        TY = 790 - (len(rows) + 1) * TABLE_ROW
        p.text(TX, TY - 24, "ユニット構成", 9, True)
        table(p, TX, TY, cols,
              [[m, w, str(n) if n else ""] for m, w, n in rows])
    from renderers import settings
    settings.draw(p, settings.fields(model=pg['model'], values=pg), pg, 900, 1220, bottom=430)
    p.post = post
    return p


LANE_POWER = {"+24V": "P", "24V": "P", "0V": "N", "24G": "N"}

# アナログの方式別配線(CSV の「方式」列: 電圧 / 電流)
# 電流入力で V+ と I+ を短絡する機種(メーカーの外部配線図で確認したもの):
#   Q64AD(SH-080055 4.4.2 「電流入力は V+ と I+ を接続」)、R60AD4(SH-081232ENG)、FX5-4AD-ADP(JY997D60501)
# 短絡しない機種: FX5-4AD(SH-081802ENG 1.6 電流入力は I+ と COM)
CURRENT_JUMPER = {"Q64AD": True, "Q64ADH": True, "R60AD4": True, "R60ADH4": True, "R60AD8-G": True, "R60AD16-G": True,
                  "Q64AD2DA": True, "Q64AD-GH": True, "FX5-4AD-ADP": True, "FX5-4A-ADP": True, "FX5-4AD": False}


def analog_names(spec, idx):
    """チャンネル idx(0〜)の端子名(テンプレートを展開したもの)"""
    direction = spec['channels'][idx]
    terms = (spec['terminals_by_channel'][idx] if spec.get('terminals_by_channel')
             else spec.get('terminals_by_direction', {}).get(direction, spec['terminals']))
    return [t.format(n=idx + 1) for t in terms]


def analog_method_pins(names, direction, method):
    """方式に使う端子: (+ の端子, - の端子, 短絡する2端子 or None, シールド端子 or None)。対応しなければ None"""
    up = [n.upper() for n in names]
    plus_v = next((n for n, u in zip(names, up) if re.fullmatch(r"V\d*\+(/I\+)?", u)), None)
    plus_i = next((n for n, u in zip(names, up) if re.fullmatch(r"(V\+/)?I\d*\+", u)), None)
    minus = [n for n, u in zip(names, up) if re.fullmatch(r"COM\d*|V-|I-|V-/I-", u)]
    sld = next((n for n, u in zip(names, up) if u == "SLD"), None)
    if method == "電圧" and plus_v and minus:
        m = next((n for n in minus if n.upper() != "I-"), minus[0])
        return plus_v, m, None, sld
    if method == "電流" and plus_i and minus:
        m = next((n for n in minus if n.upper() != "V-"), minus[0])
        jumper = (plus_v, plus_i) if direction == "入力" and plus_v and plus_v != plus_i else None
        return plus_i, m, jumper, sld
    return None


def analog_device_symbol(symbols, dist, plus_top):
    """アナログの相手機器(伝送器・負荷)。右に + と - の端子(間隔 dist、ユニットの端子の行に合わせる)"""
    key = f"analog_dev_{'pm' if plus_top else 'mp'}_{int(dist)}"
    if key not in symbols:
        dev = Symbol(key, "アナログ機器(+/-)", 60, dist + 30, 50, 15)
        dev.rect(-50, -14, 40, dist + 28)
        for k, dy, sign in ((("p", 0, "+"), ("m", dist, "-")) if plus_top else (("m", 0, "-"), ("p", dist, "+"))):
            dev.terminal(k, "e", -10, dy); dev.label(-22, dy + 4, sign, 9, True)
        dev.dynamic("label", -54, -34, 8, True)
        symbols[key] = dev
    return key


def draw_analog_wiring(p, model, direction, method, pins, x_dev, pitch, label):
    """相手機器(伝送器・負荷)を置き、+・- の端子へ配線する。シールド線は SLD 端子か接地へ。
    pins: {端子名: (部品, 端子キー)}。戻り値: 注記が要るとき True(短絡の要否が未確認の機種)"""
    plus, minus, jumper, sld = analog_method_pins(list(pins), direction, method)
    yp, ym = pins[plus][0][3], pins[minus][0][3]
    py, dist = min(yp, ym), abs(ym - yp) or pitch          # 機器の端子をユニットの端子の行にそろえて線をまっすぐにする
    key = analog_device_symbol(p.sym, dist, yp <= ym)
    dev = p.place(key, x_dev, py, label=label or ("伝送器" if direction == "入力" else "負荷"),
                  texts=[("label", -54, -34, 8, True)])
    p.wire(dev, "p", *pins[plus], num="", show=False)
    p.wire(dev, "m", *pins[minus], num="", show=False)
    note = False
    if jumper:
        need = CURRENT_JUMPER.get(model)
        if need:
            p.wire(*pins[jumper[0]], *pins[jumper[1]])          # 電流入力: V+ と I+ を短絡
        elif need is None:
            note = True
    # シールド(2本の線を囲む破線)。SLD 端子があればそこへ、なければ接地
    sx0, sx1 = x_dev + 14, x_dev + 34
    sy0, sy1 = py - 10, py + dist + 10
    p.rect(sx0, sy0, sx1, sy1, dash=True, width=0.8)
    node = p.place("node", (sx0 + sx1) / 2, sy1)
    if sld:
        p.wire(node, "s", *pins[sld])
    else:
        e = p.place("earth", (sx0 + sx1) / 2, sy1 + 14)
        p.wire(node, "s", e, "n")
    return note


def analog_split(n):
    """1ページに描くチャンネル数 n を左右の半分に分ける: 1 半分あたりの数(左が多め)"""
    return max(1, (n + 1) // 2)


def analog_page_channels(kind, spec):
    if kind not in ('qanalog','iqranalog','remoteanalog'):
        return 8
    counts=[len(channel_rows(spec,i)) for i in range(len(spec['channels']))]
    extra=len(spec.get('power',[]))+len(extra_rows(spec))
    return next((n for n in range(8,0,-1) if analog_split(n)*max(counts)+extra<=17),1)


def build_fx_analog_page(pg, cfg, symbols, rows, start=0):
    """アナログ端子を接続可能な端子として展開する(左右の半分に振り分ける)。外部配線は利用者が決める。"""
    model = pg["model"].upper()
    spec = {"iqranalog": IQR_ANALOG, "qanalog": Q_ANALOG, "fx5analog": FX5_ANALOG_SPECS, "remoteanalog": REMOTE_ANALOG}[pg["kind"]][model]
    right_only = pg['kind']=='fx5analog' and model!='FX5-8AD'
    layout_offset = HALF_W if right_only else 0
    descriptions = {int(r["CH"]): r.get("用途", "").strip() for r in rows}
    row_by_ch = {int(r["CH"]): r for r in rows}
    p = Page(symbols)
    ch_pins = {}                                   # チャンネル → {端子名: (部品, 端子キー)}

    def wire_channels(pitch):
        """CSV の「方式」が書かれたチャンネルに、相手機器とシールドを描く"""
        note = False
        for idx, pins in ch_pins.items():
            r = row_by_ch.get(idx + 1, {})
            method = r.get("方式", "").strip()
            if not method:
                continue
            first = next(iter(pins.values()))[0]
            note |= draw_analog_wiring(p, model, spec['channels'][idx], method, pins, first[2] - 95, pitch,
                                       r.get("機器番号", "").strip())
        if note:
            p.text(HEAD_X+layout_offset, 782 if spec.get('diagram_note') else 800, "※電流入力で V+ と I+ を短絡するかはメーカーの配線図で確認", 8)
    if spec.get('diagram_note'):
        p.text(HEAD_X+layout_offset, 800, spec['diagram_note'], 8)
    n = min(analog_page_channels(pg['kind'],spec), len(spec['channels']) - start)
    per = analog_split(n)
    if right_only:
        per = n
    if pg['kind'] in ('qanalog', 'remoteanalog', 'iqranalog'):   # iQ-R も Q と同じ表(端子│信号│用途)で描く(利用者: Q の方が見やすい)
        analog_row_y0 = ROW_Y0
        power = list(zip(spec.get('power_pins', spec['power']), spec['power']))
        use_lanes = spec.get('auto_wiring', True) and any(t in LANE_POWER for _, t in power)
        sides = 2 if n > 1 else 1
        for side in range(sides):
            x0 = IN_X['plc'] + side * HALF_W
            io_table_header(p,pg,x0+4,250,(45,100),('端子','信号','用途'))
        lane_tops = {}
        if use_lanes:
            for name in ('P', 'N'):
                ctext(p, IN_X[name], 44, LANE[name], 8, True)
                lane_tops[name] = p.place('junction', IN_X[name], LANE_TOP_Y)
        row_index = [0, 0]
        for idx in range(start, start + n):
            direction = spec['channels'][idx]
            side = (idx - start) // per
            for row in channel_rows(spec, idx):
                name, pin, template = row['signal'], row['pin'], row.get('template', '')
                meaning = (spec.get('signal_labels_by_direction', {}).get(direction, {}).get(template, 'コモン' if name.startswith('COM') else '')
                           if row['connectable'] else '接続しない')
                comment = (spec.get("channel_labels", [])[idx] if spec.get("channel_labels") else f"CH{idx + 1} {direction}") + (f" {meaning}" if meaning else '') + (f" {descriptions[idx + 1]}" if descriptions.get(idx + 1) else '')
                x, y = IN_X['plc'] + side * HALF_W, analog_row_y0 + row_index[side] * ROW_PITCH
                if spec.get('channel_connectors'):
                    connector_name = spec['channel_connectors'][idx]['name']
                    if not comment.startswith(connector_name):
                        comment = connector_name + ' ' + comment
                comment = wrap2(comment, 140, 8)
                key = 'plc_in' if row['connectable'] else readonly_symbol(p.sym, 'plc_in')
                h = p.place(key, x, y, label=name, comment=comment, infos={'auxiliary1': pin},
                            texts=[text for text in IN_TEXTS if text[0] != 'comment'] +
                                  [comment_text(comment, 110, 140, 8, ROW_PITCH)])
                if row['connectable']:
                    ch_pins.setdefault(idx, {})[name] = (h, 't')
                row_index[side] += 1
        for pin, terminal in power:
            x, y = IN_X['plc'], analog_row_y0 + row_index[0] * ROW_PITCH
            label = str(pin) if pin != terminal else ''
            plc = p.place('plc_in', x, y, label=terminal, comment=spec.get('power_title', '電源・接地'), infos={'auxiliary1': label}, texts=IN_TEXTS)
            lane = LANE_POWER.get(terminal)
            if lane and use_lanes:
                junction = p.place('junction', IN_X[lane], y)
                p.wire(lane_tops[lane], 's', junction, 'n')
                lane_tops[lane] = junction
                p.wire(junction, 'e', plc, 't', num=LANE[lane], show=True)
            row_index[0] += 1
        if use_lanes:
            p.extend_lanes([IN_X['P'], IN_X['N']])
        for terminal in extra_rows(spec):
            y = analog_row_y0 + row_index[0] * ROW_PITCH
            key = 'plc_in'
            if terminal.get('connectable') is False:
                key = readonly_symbol(p.sym, 'plc_in')
            description = terminal.get('description', terminal.get('group', '')) + ('（外部配線不可）' if terminal.get('connectable') is False and terminal['signal'] != 'NC' else '')
            description = wrap2(description, 140, 8)
            p.place(key, IN_X['plc'], y, label=terminal['signal'], comment=description,
                    infos={'auxiliary1': str(terminal['pin'])},
                    texts=[text for text in IN_TEXTS if text[0] != 'comment'] + [comment_text(description, 110, 140, 8, ROW_PITCH)])
            row_index[0] += 1
        wire_channels(ROW_PITCH)
        return p
    new_layout = pg['kind'] in ('fx5analog', 'qanalog')
    note = ""
    if new_layout:
        power = list(zip(spec.get('power_pins', spec['power']), spec['power'])) if spec.get('power') else []
        use_lanes = spec.get('auto_wiring', True) and any(t in LANE_POWER for _, t in power)
        for side in range(1 if right_only else 2 if n > 1 else 1):
            unit_identity_header(p,pg,275+layout_offset+side*HALF_W,235)
        p.text(HEAD_X+layout_offset,782 if spec.get('diagram_note') else 800,note,8)
        next_y = [82, 82]
        lane_tops = {}
        if use_lanes:
            for name, offset in (('P', FX_IN_X['outer']), ('N', FX_IN_X['inner'])):
                offset += layout_offset
                ctext(p, offset, 44, LANE[name], 8, True)
                lane_tops[name] = p.place('junction', offset, LANE_TOP_Y)
        for idx in range(start, start + n):
            direction = spec['channels'][idx]
            side = (idx - start) // per
            x, y0 = 275 + layout_offset + side * HALF_W, next_y[side]
            display_rows = channel_rows(spec, idx)
            p.rect(x, y0 - 30, x + 235, y0 + len(display_rows) * 32 - 8, dash=False, width=1)
            p.text(x + 12, y0 - 25, f"CH{idx + 1} {direction}  {descriptions.get(idx + 1, '')}", 8, True)
            for ti, row in enumerate(display_rows):
                name, template = row['signal'], row.get('template', '')
                meaning = (spec.get('signal_labels_by_direction', {}).get(direction, {}).get(template, 'コモン' if name.startswith('COM') else '')
                           if row['connectable'] else '接続しない')
                y = y0 + ti * 32
                label = (row['pin'] + '  ' if row['pin'] else '') + name
                key = 'module_pin' if row['connectable'] else readonly_symbol(p.sym, 'module_pin')
                h = p.place(key, x, y, label=label, comment=meaning,
                        texts=[('label', 14, -7, 8, False), ('comment', 72, -7, 8, False)])
                if row['connectable']:
                    ch_pins.setdefault(idx, {})[name] = (h, 't')
            next_y[side] = y0 + 22 + len(display_rows) * 32
        if power:
            x, y0 = 275 + layout_offset, next_y[0]
            p.rect(x, y0 - 30, x + 235, y0 + len(power) * 30 - 10, dash=False, width=1)
            p.text(x + 12, y0 - 25, spec.get('power_title', '電源・接地'), 8, True)
            for i, (pin, terminal) in enumerate(power):
                y = y0 + i * 30
                plc = p.place('module_pin', x, y, label=pin, comment=terminal if pin != terminal else '',
                              texts=[('label', 14, -7, 8, False), ('comment', 72, -7, 8, False)])
                lane = LANE_POWER.get(terminal)
                if lane and use_lanes:
                    lx = FX_IN_X['outer' if lane == 'P' else 'inner'] + layout_offset
                    junction = p.place('junction', lx, y)
                    p.wire(lane_tops[lane], 's', junction, 'n')
                    lane_tops[lane] = junction
                    p.wire(junction, 'e', plc, 't', num=LANE[lane], show=True)
        if use_lanes:
            p.extend_lanes([FX_IN_X['outer']+layout_offset, FX_IN_X['inner']+layout_offset])
        wire_channels(32)
        return p
    page_heading(p, f"{model} アナログ端子")
    p.text(HEAD_X,782 if spec.get('diagram_note') else 800,note,8)
    for idx in range(start, start + n):
        direction = spec["channels"][idx]
        side, slot = divmod(idx - start, per)
        x = 275 + side * HALF_W
        y0 = 100 + slot * 140
        p.text(x - 245, y0 - 24, f"CH{idx + 1} {direction}  {descriptions.get(idx + 1, '')}", 8, True)
        terminals = spec.get("terminals_by_channel", [])[idx] if spec.get("terminals_by_channel") else spec.get("terminals_by_direction", {}).get(direction, spec["terminals"])
        for ti, terminal in enumerate(terminals):
            y = y0 + ti * 32
            name = terminal.format(n=idx + 1)
            pins = spec.get("pins_by_channel")
            label, comment = (pins[idx][ti], name) if pins else (name, f"CH{idx + 1} {direction}")
            h = p.place("fx_in", x, y, label=label, comment=comment,
                        texts=FX_IN_TEXTS + [("comment", 64, vcenter(8), 8, False)])
            ch_pins.setdefault(idx, {})[name] = (h, 't')
    power_y = 100 + per * 140 + 10
    power = list(zip(spec.get("power_pins", spec["power"]), spec["power"]))
    if spec.get("power_per_8_channels"):
        power = power[(start // 8) * 4:(start // 8 + 1) * 4]
    if power:
        p.text(30, power_y - 24, "電源・補償・接地端子", 8, True)
    for i, (pin, terminal) in enumerate(power):
        x, y = 275 + (i % 2) * HALF_W, power_y + (i // 2) * 40
        p.place("fx_in", x, y, label=pin, comment=terminal if pin != terminal else "",
                texts=FX_IN_TEXTS + [("comment", 64, vcenter(8), 8, False)])
    for i, terminal in enumerate(spec.get('auxiliary_terminals', []), len(power)):
        x, y = 275 + (i % 2) * HALF_W, power_y + (i // 2) * 40
        p.place("fx_in", x, y, label=str(terminal['pin']),
                comment=terminal['signal'] + ' ' + terminal.get('description', terminal.get('group', '')),
                texts=FX_IN_TEXTS + [("comment", 64, vcenter(8), 8, False)])
    wire_channels(32)
    return p


def comm_settings(p, pg, spec, x, prefix):
    """通信ユニットの機種別記入欄。非表示項目の値は保持する。"""
    from renderers import settings
    model = pg.get(prefix + "_model", "")
    settings.draw(p, settings.fields(model=model, values=pg, prefix=prefix), settings.values(pg, prefix), x - 245, x - 15)


def build_q_comm_page(pg, symbols):
    from renderers.communication import draw_notes, interface_rows
    p = Page(symbols)
    definitions = {'iqrcomm': IQR_COMM, 'qcomm': Q_COMM, 'fxcomm': FX5_COMM}[pg['kind']]
    for side, field in enumerate(("left_model", "right_model")):
        model = pg.get(field, "").strip().upper()
        if not model:
            continue
        spec = definitions[model]
        x = 275 + side * HALF_W
        prefix='left' if side==0 else 'right'
        identity={'kind':pg['kind'],'model':model,'tag':pg.get(prefix+'_tag',''),
                  'slot':pg.get(prefix+'_slot',''),'unit_no':pg.get(prefix+'_unit_no','')}
        if spec.get('panel_interfaces'):
            from renderers.communication import draw_panel
            right=draw_panel(p, symbols, spec, x, Symbol, pg, prefix)
            unit_identity_header(p,identity,x,right-x)
            comm_settings(p, pg, spec, x, 'left' if side == 0 else 'right')
            continue
        unit_identity_header(p,identity,x,UNIT_BOX_W)
        if pg['kind'] in ('qcomm', 'iqrcomm') and spec.get('interfaces'):
            p.rect(x, 52, x + UNIT_BOX_W, 84 + len(spec['interfaces']) * 225, dash=False, width=1)
            p.text(x+12,60,spec['network'],8,True)
            for k in range(1, len(spec['interfaces'])):
                p.line(x, 84 + k * 225, x + UNIT_BOX_W, 84 + k * 225, width=0.5)
            signals = {'SDA':'TXD+', 'SDB':'TXD-', 'RDA':'RXD+', 'RDB':'RXD-', 'SG':'GND', 'SLD':'シールド', 'FG':'接地'}
            for channel, interface in enumerate(spec['interfaces']):
                top = 94 + channel * 225
                p.text(x + 12, top, interface['name'], 8, True)
                if interface['kind'] == 'dsub9':
                    y = top + 90
                    plug = p.place('module_dsub_f', x, y)
                    p.text(x + 15, y + 40, 'D-sub 9pin メス', 8)
                else:
                    for i, port in enumerate(interface['ports']):
                        y = top + 34 + i * 24
                        plc = p.place('module_pin', x, y, label=port, comment=signals.get(port, ''),
                                      texts=[('label',14,-7,8,False), ('comment',72,-7,8,False)])
        elif pg['kind'] in ('qcomm', 'iqrcomm') and spec.get('connector_type'):
            kind = spec['connector_type']
            if kind == 'terminal':
                bottom = 117 + len(interface_rows(spec)) * 36 + (20 if spec.get('unconnected_pins') else 0)
            else:
                bottom = 152 + len(spec['ports']) * 115 - 40
                if spec.get('power_ports'):
                    bottom = 417 + len(spec['power_ports']) * 36
            p.rect(x, 52, x + UNIT_BOX_W, bottom, dash=False, width=1)
            p.text(x + 12, 62, spec['network'], 8, True)
            if kind == 'terminal':
                for i, row in enumerate(interface_rows(spec)):
                    y = 117 + i * 36
                    label=(row['pin']+'  ' if row['pin'] else '')+row['signal']
                    if row['connectable']:
                        p.place('module_pin',x,y,label=label,texts=[('label',14,-7,8,False)])
                    else:
                        p.text(x+14,y-7,label+'（接続しない）',8)
            else:
                for i, port in enumerate(spec['ports']):
                    y = 152 + i * 115
                    plug = p.place('module_' + kind, x, y)
                    label = spec.get('connector_label', {'rj45': 'RJ-45', 'coax': '同軸 F形', 'optical': '光ファイバ'}[kind])
                    p.text(x + 58, y - 15, port, 8, True)
                    p.text(x + 58, y + 3, label, 8)
                for i, port in enumerate(spec.get('power_ports', [])):
                    y = 417 + i * 36
                    plc = p.place('module_pin', x, y, label=port, texts=[('label',14,-7,8,False)])
                if spec.get('power_ports'):
                    p.text(x + 12, 377, '外部電源', 8, True)
        elif pg['kind'] == 'fxcomm':
            serial = not (model == 'FX5-232ADP' or spec.get('connection', '').startswith('MINI-DIN'))
            p.rect(x, 52, x + UNIT_BOX_W, 102 + len(spec['ports']) * 50 - 10 if serial else 242, dash=False, width=1)
            p.text(x + 12, 60, spec['network'], 8, True)
            if model == 'FX5-232ADP' or spec.get('connection', '').startswith('MINI-DIN'):
                dsub = model == 'FX5-232ADP'
                plug = p.place('module_dsub' if dsub else 'module_minidin', x, 172)
                p.text(x + 15, 212, 'D-sub 9pin オス' if dsub else 'MINI-DIN 8pin メス', 8)
            else:
                signals = {'RDA':'RXD+', 'RDB':'RXD-', 'SDA':'TXD+', 'SDB':'TXD-', 'SG':'GND'}
                for i, port in enumerate(spec['ports']):
                    y = 102 + i * 50
                    plc = p.place('module_pin', x, y, label=port, comment=signals.get(port, ''),
                                  texts=[('label',14,-7,8,False), ('comment',72,-7,8,False)])
        else:
          p.rect(x,52,x+UNIT_BOX_W,122+len(spec['ports'])*60,dash=False,width=1)
          p.text(x+12,60,spec['network'],8,True)
          for i, port in enumerate(spec["ports"]):
            y = 102 + i * 60
            is_terminal = spec['network'] == 'CC-Link' or spec.get('terminal_labels', False)
            label = port if is_terminal else f"PORT{i + 1}"
            comment = "" if is_terminal else port
            plc = p.place("fx_in", x, y, label=label, comment=comment,
                          texts=FX_IN_TEXTS + [("comment", 64, vcenter(8), 8, False)])
        if spec.get('unconnected_pins') and not spec.get('unconnected_ports'):
            for i,pin in enumerate(spec['unconnected_pins']):
                p.text(x+14,bottom-35+i*18,str(pin)+'  NC（接続しない）',8)
        notes=['※接続先・配線方式はQETで記入']+list(spec.get('diagram_notes',[]))
        if spec.get('shield_ground_connected') or any(i.get('shield_ground_connected') for i in spec.get('interfaces',[])):
            notes.append('SLD・FG 内部接続')
        draw_notes(p,x,UNIT_BOX_W,notes)
        comm_settings(p, pg, spec, x, "left" if side == 0 else "right")
    p.stretch_boxes(bottom=min(UNIT_BOX_BOTTOM,getattr(p,'communication_footer_top',UNIT_BOX_BOTTOM+8)-8))
    return p



def remote_spec(model):
    for definitions in (IO_UNITS, REMOTE_MIXED, REMOTE_ANALOG, REMOTE_IOLINK, REMOTE_PULSE):
        if model in definitions:
            return definitions[model]
    return None


def remote_connector_pages(pg, symbols, spec):
    from renderers.remote import connector_pages
    if pg.get('_mixed_io') and not pg.get('title'):
        pg = dict(pg, title=pg['model'] + (' 入力' if pg['_mixed_io'] == 'in' else ' 出力'))
    return connector_pages(pg, symbols, spec, Page, Symbol, page_heading)


def build_remote_body_page(pg, symbols):
    model = pg['model'].upper()
    spec = remote_spec(model)
    if any(k in spec for k in ('network_connectors', 'power_connectors')) or spec.get('module_role') == 'extension':
        from renderers.remote import build_body
        return build_body(pg, symbols, spec, Page, Symbol, page_heading)
    p = Page(symbols)
    x = 275
    unit_identity_header(p,pg,x,UNIT_BOX_W)
    if spec['network'] == 'CC-Link':
        ports = spec['network_terminals']
        p.text(x + 12, 62, 'CC-Link・電源', 8, True)
    else:
        ports = spec.get('power_ports', [('1', '+24V'), ('2', '24G'), ('3', 'FG')])
        p.text(x + 12, 62, '電源・FG（コネクタ）', 8, True)
    for i, (pin, label) in enumerate(ports):
        y = 97 + i * 27
        plc = p.place('module_pin', x, y, label=pin, comment=label,
                      texts=[('label',14,-7,8,False), ('comment',72,-7,8,False)])
    y_next = 97 + len(ports) * 27 + 40
    if spec['network'] != 'CC-Link':
        for i, port in enumerate(('P1', 'P2')):
            y = y_next + 20 + i * 65
            plug = p.place('module_rj45', x, y)
            p.text(x + 58, y - 15, port, 8, True)
            p.text(x + 58, y + 3, 'RJ-45', 8)
        y_next += 20 + 2 * 65
    notes = (['配線・終端抵抗はネットワーク構成に従って接続']
             if spec['network'] == 'CC-Link' else spec.get('power_notes', []))
    # 注記は箱の幅で折り返す(箱は中身に合わせた幅 300)
    from renderers.communication import draw_notes
    draw_notes(p,x,UNIT_BOX_W,['※通信・電源の接続先はQETで記入']+list(notes))
    y_next += 10
    p.rect(x, 52, x + UNIT_BOX_W, max(y_next, 200), dash=False, width=1)
    # 設定欄は左下に表として並べる(端子の左は配線用に空ける)。CC-Link(イーサネットなし)は IP 欄を出さない
    from renderers import settings
    rows = settings.fields(model=pg['model'], values=pg)
    settings.draw(p, rows, pg)
    p.stretch_boxes(bottom=min(UNIT_BOX_BOTTOM,getattr(p,'communication_footer_top',UNIT_BOX_BOTTOM+8)-8))
    return p


def build_sensor_connector_page(uc, symbols, start):
    spec = configured_unit(uc)
    p = Page(symbols)
    page_heading(p, f"{uc['model']} センサコネクタ端子")
    p.text(HEAD_X, 800, '※配線はQETで記入', 8)
    for position in range(8):
        index = start + position
        if index >= spec['points']:
            break
        side, slot = divmod(position, 4)
        x, y0 = 275 + side * HALF_W, 88 + slot * 155
        p.text(x - 245, y0 - 24, f"CON{spec.get('sensor_connector_start', 1) + index}  {spec.get('sensor_prefix', 'X')}{index:X}", 8, True)
        for pin, label in enumerate(spec['sensor_pins'], 1):
            y = y0 + (pin - 1) * 31
            plc = p.place('fx_in', x, y, label=str(pin), comment=label,
                          texts=FX_IN_TEXTS + [('comment', 64, vcenter(8), 8, False)])
    return p


# ============================================================ 電源ページ(FX5U 本体・DC24V)
def build_power_page(pg, cfg, symbols):
    """AC電源 → ブレーカ → FX5U本体(L/N/⏚)と DC24V電源 → P/N(入出力ページへ)
    本体が DC電源タイプ(形名 /D…、または "power_type": "DC")なら build_power_page_dc"""
    ptype = (pg.get("power_type") or model_power(pg.get("model", ""))).upper()
    if ptype == "DC":
        return build_power_page_dc(pg, cfg, symbols)
    p = Page(symbols)
    pw = cfg["power"]
    RL, RN, RPE = 150, 200, 250                    # L / N / PE レールの Y
    X0, XCB, XPLC, XPSU, XEND = 60, 180, 340, 700, 1000

    p.text(30, 70, pg.get("ac", "AC100V 50/60Hz"), 10, True)
    for name, y in (("L", RL), ("N", RN), ("PE", RPE)):
        p.text(X0 - 28, y - 9, name, 9, True)
    # 入口
    l0 = p.place("junction", X0, RL)
    n0 = p.place("junction", X0, RN)
    pe0 = p.place("junction", X0, RPE)
    cb = p.place("breaker_2p", XCB, RL, label=pg.get("cb", "CB1"), comment=pg.get("cb_spec", ""),
                 texts=[("label", -16, -30, 9, True), ("comment", -16, 58, 7, False)])
    p.wire(l0, "e", cb, "w0", num="L", show=False)
    p.wire(n0, "e", cb, "w50", num="N", show=False)

    # 分岐点
    lp = p.place("junction", XPLC, RL); np_ = p.place("junction", XPLC + 40, RN)
    pep = p.place("junction", XPLC + 80, RPE)
    ls = p.place("junction", XPSU, RL); ns = p.place("junction", XPSU + 40, RN)
    pes = p.place("junction", XPSU + 80, RPE)
    p.wire(cb, "e0", lp, "w", num="L1", show=True)
    p.wire(cb, "e50", np_, "w", num="N1", show=True)
    p.wire(lp, "e", ls, "w")
    p.wire(np_, "e", ns, "w")
    p.wire(pe0, "e", pep, "w", num="PE", show=True)
    p.wire(pep, "e", pes, "w")

    # FX5U 本体
    plc = p.place("fx5u_power", XPLC, 330, label=pg.get("model", "FX5U"), comment="本体電源",
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 192)])
    p.wire(lp, "s", plc, "L"); p.wire(np_, "s", plc, "N"); p.wire(pep, "s", plc, "⏚")
    sp = pg.get("service_power", "unused")
    if sp == "unused":
        p.text(XPLC - 20, 430, "24+ / 0V:サービス電源 未使用(入出力は外部DC24V電源から供給)", 7)
    # DC24V 電源
    psu = p.place("psu_24v", XPSU, 330, label=pg.get("psu", "PS1"), comment=pg.get("psu_spec", "DC24V"),
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 152)])
    p.wire(ls, "s", psu, "L"); p.wire(ns, "s", psu, "N"); p.wire(pes, "s", psu, "⏚")

    # P / N へ
    YN, YP = 500, 540
    nj = p.place("junction", XPSU + 40, YN)
    pj = p.place("junction", XPSU, YP)
    ne = p.place("junction", XEND, YN)
    pe_ = p.place("junction", XEND, YP)
    p.wire(psu, "-V", nj, "n"); p.wire(nj, "e", ne, "w", num=LANE["N"], show=True)
    p.wire(psu, "+V", pj, "n"); p.wire(pj, "e", pe_, "w", num=LANE["P"], show=True)
    p.text(XEND + 12, YN - 9, f"{LANE['N']} → 各ページ", 9, True)
    p.text(XEND + 12, YP - 9, f"{LANE['P']} → 各ページ", 9, True)
    return p


def build_power_page_dc(pg, cfg, symbols):
    """DC電源タイプ: AC電源 → ブレーカ → DC24V電源 → P/N(入出力ページへ)、
    P → サーキットプロテクタ → 本体[+]、N → 本体[-]"""
    p = Page(symbols)
    RL, RN, RPE = 150, 200, 250
    X0, XCB, XPSU, XPLC, XEND = 60, 180, 340, 700, 1000
    YN, YP = 500, 540

    p.text(30, 70, pg.get("ac", "AC100V 50/60Hz"), 10, True)
    for name, y in (("L", RL), ("N", RN), ("PE", RPE)):
        p.text(X0 - 28, y - 9, name, 9, True)
    l0 = p.place("junction", X0, RL)
    n0 = p.place("junction", X0, RN)
    pe0 = p.place("junction", X0, RPE)
    cb = p.place("breaker_2p", XCB, RL, label=pg.get("cb", "CB1"), comment=pg.get("cb_spec", ""),
                 texts=[("label", -16, -30, 9, True), ("comment", -16, 58, 7, False)])
    p.wire(l0, "e", cb, "w0", num="L", show=False)
    p.wire(n0, "e", cb, "w50", num="N", show=False)

    # DC24V 電源
    psu = p.place("psu_24v", XPSU, 330, label=pg.get("psu", "PS1"), comment=pg.get("psu_spec", "DC24V"),
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 152)])
    ls = p.place("junction", XPSU, RL); ns = p.place("junction", XPSU + 40, RN)
    p.wire(cb, "e0", ls, "w", num="L1", show=True); p.wire(ls, "s", psu, "L")
    p.wire(cb, "e50", ns, "w", num="N1", show=True); p.wire(ns, "s", psu, "N")
    pes = p.place("junction", XPSU + 80, RPE)
    pep = p.place("junction", XPLC + 80, RPE)
    p.wire(pe0, "e", pes, "w", num="PE", show=True)
    p.wire(pes, "e", pep, "w")
    p.wire(pes, "s", psu, "⏚")

    # P / N へ(本体の電源もここから取る)
    nj = p.place("junction", XPSU + 40, YN)
    pj = p.place("junction", XPSU, YP)
    nb = p.place("junction", XPLC + 40, YN)
    pb = p.place("junction", XPLC, YP)
    ne = p.place("junction", XEND, YN)
    pe_ = p.place("junction", XEND, YP)
    p.wire(psu, "-V", nj, "n")
    p.wire(nj, "e", nb, "w", num=LANE["N"], show=True); p.wire(nb, "e", ne, "w")
    p.wire(psu, "+V", pj, "n")
    p.wire(pj, "e", pb, "w", num=LANE["P"], show=True); p.wire(pb, "e", pe_, "w")
    p.text(XEND + 12, YN - 9, f"{LANE['N']} → 各ページ", 9, True)
    p.text(XEND + 12, YP - 9, f"{LANE['P']} → 各ページ", 9, True)

    # 本体(DC電源)
    cp = p.place("cp_1p", XPLC, 580, label=pg.get("cp", "CP1"), comment=pg.get("cp_spec", ""),
                 texts=[("label", 12, 4, 9, True), ("comment", 12, 20, 7, False)])
    p.wire(pb, "s", cp, "n")
    model = pg.get("model", "FX5U")
    terms = "電源コネクタ 1(赤)=+24V 2(黒)=0V 3=アース" if model.upper().startswith("FX5UC") else "本体電源 DC24V"
    plc = p.place("fx5_power_dc", XPLC, 680, label=model, comment=terms,
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 192)])
    p.wire(cp, "s", plc, "+", num="P1", show=True)
    p.wire(nb, "s", plc, "-")
    p.wire(pep, "s", plc, "⏚")
    return p


# ============================================================ 表紙・改訂履歴・目次
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


def build_cover(cfg, symbols, latest_rev):
    p = Page(symbols)
    dx = 20 + BORDER_COLS * COL_SIZE // 2 - 470 - 260   # 枠(幅940)を図枠の中央に
    p.text(dx + 300, 170, cfg.get("customer", ""), 14)
    p.text(dx + 300, 220, cfg["machine"], 28, True)
    p.text(dx + 300, 290, "電気図面", 24, True)
    rows = [["図番", cfg["drawing_no"]], ["最新改訂", latest_rev], ["作成日", fmt_date(cfg["date"])],
            ["作成", cfg["author"]], ["会社", cfg["company"]]]
    for i, (k, v) in enumerate(rows):
        y = 400 + i * 40
        p.line(dx + 300, y + 36, dx + 900, y + 36, 0.8)
        p.text(dx + 310, y + 8, k, 11, True)
        p.text(dx + 460, y + 8, v, 12)
    p.rect(dx + 260, 130, 940, 620, dash=False, width=2.0)
    return p


def build_revision_pages(cfg, symbols, revs, per_page=19):
    cols = [("改訂", 70), ("日付", 120), ("変更内容", BORDER_COLS * COL_SIZE - 2 * (TABLE_X0 - 20) - 570), ("対象ページ", 200), ("作成", 90), ("承認", 90)]
    pages = []
    chunks = [revs[i:i + per_page] for i in range(0, max(len(revs), 1), per_page)] or [[]]
    for ci, chunk in enumerate(chunks):
        p = Page(symbols)
        p.text(TABLE_X0, 60, "改訂履歴(全ページ共通)" + (f"  {ci + 1}/{len(chunks)}" if len(chunks) > 1 else ""), 14, True)
        rows = [[r.get("改訂", ""), r.get("日付", ""), r.get("変更内容", ""), r.get("対象ページ", ""),
                 r.get("作成", ""), r.get("承認", "")] for r in chunk]
        rows += [[""] * len(cols)] * (per_page - len(rows))   # 空行で表を埋める
        table(p, TABLE_X0, TABLE_Y0, cols, rows)
        pages.append(("改訂履歴" if len(chunks) == 1 else f"改訂履歴 {ci + 1}", p))
    return pages


def build_toc_pages(cfg, symbols, entries, per_col=19):
    """entries: [(ページ番号, 名称)]。1ページ2列(左右)"""
    cols = [("頁", 60), ("図面名称", HALF_W - 120)]          # 2つの表で図枠の幅いっぱいを使う
    per_page = per_col * 2
    pages = []
    for start in range(0, len(entries), per_page):
        p = Page(symbols)
        p.text(50, 60, "目次", 14, True)
        chunk = entries[start:start + per_page]
        for side, sub in enumerate((chunk[:per_col], chunk[per_col:])):
            # 右の表は中身がなくても枠を描く(あとでページが増えたときに書き足せるように)
            rows = [[n, t] for n, t in sub] + [["", ""]] * (per_col - len(sub))
            table(p, 50 + side * HALF_W, TABLE_Y0, cols, rows)
        pages.append(("目次", p))
    return pages


def fmt_date(d):
    d = str(d)
    return f"{d[:4]}/{d[4:6]}/{d[6:8]}" if len(d) == 8 and d.isdigit() else d


BUILDERS = {"input": (build_input_page, "X"), "output": (build_output_page, "Y")}


# ------------------------------------------------------------ 図枠(日本語・下部2段)
TITLEBLOCK_NAME = "JP_A3_2dan"


def titleblock_xml():
    tb = ET.Element("titleblocktemplate", name=TITLEBLOCK_NAME)
    ET.SubElement(tb, "information").text = "日本語 下部2段 図枠(改訂履歴は別ページ)"
    ET.SubElement(tb, "logos")
    grid = ET.SubElement(tb, "grid", rows="25;25;", cols="t16%;t20%;t12%;t12%;t10%;t10%;r100%;")

    def field(row, col, name, value, label, colspan=0, size=9, show_label=True, align="center"):
        f = ET.SubElement(grid, "field", row=str(row), col=str(col), name=name,
                          displaylabel="true" if show_label else "false",
                          align=align, valign="center", hadjust="true", fontsize=str(size))
        if colspan > 0:  # QElectroTech の colspan は「右に追加で結合する列数」
            f.set("colspan", str(colspan))
        v = ET.SubElement(f, "value")
        for lang in ("ja", "en"):
            ET.SubElement(v, "translation", lang=lang).text = value
        lb = ET.SubElement(f, "label")
        for lang in ("ja", "en"):
            ET.SubElement(lb, "translation", lang=lang).text = label

    # 上段: 会社名 / 装置名 / 図面名称
    field(0, 0, "company", "%{company}", "会社", show_label=False, size=10)
    field(0, 1, "machine", "%{machine}", "装置名", colspan=1, size=10)
    field(0, 3, "title", "%title", "図面名称", colspan=3, size=11, show_label=False)
    # 下段: 図番 / 日付 / 改訂 / 作成 / 検図 / 承認 / ページ
    field(1, 0, "drawing_no", "%{drawing_no}", "図番", size=9)
    field(1, 1, "date", "%date", "日付", size=8)
    field(1, 2, "rev", "%indexrev", "改訂", size=9)
    field(1, 3, "author", "%author", "作成", size=8)
    field(1, 4, "checker", "%{checker}", "検図", size=8)
    field(1, 5, "approver", "%{approver}", "承認", size=8)
    field(1, 6, "page", "%{folio-id} / %{folio-total}", "頁", size=10)
    return tb


# ------------------------------------------------------------ プロジェクト出力
def add_diagram(proj, cfg, title, order, page):
    dg = ET.SubElement(proj, "diagram", {
        "title": title, "author": cfg["author"], "date": cfg["date"],
        "indexrev": cfg["revision"], "folio": "%id/%total", "order": str(order),
        "cols": str(BORDER_COLS), "colsize": str(COL_SIZE),
        "rows": str(BORDER_ROWS), "rowsize": str(ROW_SIZE),
        "displaycols": "true", "displayrows": "true", "displayAt": "bottom",
        "titleblocktemplate": TITLEBLOCK_NAME, "titleblocktemplateCollection": "embedded",
        "version": "0.100.0", "freezeNewConductor": "false", "freezeNewElement": "false",
        "filename": "", "plant": "", "locmach": "", "auto_page_num": "", "uuid": u(),
    })
    dprops = ET.SubElement(dg, "properties")
    for k in ("company", "machine", "drawing_no", "checker", "approver"):
        ET.SubElement(dprops, "property", name=k, show="1").text = cfg.get(k, "")
    ET.SubElement(dg, "defaultconductor", type="multi", num="_", displaytext="1", numsize="7",
                  condsize="1", horizrotatetext="0", vertirotatetext="270")
    for tag, items in (("elements", page.elements), ("conductors", page.conductors), ("inputs", page.texts)):
        holder = ET.SubElement(dg, tag)
        for it in items:
            holder.append(it)
    shapes = ET.SubElement(dg, "shapes")
    for sh in page.shapes:
        shapes.append(sh)


def build_project(cfg, pages_rows):
    cfg = project_config(cfg)
    symbols = build_symbols()
    proj = ET.Element("project", title=cfg["project_title"], version="0.100.0")
    props = ET.SubElement(proj, "properties")
    ET.SubElement(props, "property", name="saveddate", show="1").text = cfg["date"]
    ET.SubElement(proj, "titleblocktemplates").append(titleblock_xml())

    nd = ET.SubElement(proj, "newdiagrams")
    ET.SubElement(nd, "border", cols=str(BORDER_COLS), colsize=str(COL_SIZE),
                  rows=str(BORDER_ROWS), rowsize=str(ROW_SIZE), displaycols="true", displayrows="true")
    # クロスリファレンスの表示: 位置は「ページ-列行」(例 5-12C)
    xr = ET.SubElement(nd, "xrefs")
    for t, disp, snap in (("coil", "contacts", "label"), ("protection", "cross", "label"),
                          ("commutator", "cross", "label")):
        ET.SubElement(xr, "xref", type=t, displayhas=disp, snapto=snap, offset="0",
                      master_label="%f-%c%l", slave_label="(%f-%c%l)", showpowerctc="false",
                      xrefpos="AlignRight", switchprefix="", delayprefix="", powerprefix="")
    ET.SubElement(nd, "inset", title="", author=cfg["author"], folio="%id/%total",
                  date="null", displayAt="bottom", indexrev=cfg["revision"],
                  titleblocktemplate=TITLEBLOCK_NAME, titleblocktemplateCollection="embedded")

    ZONE["col_start"] = int(cfg.get("zone_col_start", 1))
    LANE["P"] = cfg.get("power", {}).get("P_name", "P24")
    LANE["N"] = cfg.get("power", {}).get("N_name", "N24")
    xref_reset(xref_devices(pages_rows, cfg))
    body = []
    pages_of = {}          # id(pg) → その設定から作ったページ(構成ページの参照に使う)
    shared = None          # 右半分が空いている増設ユニットのページ(body の番号)
    for pg, rows in pages_rows:
        first = len(body)
        single = fx_single_half(pg, rows["in"], rows["out"]) if pg["kind"] == "fx5ext" else None
        if single and shared is not None:
            # 入力だけ・出力だけの小さいユニットは、前のユニットの右半分に並べる
            title, page = body[shared]
            body[shared] = (title + " / " + fx_draw_single_half(page, HALF_W, pg, cfg, single), page)
            pages_of[id(pg)] = [page]
            shared = None
            continue
        if single:
            page = Page(symbols)
            body.append((fx_draw_single_half(page, 0, pg, cfg, single), page))
            shared = len(body) - 1
            pages_of[id(pg)] = [page]
            continue
        shared = None
        if pg["kind"] in ("fx5u", "fx5ext"):
            body += build_fx5u_pages(pg, cfg, symbols, rows["in"], rows["out"])
        elif pg["kind"] in ("fx5analog", "iqranalog", "qanalog", "remoteanalog"):
            spec = {"iqranalog": IQR_ANALOG, "qanalog": Q_ANALOG, "fx5analog": FX5_ANALOG_SPECS, "remoteanalog": REMOTE_ANALOG}[pg["kind"]][pg["model"].upper()]
            page_channels = analog_page_channels(pg['kind'],spec)
            count = (len(spec["channels"]) + page_channels-1) // page_channels
            for part in range(count):
                title = pg.get("title", pg["model"] + " アナログ端子")
                if count > 1: title += f" ({part + 1}/{count})"
                body.append((title, build_fx_analog_page(pg, cfg, symbols, rows, part * page_channels)))
        elif pg["kind"] in ("kvbody", "nxbody"):
            from renderers.plc_configuration import build_pages
            body.extend(build_pages(pg, symbols))
        elif pg["kind"] == "unit_diagram":
            from renderers.unit_diagrams import build_pages
            body.extend(build_pages(pg, UNIT_DIAGRAMS[pg["model"].upper()], symbols))
        elif pg["kind"] == "kv_io":
            from renderers.keyence import build_pages
            body.extend(build_pages(pg, KV_IO[pg["model"].upper()], symbols))
        elif pg["kind"] in ("remotepulse", "mxio"):
            from renderers.terminal_pages import build_pages
            spec = (REMOTE_PULSE if pg['kind'] == 'remotepulse' else MX_IO)[pg['model'].upper()]
            body += build_pages(pg, spec, symbols, rows)
        elif pg["kind"] == "inverter":
            from renderers.inverter import build_body
            body.append((pg.get("title", pg["model"]), build_body(pg, INVERTERS[pg["model"].upper()], symbols)))
        elif pg["kind"] == "mxbody":
            from renderers.controllers import build_body
            body.append((pg.get('title', pg['model'] + ' 本体'), build_body(pg, MX_CPU[pg['model'].upper()], symbols)))
        elif pg["kind"] == "gotbody":
            from renderers.hmi import build_body
            body.append((pg.get('title', pg['model'] + ' 接続図'), build_body(pg, symbols, GOT_BODY[pg['model'].upper()], Page, Symbol, page_heading, (LANE, LANE_TOP_Y, ctext))))
        elif pg["kind"] == "gotoption":
            from renderers.hmi import build_options
            body.append((pg.get('title', 'GOT通信オプション'), build_options(pg, symbols, GOT_OPTION, Page, Symbol, page_heading)))
        elif pg["kind"] in ("qcomm", "iqrcomm", "fxcomm"):
            body.append((pg.get("title", "通信ユニット"), build_q_comm_page(pg, symbols)))
        elif pg["kind"] in ("remotebody", "remoteiolink"):
            body.append((pg.get("title", pg["model"] + " 通信・電源"), build_remote_body_page(pg, symbols)))
            if pg["kind"] == "remoteiolink":
                body += remote_connector_pages(pg, symbols, remote_spec(pg["model"].upper()))
        elif pg["kind"] == "fx5body":
            body.append((pg.get("title", pg["model"] + " 本体"), build_fx5_body_page(pg, symbols)))
        elif pg["kind"] in ("iqrbody", "qbody"):
            body += build_iqr_body_page(pg, symbols)
        elif pg["kind"] == "power":
            body.append((pg.get("title", "電源回路"), build_power_page(pg, cfg, symbols)))
        else:
            halves = iqr_halves(pg, rows)
            for i in range(0, len(halves), 2):
                part = halves[i:i + 2]
                title = pg.get("title", pg["model"]) if len(halves) <= 2 else f"{pg.get('title', pg['model'])} ({i // 2 + 1}/{(len(halves) + 1) // 2})"
                body.append((title, build_iqr_page(rows, pg, cfg, symbols, part)))
            for uc, _ in iqr_units(pg, rows):
                spec = configured_unit(uc)
                if spec.get('io_connectors') and not (pg['kind'] == 'remotemixed' and REMOTE_MIXED[pg['model'].upper()].get('io_connectors')):
                    body += remote_connector_pages(uc, symbols, spec)
                elif spec.get('sensor_pins'):
                    for start in range(0, spec['points'], 8):
                        title = f"{uc['model']} センサ端子 {start + 1}〜{min(start + 8, spec['points'])}"
                        body.append((title, build_sensor_connector_page(uc, symbols, start)))
        if pg['kind'] == 'remotemixed' and REMOTE_MIXED[pg['model'].upper()].get('io_connectors'):
            body += remote_connector_pages(pg, symbols, REMOTE_MIXED[pg['model'].upper()])
        pages_of[id(pg)] = [page for _, page in body[first:]]
        for page in pages_of[id(pg)]:
            if getattr(page, 'identity_headers', False):
                continue
            for text in page.texts:
                if float(text.get('y', '0')) > 60:
                    continue
                scope = pg.get('right', pg) if float(text.get('x', '0')) >= HALF_W else pg
                for model_key, tag_key in (('model','tag'), ('left_model','left_tag'), ('right_model','right_tag')):
                    model, tag = scope.get(model_key, ''), scope.get(tag_key, '').strip()
                    if model and tag and text.get('text', '').upper().startswith(model.upper()):
                        if model_key == 'left_model' and float(text.get('x','0')) >= HALF_W:
                            continue
                        if model_key == 'right_model' and float(text.get('x','0')) < HALF_W:
                            continue
                        text.set('text', tag + '  ' + text.get('text'))
                        break


    # 表紙 → 改訂履歴 → 目次 → 本文
    from project_wiring.data import normalize, page_identity
    from renderers import wiring as wiring_renderer
    wiring_references = []
    for pg, _ in pages_rows:
        wiring = normalize(pg.get('wiring'))
        targets = pages_of[id(pg)]
        for row in wiring['boundaries'] + wiring['connections']:
            if row['part'] > len(targets):
                raise ValueError(f"[{pg.get('model', '')}] 配線情報の分割ページ{row['part']}がありません（全{len(targets)}ページ）")
        for row in wiring['connections']:
            if not row['unit_tag'].strip():
                row['unit_tag'] = page_identity(pg)[1]
        for part, page in enumerate(targets, 1):
            wiring_references += wiring_renderer.apply(page, wiring, part, Symbol,
                                                       f"{pg.get('model', '')} 分割ページ{part}")
    wiring_renderer.link_references(wiring_references)
    if wiring_references:
        ET.SubElement(nd, 'report', label='%f-%c%l')

    from renderers.terminal_plan import build_pages as build_terminal_plan_pages
    body += build_terminal_plan_pages(pages_rows, symbols, Page, table, page_heading)

    revs = cfg.get("_revisions", [])
    latest = revs[-1].get("改訂", cfg["revision"]) if revs else cfg["revision"]
    front = []
    if cfg.get("front_pages", True):
        front.append(("表紙", build_cover(cfg, symbols, latest)))
        front += build_revision_pages(cfg, symbols, revs)
        n_toc = 1
        while True:   # 目次のページ数は総ページ数で決まるので収束するまで数え直す
            total = len(front) + n_toc + len(body)
            entries = [(i + 1, t) for i, (t, _) in enumerate(front)]
            entries += [(len(front) + i + 1, "目次") for i in range(n_toc)]
            entries += [(len(front) + n_toc + i + 1, t) for i, (t, _) in enumerate(body)]
            toc = build_toc_pages(cfg, symbols, entries)
            if len(toc) == n_toc:
                break
            n_toc = len(toc)
        front += toc

    nums = {id(page): i for i, (_, page) in enumerate(front + body, 1)}
    # 構成ページに各ユニットのページ番号を書く(ページ番号が決まってから)
    def page_of(pg_):
        got = pages_of.get(id(pg_))
        return nums[id(got[0])] if got else None
    for _, page in body:
        if hasattr(page, "post"):
            page.post(pages_rows, page_of)
    ref_errs = write_references(lambda pg_: nums[id(pg_)])
    if ref_errs:
        raise SystemExit("参照エラー:\n  " + "\n  ".join(ref_errs))
    n_links = sum(1 for c in LINES["contacts"] if c[1] in LINES["coil"])

    cfg = dict(cfg, revision=latest)
    stats = []
    for order, (title, page) in enumerate(front + body, 1):
        page.finish()
        add_diagram(proj, cfg, title, order, page)
        stats.append((title, len(page.elements), len(page.conductors)))

    col = ET.SubElement(proj, "collection")
    imp = ET.SubElement(col, "category", name="import")
    n = ET.SubElement(imp, "names")
    ET.SubElement(n, "name", lang="en").text = "Imported elements"
    ET.SubElement(n, "name", lang="ja").text = "取り込み要素"
    cat = ET.SubElement(imp, "category", name="plc_io")
    n = ET.SubElement(cat, "names")
    ET.SubElement(n, "name", lang="en").text = "PLC I/O"
    ET.SubElement(n, "name", lang="ja").text = "PLC I/O(試作)"
    for sym in symbols.values():
        cat.append(sym.to_xml())
    stats.append((f"区分参照 {n_links} 接点", 0, 0))
    return proj, stats


def validate(rows, pg):
    """iQ-R / Q のユニット: アドレスが機種・先頭アドレスどおりか、ピン指定が配置と合うか"""
    errs = []
    for uc, urows in iqr_units(pg, rows):
        unit = configured_unit(uc)
        tag = f"[{uc.get('csv') or uc['model']}] "
        if unit.get("input_voltages") and str(uc.get("input_voltage", unit["input_voltages"][0])) not in unit["input_voltages"]:
            errs.append(tag + f"{uc['model']} の入力電圧は {', '.join(unit['input_voltages'])} Vから選択してください")
        exp = unit_addrs(uc)
        got = [r["アドレス"].strip().upper() for r in urows]
        if got != exp:
            errs.append(tag + f"アドレスが {uc['model']} と一致しません(16進で {exp[0]}〜{exp[-1]} の {len(exp)} 点"
                        f"、先頭は project.json の start)")
        for i, r in enumerate(urows[:len(exp)]):
            given = r.get("コネクタピン", "").strip().upper()
            if given and given != unit["pins"][i]:
                errs.append(tag + f"{r['アドレス']}: ピン {given} は {uc['model']} の配置({unit['pins'][i]})と一致しません")
        if unit["io"] == "out":
            devs = [r["機器番号"].strip() for r in urows if r["機器番号"].strip()]
            for d in sorted({d for d in devs if devs.count(d) > 1}):
                errs.append(tag + f"機器番号重複: {d}")
    return errs


def validate_fx(pg, in_rows, out_rows):
    exp_in, exp_out = fx_expected(pg)
    errs = []
    if fx_spec(pg).get("sink_only") and pg.get("input_mode", "sink") != "sink":
        errs.append(f"[{pg['model']}] この入力ユニットはシンク入力のみ対応しています")
    for label, rows, exp in (("入力", in_rows, exp_in), ("出力", out_rows, exp_out)):
        got = [r["アドレス"].strip().upper() for r in rows]
        if not exp and not got:
            continue
        if not exp:
            errs.append(f"[{pg['model']}] {label}のないユニットに{label}のCSVが指定されています")
            continue
        if got != exp:
            missing = [a for a in exp if a not in got]
            extra = [a for a in got if a not in exp]
            errs.append(f"[{pg['model']} {label}] アドレスが機種と一致しません"
                        f"(8進数で {exp[0]}〜{exp[-1]} の {len(exp)} 点)"
                        + (f" 不足: {','.join(missing)}" if missing else "")
                        + (f" 余分: {','.join(extra)}" if extra else ""))
    # 出力(コイル・負荷)は1機器1か所。入力の接点は同じ機器を何度使ってもよい(リレー接点など)
    devs = [r["機器番号"].strip() for r in out_rows if r["機器番号"].strip()]
    for d in sorted({d for d in devs if devs.count(d) > 1}):
        errs.append(f"[{pg['model']} 出力] 機器番号重複: {d}")
    return errs


def write_iolist(path, pages_rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ユニット", "アドレス", "用途", "機器番号", "ピン/端子/コモン", "端子台番号", "線番"])
        for pg, rows in pages_rows:
            if pg['kind'] == 'unit_diagram':
                from renderers.unit_diagrams import terminal_records
                for section, terminal in terminal_records(UNIT_DIAGRAMS[pg['model'].upper()]):
                    w.writerow([pg['model'], terminal['signal'], terminal.get('purpose', ''), '',
                                section['name'] + ' ' + terminal.get('pin', ''), '', ''])
                continue
            if pg['kind'] == 'kv_io':
                kv_spec = KV_IO[pg['model'].upper()]
                for terminal in kv_spec.get('analog', {}).get('terminals', []):
                    w.writerow([pg['model'], terminal['signal'], terminal['purpose'], '', terminal['pin'], '', ''])
                module = kv_spec.get('module', {})
                for terminal in module.get('power', []):
                    w.writerow([pg['model'], terminal['signal'], '外部電源' if terminal['lane'] else '接地', '', '', '', ''])
                modes = module.get('modes', {})
                interfaces = modes[pg.get('communication_mode') or next(iter(modes))] if modes else module.get('interfaces', [])
                for interface in interfaces:
                    for terminal in interface.get('pinout', []):
                        w.writerow([pg['model'], terminal['signal'], terminal.get('description', ''), '',
                                    interface['name'] + ' ' + terminal['pin'], '', ''])
                for section in kv_spec['pages']:
                    for side, terminals in enumerate(section['halves']):
                        location = section.get('labels', ['', ''])[side] or section['section']
                        for pin, signal in terminals:
                            w.writerow([pg['model'], signal, '', '', f'{location} {pin}'.strip(), '', ''])
                continue
            if pg['kind'] in ('mxbody', 'inverter'):
                continue
            if pg['kind'] in ('mxio', 'remotepulse'):
                from renderers.terminal_pages import terminal_rows
                spec = (MX_IO if pg['kind'] == 'mxio' else REMOTE_PULSE)[pg['model'].upper()]
                for row in terminal_rows(pg, spec, rows):
                    w.writerow([pg['model'], row['signal'], row.get('description', ''), '', row.get('pin', ''), '', ''])
                continue
            if pg["kind"] in ("kvbody", "nxbody", "power", "fx5body", "iqrbody", "qbody", "qcomm", "iqrcomm", "fxcomm", "remotebody", "remoteiolink", "gotbody", "gotoption"):
                continue
            if pg["kind"] in ("fx5analog", "iqranalog", "qanalog", "remoteanalog"):
                for r in rows:
                    w.writerow([pg["model"], "CH" + r["CH"], r.get("用途", ""), "", "", "", ""])
                continue
            if pg["kind"] in ("fx5u", "fx5ext"):
                sp = fx_spec(pg)
                fmt = "+V{}" if sp["kind"] == "source" else "COM{}"
                com_of = {a: fmt.format(no) for no, addrs in sp["groups"] for a in addrs}
                for r in rows["in"] + rows["out"]:
                    a = r["アドレス"].strip().upper()
                    w.writerow([pg["model"], a, r["信号名"], r["機器番号"], com_of.get(a, fx_spec(pg).get("in_common", "S/S")), "",
                                r.get("線番", "").strip() or a])
                continue
            for uc, urows in iqr_units(pg, rows):
                unit = configured_unit(uc)
                for i, r in enumerate(urows):
                    a = r["アドレス"].strip().upper()
                    w.writerow([uc["model"], a, r["信号名"], r["機器番号"],
                                r.get("コネクタピン", "").strip() or unit["pins"][i],
                                r.get("端子台番号", "").strip() or tb_label(uc, i), r.get("線番", "").strip() or a])
                if unit.get("out") == "independent_relay":
                    for i, r in enumerate(urows):
                        w.writerow([uc["model"], r["アドレス"], "外部電源", "", unit["feed_pins"][i], "", ""])
                    continue
                commons = {"COM": unit["common"]} if unit["io"] == "in" else (
                    {"COM": unit["vplus"], "0V": unit["com"]} if unit["out"] == "source" else
                    {"V+": unit["vplus"], "COM": unit["com"]} if unit["out"] == "sink" else {"COM": unit["com"]})
                for pin, name in unit.get("extra_terminals", []):
                    w.writerow([uc["model"], name, "補助端子", "", pin, "", ""])
                for i, pin in enumerate(unit.get('paired_com_pins', [])):
                    name = unit.get('paired_com_labels', ['COM'] * unit['points'])[i]
                    w.writerow([uc['model'], name, 'コモン', '', pin, '', ''])
                if unit.get('paired_power_terminals'):
                    commons = {name:pin for name,pin,lane in unit['paired_power_terminals']}
                if unit.get("input_power_pin"):
                    commons["V+"] = unit["input_power_pin"]
                for name, pins in commons.items():
                    for group in pins if isinstance(pins, list) else [pins]:
                        for pin in group.split("/"):
                            if pin:
                                w.writerow([uc["model"], name, "共通", "", pin, tb_label(uc, pin=pin), ""])


def main(cfg_path, out_path):
    base = os.path.dirname(os.path.abspath(cfg_path))
    with open(cfg_path, encoding="utf-8") as f:
        cfg = project_config(json.load(f))
    if "units_file" in cfg:
        raise SystemExit("units_file は廃止されました。機種別定義フォルダを units_dir に指定してください")
    use_units(os.path.join(base, cfg["units_dir"]) if cfg.get("units_dir") else UNITS_DIR)
    pages_rows, errs, warnings = [], [], []
    def read(name):
        with open(os.path.join(base, name), 'rb') as f:
            data = f.read()
        try:
            content = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            content = data.decode('cp932')
        return list(csv.DictReader(io.StringIO(content, newline='')))

    rev_file = cfg.get("revisions_csv")
    cfg["_revisions"] = read(rev_file) if rev_file else []
    for pg in cfg["pages"]:
        from renderers.settings import LABELS, controls
        try:
            controls(pg)
            keys = [prefix + key for prefix in ('', 'left_', 'right_') for key in LABELS]
            if any(not isinstance(pg.get(key, ''), str) for key in keys):
                raise ValueError('通信・機器設定欄は文字列で指定してください')
        except ValueError as error:
            errs.append(str(error))
            continue
        if pg['kind'] in ('kvbody', 'nxbody'):
            from plc_configuration import validate as validate_configuration
            try:
                validate_configuration(pg, {'kv_io': KV_IO, 'unit_diagram': UNIT_DIAGRAMS})
            except ValueError as error:
                errs.append(str(error))
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'unit_diagram':
            model = str(pg.get('model', '')).upper()
            if model not in UNIT_DIAGRAMS:
                errs.append('未対応のユニットです: ' + model)
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'kv_io':
            model = str(pg.get('model', '')).upper()
            if model not in KV_IO:
                errs.append('未対応のKVユニットです: ' + model)
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'inverter':
            if str(pg.get('model', '')).upper() not in INVERTERS:
                errs.append('対応済みインバータを指定してください')
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] in ('remotepulse', 'mxbody', 'mxio'):
            definitions = {'remotepulse': REMOTE_PULSE, 'mxbody': MX_CPU, 'mxio': MX_IO}[pg['kind']]
            model = str(pg.get('model', '')).upper()
            if model not in definitions:
                errs.append('未対応の形名です: ' + model)
            elif pg['kind'] == 'mxbody' and cpu_option_error(pg, definitions[model]):
                errs.append(cpu_option_error(pg, definitions[model]))
            else:
                if pg['kind'] == 'mxbody':
                    from renderers.controllers import expansion_items
                    try:
                        expansion_items(pg)
                    except ValueError as error:
                        errs.append(str(error))
                rows = read(pg['csv']) if pg.get('csv') and pg['kind'] != 'mxbody' else None
                if pg['kind'] != 'mxbody':
                    from renderers.terminal_pages import terminal_rows
                    try:
                        terminal_rows(pg, definitions[model], rows)
                    except ValueError as error:
                        errs.append(f'[{model}] {error}')
                pages_rows.append((pg, rows))
            continue
        if pg['kind'] == 'gotbody':
            model = str(pg.get('model', '')).upper()
            spec = GOT_BODY.get(model)
            if spec is None:
                errs.append('対応済みGOT本体を指定してください')
            elif pg.get('battery', '要確認') not in ('装着', '非装着', '搭載不可', '要確認'):
                errs.append('GOTのバッテリ状態が不正です')
            elif not spec.get('battery_supported') and pg.get('battery') == '装着':
                errs.append('このGOTにはバッテリを装着できません')
            elif spec.get('battery_supported') and pg.get('battery') == '搭載不可':
                errs.append('このGOTはバッテリを装着可能です')
            elif pg.get('sd_card', '要確認') not in ('有', '無', '要確認'):
                errs.append('SDカード状態は有・無・要確認から選んでください')
            elif not spec.get('sd_card_supported') and pg.get('sd_card') == '有':
                errs.append('このGOTの本体SDカードスロットは使用できません')
            elif pg.get('serial_mode', '') and pg['serial_mode'] not in set(spec.get('serial_modes', {})).union(*(set(i.get('modes', {})) for i in spec['interfaces'])):
                errs.append('このGOTに対応するシリアル方式を指定してください')
            elif any(not isinstance(pg.get(k, ''), str) for k in ('ip', 'station', 'dip', 'sd_card_model')):
                errs.append('GOT設定欄は文字列で指定してください')
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'gotoption':
            models = [pg.get(k, '') for k in ('left_model', 'right_model')]
            if not any(models) or any(not isinstance(m, str) or m and m.upper() not in GOT_OPTION for m in models):
                errs.append('対応済みGOTオプションを左右に指定してください')
            elif any(not isinstance(pg.get(f'{side}_{key}', ''), str) for side in ('left', 'right') for key in ('station', 'ip', 'dip', 'module')):
                errs.append('GOTオプションの設定欄は文字列で指定してください')
            elif any(pg.get(f'{side}_module') and pg.get(f'{side}_module', '').upper() not in GOT_OPTION.get(str(pg.get(f'{side}_model', '')).upper(), {}).get('module_interfaces', {})
                     for side in ('left', 'right')):
                errs.append('GOTオプションの通信モジュールはその機種に対応するものを指定してください')
            else:
                pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("remotebody", "remoteiolink"):
            model = str(pg.get("model", "")).upper()
            spec = remote_spec(model)
            if not spec or (not spec.get("network") and spec.get("module_role") != "extension") or (pg["kind"] == "remoteiolink" and model not in REMOTE_IOLINK):
                errs.append("対応済みリモートIOを指定してください")
            elif any(not isinstance(pg.get(k, ""), str) for k in ("station", "ip", "dip")):
                errs.append("局番・IPアドレス・ディップスイッチは文字列で指定してください")
            else:
                pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("qcomm", "iqrcomm", "fxcomm"):
            values = [pg.get(k, "") for k in ("left_model", "right_model")]
            comm = {'iqrcomm': IQR_COMM, 'qcomm': Q_COMM, 'fxcomm': FX5_COMM}[pg['kind']]
            if any(not isinstance(m, str) for m in values) or not any(values) or any(m and m.upper() not in comm for m in values):
                errs.append("通信ページの左右には対応済みの同一シリーズの通信ユニットを少なくとも1台指定してください")
            elif any(not isinstance(pg.get(f"{side}_{key}", ""), str) for side in ("left", "right") for key in ("station", "ip", "dip")):
                errs.append("通信ユニットの局番・IPアドレス・ディップスイッチ設定は文字列で指定してください")
            else:
                pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("iqrbody", "qbody"):
            model, power_model, base_model = (str(pg.get(k, "")).upper() for k in ("model", "power_model", "base_model"))
            modules = pg.get("modules", [])
            is_q = pg["kind"] == "qbody"
            cpus, powers, bases, analog = (Q_CPU, Q_POWER, Q_BASE, Q_ANALOG) if is_q else (iqr_cpu_positions(), IQR_POWER, IQR_BASE, IQR_ANALOG)
            comm = Q_COMM if is_q else IQR_COMM
            series = "Q" if is_q else "R"
            def module_error(base, modules, reserved=0):
                """1段分のユニットの並びを調べる。問題なければ空文字。reserved: CPU が占めるスロット数(RnENCPU のネットワーク部)"""
                allowed = cpus.get(model, {}).get('compatible_modules')
                if allowed is not None and isinstance(modules, list) and any(m and m not in allowed for m in modules):
                    return 'このCPUに対応するユニットを指定してください'
                if isinstance(modules, list) and any(isinstance(m, str) and comm.get(m.upper(), {}).get('mount_position') == 'cpu_slot' for m in modules):
                    return 'リモートヘッドはCPUスロット（model）に指定してください'
                if not isinstance(modules, list) or len(modules) > bases[base]["slots"] - reserved or any(not isinstance(m, str) or (m and ((not m.upper().startswith(series) and m.upper() not in comm) or m.upper() not in IO_UNITS and m.upper() not in (Q_MIXED if is_q else IQR_MIXED) and m.upper() not in analog and m.upper() not in comm)) for m in modules):
                    return "スロット数またはユニット形名が不正です"
                if any(slot_definition(m.upper(), is_q).get("slots", 1) == 2 and
                                    (i + 1 >= bases[base]["slots"] - reserved or i + 1 < len(modules) and modules[i + 1])
                                    for i, m in enumerate(modules) if m):
                    return "2スロットユニットの次のスロットを空けてください"
                return ""
            extensions = pg.get("extensions", [])
            ext_err = ""
            limit=cpus.get(model,{}).get('max_extension_stages',7)
            if not isinstance(extensions, list) or len(extensions) > limit:
                ext_err = f"このCPUの増設ベースは{limit}段までのリストで指定してください"
            else:
                for i, ext in enumerate(extensions, 1):
                    eb, ep = str(ext.get("base_model", "")).upper(), str(ext.get("power_model", "")).upper()
                    if eb not in bases or not bases[eb].get("extension"):
                        ext_err = f"増設{i}段のベースは対応済みの増設ベースを指定してください"
                    elif bases[eb].get("power_required", True) and ep not in powers:
                        ext_err = f"増設{i}段の電源ユニットを指定してください"
                    elif not bases[eb].get("power_required", True) and ep:
                        ext_err = f"増設{i}段のベース {eb} は電源ユニットを使いません"
                    else:
                        ext_err = module_error(eb, ext.get("modules", []))
                        ext_err = f"増設{i}段: {ext_err}" if ext_err else ""
                    if ext_err:
                        break
            if model not in cpus or power_model not in powers or base_model not in bases or bases[base_model].get("extension"):
                errs.append("構成には対応済みのCPU、電源、ベース(基本ベース)を指定してください")
            elif module_error(base_model, modules, cpus[model].get("network_part", {}).get("slots", 0)):
                errs.append(module_error(base_model, modules, cpus[model].get("network_part", {}).get("slots", 0)))
            elif ext_err:
                errs.append(ext_err)
            elif cpus[model].get('max_module_slots') and sum(bases[b]['slots'] for _,b,_,_ in body_stages(pg))>cpus[model]['max_module_slots']:
                errs.append(f"このCPUの合計スロット数は{cpus[model]['max_module_slots']}までです")
            elif not str(pg.get("empty_slot_points", EMPTY_SLOT_POINTS)).isdigit():
                errs.append("空きスロットの点数(empty_slot_points)は0以上の整数で指定してください")
            elif pg.get("battery", "要確認") not in ("装着", "非装着", "要確認"):
                errs.append("バッテリ状態は装着・非装着・要確認から選んでください")
            elif cpu_option_error(pg,cpus[model]):
                errs.append(cpu_option_error(pg,cpus[model]))
            elif slot_assignments(pg)[1]:
                errs += slot_assignments(pg)[1]
            else:
                warnings += slot_assignments(pg)[2]
                pages_rows.append((pg, None))
            continue
        if pg["kind"] == "fx5body":
            model = pg.get("model", "").upper()
            modules = pg.get('modules', [])
            if model not in FX5U_SPECS or any(FX5U_SPECS[model][key] is None for key in ("battery_supported", "usb_port", "analog", "rs485", "service")):
                errs.append(f"本体図の機種定義が未対応です: {pg.get('model', '')}")
            elif not isinstance(modules, list) or any(not isinstance(m, str) or m.upper() not in FX5_COMM for m in modules):
                errs.append('FX5本体の通信ユニット形名が不正です')
            elif model.startswith('FX5UC-') and any(FX5_COMM[m.upper()]['form'] == 'board' for m in modules):
                errs.append('FX5UCには通信ボードを装着できません')
            elif sum(FX5_COMM[m.upper()]['form'] == 'board' for m in modules) > 1:
                errs.append('FX5の通信ボードは1台までです')
            elif pg.get('board_model', '') not in ('', 'なし', *FX5_BOARDS):
                errs.append('拡張ボードの型式が不正です')
            elif model.startswith('FX5UC-') and pg.get('board_model', '') not in ('', 'なし'):
                errs.append('FX5UCには拡張ボードを装着できません')
            elif pg.get('board_model') == 'FX5-SDCD' and not model.startswith('FX5S-'):
                errs.append('FX5-SDCDはFX5S専用です')
            elif any(FX5_COMM[m.upper()]['form'] == 'board' and pg.get('board_model', '') not in ('', m.upper()) for m in modules):
                errs.append('拡張ボードの指定が重複しています')
            elif sum(FX5_COMM[m.upper()]['form'] == 'adapter' for m in modules) > (2 if model.startswith('FX5UJ-') else 4):
                errs.append('FX5の通信アダプタの台数が上限を超えています')
            elif pg.get('sd_card', '要確認') not in ('有', '無', '要確認'):
                errs.append('SDカードの状態は有・無・要確認から選んでください')
            elif not isinstance(pg.get('sd_card_model', ''), str):
                errs.append('SDカードの型式は文字列で指定してください')
            elif model.startswith('FX5S-') and pg.get('board_model') != 'FX5-SDCD' and (pg.get('sd_card') == '有' or pg.get('sd_card_model', '').strip()):
                errs.append('FX5SでSDカードを使用するには拡張ボードにFX5-SDCDを選択してください')
            else:
                supported = FX5U_SPECS[model]["battery_supported"]
                battery = pg.get("battery", "要確認" if supported else "搭載不可")
                if battery not in ("装着", "非装着", "搭載不可", "要確認"):
                    errs.append(f"電池の指定が不正です: {battery}")
                elif battery == "搭載不可" and supported:
                    errs.append(f"[{pg['model']}] オプション電池が使用できるため「搭載不可」は指定できません")
                elif not supported and battery != "搭載不可":
                    errs.append(f"[{pg['model']}] バッテリは搭載できません")
                pages_rows.append((pg, None))
            continue
        if pg["kind"] == "power":
            pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("fx5analog", "iqranalog", "qanalog", "remoteanalog"):
            model = pg.get("model", "").upper()
            analog_specs = {"iqranalog": IQR_ANALOG, "qanalog": Q_ANALOG, "fx5analog": FX5_ANALOG_SPECS, "remoteanalog": REMOTE_ANALOG}[pg["kind"]]
            if model not in analog_specs:
                errs.append(f"未対応のアナログ機種です: {model}")
                continue
            rows = read(pg["csv"]) if pg.get("csv") else []
            seen = set()
            for r in rows:
                ch = r.get("CH", "").strip()
                if not ch.isascii() or not ch.isdecimal() or not 1 <= int(ch) <= len(analog_specs[model]["channels"]):
                    errs.append(f"[{model}] CHが不正です: {ch}")
                elif int(ch) in seen:
                    errs.append(f"[{model}] CHが重複しています: {ch}")
                else:
                    seen.add(int(ch))
                    r["CH"] = str(int(ch))
                    method = r.get("方式", "").strip()
                    if method:
                        spec_a = analog_specs[model]
                        direction = spec_a["channels"][int(ch) - 1]
                        if spec_a.get("auto_wiring") is False:
                            errs.append(f"[{model}] 自動配線は未対応です。方式を空欄にしてメーカー配線図に従って手動で接続してください")
                        elif method not in ("電圧", "電流"):
                            errs.append(f"[{model}] CH{ch} の方式は 電圧 か 電流 で指定してください: {method}")
                        elif not analog_method_pins(analog_names(spec_a, int(ch) - 1), direction, method):
                            errs.append(f"[{model}] CH{ch} は {method}{direction}の自動配線に対応していません(端子は手で配線)")
            pages_rows.append((pg, rows))
            continue
        if pg["kind"] in ("qmixed", "iqrmixed", "remotemixed"):
            model = str(pg.get("model", "")).upper()
            if model not in ({"qmixed": Q_MIXED, "iqrmixed": IQR_MIXED, "remotemixed": REMOTE_MIXED}[pg["kind"]]):
                errs.append("混合ユニットの形名を指定してください")
                continue
            try:
                start = int(str(pg.get("start", "0")), 16)
                if start < 0: raise ValueError()
            except ValueError:
                errs.append(f"[{model}] 先頭アドレスは0以上の16進数で指定してください")
                continue
            rows = {"in": read(pg["input_csv"]) if pg.get("input_csv") else None,
                    "out": read(pg["output_csv"]) if pg.get("output_csv") else None}
            for uc, _ in iqr_units(pg, {"in": [], "out": []}):
                if rows[uc["_mixed_io"]] is None:
                    rows[uc["_mixed_io"]] = blank_io_rows(uc)
            errs += validate(rows, pg)
        elif pg["kind"] in ("fx5u", "fx5ext"):
            rows = {"in": read(pg["input_csv"]) if pg.get("input_csv") else [],
                    "out": read(pg["output_csv"]) if pg.get("output_csv") else []}
            errs += validate_fx(pg, rows["in"], rows["out"])
        else:
            if not pg.get("csv") and str(pg.get("model", "")).upper() not in IO_UNITS:
                errs.append(f"[{pg.get('model', '')}] 対応済みの入出力ユニットを指定してください")
                continue
            rows = read(pg["csv"]) if pg.get("csv") else blank_io_rows(pg)
            if pg.get("right"):
                pg["_right_rows"] = read(pg["right"]["csv"])
            errs += validate(rows, pg)
        pages_rows.append((pg, rows))
    if errs:
        print("入力エラー:\n  " + "\n  ".join(errs))
        sys.exit(1)
    warnings += page_start_warnings(cfg["pages"])
    if warnings:
        # 割付の誤りらしきものは知らせるだけで、値は直さない
        print("警告（XY割付）:\n  " + "\n  ".join(warnings))
    try:
        proj, stats = build_project(cfg, pages_rows)
    except ValueError as error:
        raise SystemExit(f"入力エラー:\n  {error}") from error
    xml = minidom.parseString(ET.tostring(proj, encoding="unicode")).toprettyxml(indent="    ")
    xml = xml.split("\n", 1)[1]  # QElectroTech 形式に合わせ XML宣言を外す
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    list_path = out_path.rsplit(".", 1)[0] + "_iolist.csv"
    write_iolist(list_path, pages_rows)
    from project_wiring.data import terminal_rows, write_terminal_csv
    terminal_records = terminal_rows(pages_rows)
    if terminal_records:
        terminal_path = out_path.rsplit('.', 1)[0] + '_terminals.csv'
        write_terminal_csv(terminal_path, terminal_records)
        print(f"端子台接続表: {terminal_path}")
    for title, ne, nc in stats:
        print(f"  {title}: 要素 {ne} / 配線 {nc}")
    print(f"出力: {out_path}\n帳票: {list_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(*sys.argv[1:])
