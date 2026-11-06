"""コネクタの絵(正面図)の共通部品。

図面のどこで使っても同じ絵になるよう、コネクタの絵はここだけで定義する。
描き方の決まり:
  - 外形は太線の角丸、内部は細線
  - ピン: オスは黒丸、メスは白丸、性別未確認は位置だけ小さな細線の丸
  - D-sub 系の固定ねじは二重丸(中を塗る)
  - 高さはおおむね 40(USB・HDMI・SD は実物に合わせて小さく 18〜24)
  - 端子(ケーブル1本ぶんの接続点)は左に1つ
使い方: key = symbol(symbols, Symbol, 'dsub9', 'female') → p.place(key, x, y)
QET の部品として書き出す: python tools/export_connector_elements.py
"""
import math

FILL = 'filling:black'


def _fill(sym):
    """直前に描いた図形を塗りつぶす"""
    attrs = sym.parts[-1][1]
    attrs['style'] = attrs['style'].replace('filling:none', FILL)


def _pins(sym, pts, d, gender):
    """ピン: オスは黒丸、メスは白丸、性別未確認は位置だけ小さな細線の丸"""
    for x, y in pts:
        if gender in ('male', 'female'):
            sym.circle(x - d / 2, y - d / 2, d, fill=gender == 'male')
        else:
            sym.circle(x - 1, y - 1, 2)
            sym.parts[-1][1]['style'] = sym.parts[-1][1]['style'].replace('line-weight:normal', 'line-weight:thin')


def _screws(sym, xs, cy):
    for x in xs:
        sym.circle(x - 5, cy - 5, 10)
        sym.circle(x - 2, cy - 2, 4, fill=True)


# ------------------------------------------------------------ 各コネクタ(x0: 左端、cy: 中心の高さ)
def rj45(sym, x0, cy, gender=''):
    """RJ-45 ジャック: 角丸の外形、ラッチの切り欠き付きの開口、8本の接点、左右上の LED"""
    sym.rrect(x0, cy - 20, 40, 40, 3)
    t, b = cy - 12, cy + 7
    sym.polygon([(x0 + 6, t), (x0 + 34, t), (x0 + 34, b), (x0 + 26, b), (x0 + 26, b + 6),
                 (x0 + 14, b + 6), (x0 + 14, b), (x0 + 6, b)])
    for i in range(8):
        x = x0 + 9.5 + i * 3
        sym.line(x, t, x, t + 6, thin=True)
    sym.rect(x0 + 4, cy - 18, 5, 3); _fill(sym)
    sym.rect(x0 + 31, cy - 18, 5, 3); _fill(sym)


def dsub(count):
    """D-sub(9/15/25 ピン): 角丸のフランジ、固定ねじ、台形のシェル(二重線)、2段のピン"""
    top = (count + 1) // 2
    pitch = 9 if count == 9 else 7.5
    shell = (top - 1) * pitch + 20

    def draw(sym, x0, cy, gender=''):
        w = shell + 46
        sym.rrect(x0, cy - 20, w, 40, 5)
        _screws(sym, (x0 + 9, x0 + w - 9), cy)
        l, r = x0 + 23 - 5, x0 + 23 + shell + 5
        sym.polygon([(l, cy - 15), (r, cy - 15), (r - 5, cy + 15), (l + 5, cy + 15)])
        sym.polygon([(l + 3, cy - 12), (r - 3, cy - 12), (r - 7, cy + 12), (l + 7, cy + 12)], thin=True)
        mid = x0 + w / 2
        pts = []
        for row, n in enumerate((top, count - top)):
            for i in range(n):
                pts.append((mid - (n - 1) * pitch / 2 + i * pitch, cy - 5.5 + row * 11))
        _pins(sym, pts, 5, gender)
    draw.width = shell + 46
    return draw


