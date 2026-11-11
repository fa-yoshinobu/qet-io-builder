"""リレー接点の割当と図面間参照。"""

from drawing import (
    BORDER_COLS, COL_SIZE, HALF_W, ROW_SIZE, ctext
)
from unit_catalog import (
    DEFAULT_RELAY_TYPES, configured_unit, iqr_units
)
from renderers.typography import (
    TEXT_MARGIN, text_w
)


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

LAMP_KINDS = {"PL", "L", "LAMP", "表示灯"}
