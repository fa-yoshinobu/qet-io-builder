"""MELSECのアナログ端子と配線図。"""
import re
from unit_catalog import (
    FX5_ANALOG_SPECS, IQR_ANALOG, Q_ANALOG, REMOTE_ANALOG
)
from drawing import (
    FX_IN_TEXTS, FX_IN_X, HALF_W, HEAD_X, IN_TEXTS, IN_X,
    LANE, LANE_TOP_Y, Page, ROW_PITCH, ROW_Y0, Symbol,
    comment_text, ctext, io_table_header, page_heading, unit_identity_header, vcenter
)
from renderers.analog import (
    channel_rows, extra_rows, readonly_symbol
)
from renderers.typography import (
    wrap2
)


LANE_POWER = {"+24V": "P", "24V": "P", "0V": "N", "24G": "N"}

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
    from .communication import draw_notes
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
            draw_notes(p, 30, 1200, ['※電流入力で V+ と I+ を短絡するかはメーカーの配線図で確認'])
    if spec.get('diagram_note'):
        draw_notes(p, 30, 1200, [spec['diagram_note']])
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
                p.power_lane_label(IN_X[name], LANE[name])
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
                # Qtの整数pixel文字送りと左右余白を含めて用途欄へ収める。
                comment = wrap2(comment, 116, 8)
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
            description = wrap2(description, 116, 8)
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
        draw_notes(p, 30, 1200, [note])
        next_y = [82, 82]
        lane_tops = {}
        if use_lanes:
            for name, offset in (('P', FX_IN_X['outer']), ('N', FX_IN_X['inner'])):
                offset += layout_offset
                p.power_lane_label(offset, LANE[name])
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
    draw_notes(p, 30, 1200, [note])
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