def vga(sym, x0, cy, gender=''):
    """高密度D-sub 15極（VGA）：5極×3段。"""
    sym.rrect(x0, cy - 20, 102, 40, 5)
    _screws(sym, (x0 + 9, x0 + 93), cy)
    sym.polygon([(x0 + 25, cy - 15), (x0 + 77, cy - 15),
                 (x0 + 72, cy + 15), (x0 + 30, cy + 15)])
    _pins(sym, [(x0 + 35 + col * 8 + (row % 2) * 2, cy - 8 + row * 8)
                for row in range(3) for col in range(5)], 4, gender)
vga.width = 102


def dvi_d(sym, x0, cy, gender=''):
    """DVI-Dの共通外形。資料にないリンク数・実ピン数は描き分けない。"""
    sym.rrect(x0, cy - 20, 136, 40, 4)
    _screws(sym, (x0 + 9, x0 + 127), cy)
    sym.rrect(x0 + 23, cy - 15, 90, 30, 2)
    sym.rect(x0 + 29, cy - 10, 57, 20)
    sym.rect(x0 + 94, cy - 2, 13, 4)
    if gender == 'male':
        _fill(sym)
dvi_d.width = 136


def audio_jack(sym, x0, cy, gender=''):
    """3.5mm音声ジャックの正面。"""
    sym.circle(x0, cy - 15, 30)
    sym.circle(x0 + 5, cy - 10, 20)
    sym.circle(x0 + 10, cy - 5, 10)
audio_jack.width = 30


def gpib(sym, x0, cy, gender=''):
    """IEEE 488(GP-IB) 24 ピン: 角丸のフランジ、固定ねじ、台形のシェル、中央の舌に上下12本ずつの接点"""
    w = 130
    sym.rrect(x0, cy - 20, w, 40, 5)
    _screws(sym, (x0 + 9, x0 + w - 9), cy)
    sym.polygon([(x0 + 20, cy - 15), (x0 + w - 20, cy - 15), (x0 + w - 25, cy + 15), (x0 + 25, cy + 15)])
    sym.rect(x0 + 30, cy - 5, w - 60, 10)
    for i in range(12):
        x = x0 + 33 + i * (w - 66) / 11
        sym.line(x, cy - 5, x, cy - 2, thin=True)
        sym.line(x, cy + 2, x, cy + 5, thin=True)
gpib.width = 130


def minidin(count):
    """MINI-DIN(6/8 ピン): 丸いシェル(二重線)、下のキー溝、中央のキー、ピン"""
    layout = {8: ((-9, -9), (0, -11), (9, -9), (-12, 0), (12, 0), (-9, 8), (9, 8), (0, 8)),
              6: ((-9, -8), (0, -11), (9, -8), (-11, 3), (11, 3), (0, 9))}[count]

    def draw(sym, x0, cy, gender='male'):
        sym.circle(x0, cy - 22, 44)
        sym.circle(x0 + 5, cy - 17, 34, )
        sym.parts[-1][1]['style'] = sym.parts[-1][1]['style'].replace('line-weight:normal', 'line-weight:thin')
        sym.rect(x0 + 18, cy + 13, 8, 4); _fill(sym)
        sym.rect(x0 + 18, cy - 3, 8, 7)
        _pins(sym, [(x0 + 22 + px, cy + py) for px, py in layout], 4, gender or 'male')
    draw.width = 44
    return draw


def coax_f(sym, x0, cy, gender=''):
    """同軸 F形: 六角ナット、外導体、絶縁体、中心導体"""
    r = 21
    sym.polygon([(x0 + 22 + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 360, 60)])
    sym.circle(x0 + 22 - 15, cy - 15, 30)
    sym.circle(x0 + 22 - 10, cy - 10, 20)
    sym.circle(x0 + 22 - 3, cy - 3, 6, fill=True)
coax_f.width = 44


