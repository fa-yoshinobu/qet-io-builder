"""PLC回路図の部品定義。"""
from renderers import connectors as CONN
from drawing import (
    Symbol, box_symbol, draw_dsub9, draw_minidin8, draw_rj45, draw_usb_minib,
    rotate90, vcenter
)
from renderers.typography import (
    text_w
)


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