def coax_bnc(sym, x0, cy, gender=''):
    """同軸 BNC: 丸い外導体、左右のバヨネット突起、絶縁体、中心導体"""
    sym.circle(x0 + 2, cy - 20, 40)
    sym.rect(x0 - 3, cy - 3, 6, 6); _fill(sym)
    sym.rect(x0 + 39, cy - 3, 6, 6); _fill(sym)
    sym.circle(x0 + 22 - 14, cy - 14, 28)
    sym.circle(x0 + 22 - 9, cy - 9, 18)
    sym.parts[-1][1]['style'] = sym.parts[-1][1]['style'].replace('line-weight:normal', 'line-weight:thin')
    sym.circle(x0 + 22 - 3, cy - 3, 6, fill=True)
coax_bnc.width = 44


def optical(sym, x0, cy, gender=''):
    """光ファイバ(2心): 角丸の外形、送受2つの口とフェルール"""
    sym.rrect(x0, cy - 20, 48, 40, 4)
    for dx, name in ((5, 'TX'), (26, 'RX')):
        sym.rrect(x0 + dx, cy - 13, 17, 26, 2)
        sym.circle(x0 + dx + 4.5, cy - 4, 8)
        sym.circle(x0 + dx + 7, cy - 1.5, 3, fill=True)
        sym.label(x0 + dx + 2, cy + 30, name, 6)
optical.width = 48


def usb_minib(sym, x0, cy, gender=''):
    """USB Mini-B: 角丸の外形、下の角を落とした開口、中の舌片"""
    sym.rrect(x0, cy - 9, 28, 18, 2)
    sym.polygon([(x0 + 4, cy - 5), (x0 + 24, cy - 5), (x0 + 24, cy + 1), (x0 + 20, cy + 5),
                 (x0 + 8, cy + 5), (x0 + 4, cy + 1)])
    sym.rect(x0 + 8, cy - 2, 12, 3); _fill(sym)
usb_minib.width = 28


def usb_b(sym, x0, cy, gender=''):
    """USB Type-B。シェルの開口、中央の樹脂ブロック、上下の4接点。"""
    sym.rrect(x0, cy - 16, 32, 32, 3)
    sym.polygon([(x0 + 4, cy - 5), (x0 + 11, cy - 12), (x0 + 21, cy - 12),
                 (x0 + 28, cy - 5), (x0 + 28, cy + 12), (x0 + 4, cy + 12)], thin=True)
    sym.rect(x0 + 9, cy - 5, 14, 10)
    sym.parts[-1][1]['style'] = sym.parts[-1][1]['style'].replace('line-weight:normal', 'line-weight:thin')
    for x in (x0 + 12, x0 + 20):
        for y in (cy - 6, cy + 3):
            sym.rect(x - 1, y, 2, 3)
            _fill(sym)
    sym.line(x0 + 2, cy + 8, x0 + 4, cy + 8, thin=True)
    sym.line(x0 + 28, cy + 8, x0 + 30, cy + 8, thin=True)
usb_b.width = 32


def modular6(sym, x0, cy, gender=''):
    """6ピンモジュラージャック。開口、ばね接点、ラッチの受け。"""
    sym.rrect(x0, cy - 18, 38, 36, 3)
    sym.polygon([(x0 + 5, cy - 12), (x0 + 33, cy - 12), (x0 + 33, cy + 7),
                 (x0 + 26, cy + 7), (x0 + 26, cy + 13), (x0 + 12, cy + 13),
                 (x0 + 12, cy + 7), (x0 + 5, cy + 7)], thin=True)
    for i in range(6):
        x = x0 + 9 + i * 4
        sym.rect(x - 1, cy - 12, 2, 3)
        _fill(sym)
        sym.line(x, cy - 9, x, cy + 1, thin=True)
        sym.line(x, cy + 1, x + 1, cy + 3, thin=True)
    sym.line(x0 + 14, cy + 10, x0 + 24, cy + 10, thin=True)
modular6.width = 38


def usb_a(sym, x0, cy, gender=''):
    """USB Type-A: 角丸の外形、四角い開口、上半分の舌片(塗り)と4本の接点"""
    sym.rrect(x0, cy - 10, 40, 20, 2)
    sym.rect(x0 + 4, cy - 6, 32, 12)
    sym.rect(x0 + 7, cy - 6, 26, 5); _fill(sym)
    for i in range(4):
        sym.line(x0 + 11 + i * 6, cy + 1, x0 + 11 + i * 6, cy + 4, thin=True)
usb_a.width = 40


def usb_c(sym, x0, cy, gender=''):
    """USB Type-C: 角丸の外形、小判形の開口、中央の舌片(塗り)"""
    sym.rrect(x0, cy - 10, 40, 20, 2)
    sym.rrect(x0 + 5, cy - 6, 30, 12, 6)
    sym.rrect(x0 + 11, cy - 1.5, 18, 3, 1.5); _fill(sym)
usb_c.width = 40


def hdmi(sym, x0, cy, gender=''):
    """HDMI Type-A: 角丸の外形、下の角を落とした開口、中の舌片(塗り)"""
    sym.rrect(x0, cy - 11, 48, 22, 2)
    sym.polygon([(x0 + 4, cy - 7), (x0 + 44, cy - 7), (x0 + 44, cy + 1), (x0 + 39, cy + 6),
                 (x0 + 9, cy + 6), (x0 + 4, cy + 1)])
    sym.rect(x0 + 10, cy - 4, 28, 3); _fill(sym)
hdmi.width = 48


def sd(sym, x0, cy, gender=''):
    """SD カードスロット: 角丸の外形、細いスロット、カード(角を1つ落とす)"""
    sym.rrect(x0, cy - 12, 56, 24, 2)
    sym.rect(x0 + 4, cy - 2, 48, 4)
    sym.polygon([(x0 + 10, cy - 9), (x0 + 42, cy - 9), (x0 + 46, cy - 5), (x0 + 46, cy - 2),
                 (x0 + 10, cy - 2)], thin=True)
sd.width = 56


def bus(sym, x0, cy, gender=''):
    """バス接続(多芯の角形コネクタ): 角丸の外形、両端のラッチ、2段の接点"""
    sym.rrect(x0, cy - 20, 76, 40, 4)
    sym.rect(x0 + 3, cy - 8, 4, 16); _fill(sym)
    sym.rect(x0 + 69, cy - 8, 4, 16); _fill(sym)
    sym.rect(x0 + 11, cy - 12, 54, 24)
    for row in (-5, 5):
        for i in range(10):
            sym.rect(x0 + 14 + i * 5, cy + row - 2, 3, 4); _fill(sym)
bus.width = 76


def handheld32(sym, x0, cy, gender='female'):
    """ハンディ GOT 用 丸形 32 極: 丸いシェル(二重線)、キー、同心円上のピン"""
    sym.circle(x0, cy - 22, 44)
    sym.circle(x0 + 4, cy - 18, 36)
    sym.rect(x0 + 19, cy - 22, 6, 4); _fill(sym)
    pts = []
    for count, radius in ((14, 14), (12, 9), (6, 4)):
        for i in range(count):
            a = i * 2 * math.pi / count
            pts.append((x0 + 22 + radius * math.cos(a), cy + radius * math.sin(a)))
    _pins(sym, pts[:32], 2.5, gender or 'female')
handheld32.width = 44


def handheld42(sym, x0, cy, gender='female'):
    """ハンディ GOT 用 角形 42 極: 角丸の外形、内側の枠、6×7 のピン"""
    sym.rrect(x0, cy - 22, 70, 44, 4)
    sym.rrect(x0 + 5, cy - 17, 60, 34, 2)
    _pins(sym, [(x0 + 12 + c * 7.5, cy - 13 + r * 5.2) for r in range(6) for c in range(7)], 2.5, gender or 'female')
handheld42.width = 70


def circular(count, code):
    """M12 / 7/8 インチの丸形: ローレットの外輪(二重線)、キー、周上と中心のピン"""
    def draw(sym, x0, cy, gender=''):
        cx = x0 + 22
        sym.circle(x0, cy - 22, 44)
        sym.circle(x0 + 4, cy - 18, 36)
        sym.parts[-1][1]['style'] = sym.parts[-1][1]['style'].replace('line-weight:normal', 'line-weight:thin')
        if code == 'X':
            # X コード: 十字の仕切り
            sym.line(cx - 12, cy - 12, cx + 12, cy + 12, thin=True)
            sym.line(cx - 12, cy + 12, cx + 12, cy - 12, thin=True)
            outer = count
            pts = [(cx + 11 * math.cos(math.pi / 8 + i * math.pi / 4), cy + 11 * math.sin(math.pi / 8 + i * math.pi / 4)) for i in range(outer)]
        else:
            outer = count - 1
            pts = [(cx + 10 * math.cos(-math.pi / 4 + i * 2 * math.pi / outer), cy + 10 * math.sin(-math.pi / 4 + i * 2 * math.pi / outer)) for i in range(outer)]
            pts.append((cx, cy))
        # キー: A コードは上に1つ、L コードは上下に2つ、7/8 インチは下に1つ
        keys = {'A': (-1,), 'L': (-1, 1), '7/8': (1,)}.get(code, ())
        for k in keys:
            sym.rect(cx - 3, cy + k * 18 - (4 if k < 0 else 0), 6, 4); _fill(sym)
        _pins(sym, pts, 4 if code != 'L' else 5, gender)
    draw.width = 44
    return draw


def econ(sym, x0, cy, gender=''):
    """e-CON(4 極): 角丸の外形、上のロックレバー、4つの差込口"""
    sym.rrect(x0, cy - 14, 44, 30, 3)
    sym.rect(x0 + 12, cy - 20, 20, 6)
    for i in range(4):
        sym.rect(x0 + 6 + i * 9, cy - 4, 6, 10)
        if gender == 'male':
            _fill(sym)
econ.width = 44


def screw_terminal(count, rows=1):
    """ねじ端子台: 外形、端子ごとのねじ(丸に斜めの溝)"""
    per = (count + rows - 1) // rows
    pitch = 12 if per <= 5 else 4.6

    def draw(sym, x0, cy, gender=''):
        w = per * pitch + 8
        h = 24 if rows == 1 else 36
        sym.rect(x0, cy - h / 2, w, h)
        d = min(9, pitch - 1)
        for r in range(rows):
            y = cy - h / 2 + (h / rows) * (r + 0.5)
            for i in range(per):
                x = x0 + 4 + pitch * (i + 0.5)
                sym.circle(x - d / 2, y - d / 2, d)
                sym.line(x - d / 3, y + d / 3, x + d / 3, y - d / 3, thin=True)
    draw.width = per * pitch + 8
    return draw


def fcn(count):
    """FCN 形(MIL 系の角形多極): 角丸のシェル、両端の固定ねじ、中の枠に2段のピン"""
    per = count // 2

    def draw(sym, x0, cy, gender=''):
        w = per * 3.2 + 40
        sym.rrect(x0, cy - 16, w, 32, 3)
        _screws(sym, (x0 + 8, x0 + w - 8), cy)
        sym.rect(x0 + 17, cy - 9, w - 34, 18)
        sym.line(x0 + 17, cy - 5, x0 + 21, cy - 9, thin=True)       # 極性の面取り
        _pins(sym, [(x0 + 21 + i * 3.2, cy - 3.5 + r * 7) for r in range(2) for i in range(per)], 2.2, gender or 'female')
    draw.width = per * 3.2 + 40
    return draw


def mil(count):
    """MIL 形(角形多極): 角丸のシェル、上中央のキー、中の枠に2段のピン"""
    per = count // 2

    def draw(sym, x0, cy, gender=''):
        w = per * 4.5 + 20
        sym.rrect(x0, cy - 14, w, 28, 3)
        sym.rect(x0 + w / 2 - 6, cy - 18, 12, 4); _fill(sym)     # 極性キー
        sym.rect(x0 + 5, cy - 9, w - 10, 18)
        _pins(sym, [(x0 + 10 + i * 4.5, cy - 4 + r * 8) for r in range(2) for i in range(per)], 3, gender or 'female')
    draw.width = per * 4.5 + 20
    return draw


def proprietary(sym, x0, cy, gender=''):
    """専用コネクタ(形状の資料なし): 角丸の外形と斜線の窓"""
    sym.rrect(x0, cy - 16, 44, 32, 3)
    sym.rect(x0 + 6, cy - 10, 32, 20)
    for i in range(4):
        sym.line(x0 + 8 + i * 8, cy + 8, x0 + 14 + i * 8, cy - 8, thin=True)
proprietary.width = 44


def push_in(count):
    """ワンタッチ(プッシュイン)端子: 外形、電線の差込口と解除ボタン"""
    def draw(sym, x0, cy, gender=''):
        w = count * 9 + 6
        sym.rrect(x0, cy - 16, w, 32, 2)
        for i in range(count):
            x = x0 + 4 + i * 9
            sym.rect(x, cy - 12, 7, 7)                     # 差込口
            sym.rect(x + 1.5, cy + 1, 4, 10); _fill(sym)   # 解除ボタン
    draw.width = count * 9 + 6
    return draw


def power_plug(count):
    """電源コネクタ(角形・多極): 角丸の外形、上のキー、ピン"""
    def draw(sym, x0, cy, gender=''):
        w = count * 9 + 10
        sym.rrect(x0, cy - 14, w, 28, 4)
        sym.rect(x0 + w / 2 - 5, cy - 18, 10, 4); _fill(sym)
        _pins(sym, [(x0 + 9 + i * 9, cy) for i in range(count)], 5, gender)
        if gender not in ('male', 'female'):
            for i in range(count):
                sym.rect(x0 + 6.5 + i * 9, cy - 3, 5, 6)
    draw.width = count * 9 + 10
    return draw


# 種類 → (名前, 絵)。別名はここで1つの絵にまとめる
CONNECTORS = {
    'rj45': ('RJ-45', rj45),
    'dsub9': ('D-sub 9pin', dsub(9)),
    'dsub15': ('D-sub 15pin', dsub(15)),
    'dsub25': ('D-sub 25pin', dsub(25)),
    'vga': ('高密度D-sub 15pin', vga),
    'dvi_d': ('DVI-D', dvi_d),
    'audio_jack': ('3.5mm 音声ジャック', audio_jack),
    'gpib': ('IEEE 488 24pin', gpib),
    'minidin8': ('MINI-DIN 8pin', minidin(8)),
    'minidin6': ('MINI-DIN 6pin', minidin(6)),
    'coax_f': ('同軸 F形', coax_f),
    'coax_bnc': ('同軸 BNC', coax_bnc),
    'optical': ('光ファイバ 2心', optical),
    'usb_minib': ('USB Mini-B', usb_minib),
    'usb_a': ('USB Type-A', usb_a),
    'usb_b': ('USB Type-B', usb_b),
    'modular6': ('モジュラー 6pin', modular6),
    'usb_c': ('USB Type-C', usb_c),
    'hdmi': ('HDMI Type-A', hdmi),
    'sd': ('SD カード', sd),
    'bus': ('バス接続', bus),
    'handheld32': ('丸形 32極', handheld32),
    'handheld42': ('角形 42極', handheld42),
    'm12_a_5': ('M12 Aコード 5極', circular(5, 'A')),
    'm12_x_8': ('M12 Xコード 8極', circular(8, 'X')),
    'm12_l_5': ('M12 Lコード 5極', circular(5, 'L')),
    '7_8_5': ('7/8インチ 5極', circular(5, '7/8')),
    'econ_4': ('e-CON 4極', econ),
    'terminal_3': ('ねじ端子台 3極', screw_terminal(3)),
    'terminal_40': ('ねじ端子台 40極', screw_terminal(40, 2)),
    'fcn_40': ('FCN 40極', fcn(40)),
    'one_touch_5': ('ワンタッチ 5極', push_in(5)),
    'power_5': ('電源コネクタ 5極', power_plug(5)),
    'proprietary': ('専用コネクタ', proprietary),
}
ALIASES = {'usb': 'usb_minib', 'usb_mini_b': 'usb_minib', 'coax': 'coax_f', 'minidin': 'minidin8',
           'dsub9_male': ('dsub9', 'male'), 'dsub9_neutral': ('dsub9', '')}


# 極数つきの種類(terminal_18、mil_20 など)は必要になったときに作る
FAMILIES = {'terminal': ('ねじ端子台 {n}極', lambda n: screw_terminal(n, 1 if n <= 6 else 2)),
            'mil': ('MIL {n}極', mil), 'fcn': ('FCN {n}極', fcn), 'power': ('電源コネクタ {n}極', power_plug),
            'one_touch': ('ワンタッチ {n}極', push_in)}


def resolve(kind, gender=''):
    target = ALIASES.get(kind, kind)
    if isinstance(target, tuple):
        target, gender = target
    if target not in CONNECTORS:
        family, _, count = target.rpartition('_')
        if family in FAMILIES and count.isdigit():
            label, make = FAMILIES[family]
            CONNECTORS[target] = (label.format(n=count), make(int(count)))
        else:
            raise ValueError('未対応のコネクタ: ' + kind)
    return target, gender


def width(kind):
    target, _ = resolve(kind)
    draw = CONNECTORS[target][1]
    return getattr(draw, 'width', 40)


def draw(sym, kind, x0, cy, gender=''):
    """シンボルの中にコネクタの絵を描く(本体の箱の中に描くとき)"""
    target, gender = resolve(kind, gender)
    CONNECTORS[target][1](sym, x0, cy, gender)


def symbol(symbols, Symbol, kind, gender='', name=None, center=False, terminal='t', wired=True, terminal_side='left'):
    """コネクタ1個の部品を作って symbols に登録し、キーを返す。端子は左(ケーブル1本ぶん)。
    center=True なら原点を絵の中心に置く(リモート機器のページ用)。
    wired=False は絵だけ(ピンを別に端子として並べるとき。接続点が二重にならないよう端子を付けない)。
    terminal_side='right' は絵を左右反転せず、原点を絵の右端に置いて右へ接続する。"""
    target, gender = resolve(kind, gender)
    key = (name or 'conn_' + target + ('_' + gender if gender else '')) + ('' if wired else '_pic')
    if terminal_side == 'right':
        key += '_right'
    if key in symbols:
        return key
    label, fn = CONNECTORS[target]
    w = getattr(fn, 'width', 40)
    wired = wired and target != 'sd'       # SD カードは配線しないので端子なし
    if terminal_side == 'right':
        x0 = -w
        s = Symbol(key, 'コネクタ ' + label, w + 22, 60, w + 11, 30)
        if wired:
            s.terminal(terminal, 'e', 0, 0)
    elif center:
        x0 = -w / 2
        s = Symbol(key, 'コネクタ ' + label, w + 22, 60, w / 2 + 11, 30)
        if wired:
            s.terminal(terminal, 'w', x0, 0)
    else:
        x0 = 5
        s = Symbol(key, 'コネクタ ' + label, w + 15, 60, 0, 30)
        if wired:
            s.terminal(terminal, 'w', x0, 0)
    fn(s, x0, 0, gender)
    symbols[key] = s
    return key
