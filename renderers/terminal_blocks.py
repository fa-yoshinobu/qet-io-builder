"""中継端子台の現物記名と、接続ケーブルを通したPLC側ピンとの対応を描く。"""
from itertools import groupby


def relay_branch_pins(spec, branch):
    """PLC実ピンと分岐先MIL20ピンを、出力順・最後にコモンで返す。"""
    mil_pins = [row['pin'] for row in spec['relay_contacts']] + [spec['relay_common_pin']]
    return list(zip(branch['plc_pins'], mil_pins, strict=True))


def _build_relay_page(pg, spec, symbols):
    from gen_io_page import KV_IO, Page, Symbol, ctext, unit_identity_header, vcenter
    from .unit_diagrams import _power_wire, _rails

    branch = pg['branch']
    pin_pairs = relay_branch_pins(spec, branch)
    signals = {pin: signal for section in KV_IO[pg['plc_model']]['pages']
               for half in section['halves'] for pin, signal in half}
    # 二つのねじ端子と常開接点を一部品にする。制御側とは導体を結ばない。
    key = 'terminal_block_isolated_no'
    if key not in symbols:
        contact = Symbol(key, '独立a接点・負荷端子対', 60, 30, 54, 15)
        for y in (-9, 9):
            contact.circle(-8, y - 4, 8)
            contact.line(-32, y, -8, y)
        contact.line(-32, -9, -32, -4)
        contact.line(-32, 9, -40, -4)
        contact.terminal('upper', 'e', 0, -9)
        contact.terminal('lower', 'e', 0, 9)
        symbols[key] = contact

    page = Page(symbols)
    left, right = 405, 827
    top, pitch = 132, 36
    bottom = top + pitch * len(spec['relay_contacts'])
    unit_identity_header(page, pg, left, right - left)
    page.rect(left, 52, right, bottom, dash=False, width=1)
    page.line(left, 108, right, 108, width=0.5)
    power = spec['relay_supply']
    rails = _rails(page, [(None, row) for row in power], offset=150)
    for i, row in enumerate(power):
        y = 66 + i * 27
        pin = page.place('module_pin', left, y, label=row['terminal'], comment=row['signal'],
                         texts=[('label', 12, vcenter(9), 9, True), ('comment', 60, vcenter(9), 9, False)])
        _power_wire(page, rails, row, pin)
    page.extend_lanes([r[0] for r in rails.values()], bottom=bottom)
    ctext(page, 657, 67, 'TB1　外部電源　DC24V', 9, True)
    plc_common, mil_common = pin_pairs[-1]
    ctext(page, 657, 93, f"PLC {signals[plc_common]}（ピン{plc_common}） → {branch['connector']} ピン{mil_common}", 9)

    columns = (left, 490, 575, 660, right)
    headings = ('PLC出力', 'PLCピン', branch['connector'] + ' ピン', 'TB1端子（負荷記名）')
    for i, heading in enumerate(headings):
        ctext(page, (columns[i] + columns[i+1]) / 2, 120, heading, 8, True)
    for x in columns[1:-1]:
        page.line(x, 108, x, bottom, width=0.5)
    for i, (row, (plc_pin, mil_pin)) in enumerate(zip(spec['relay_contacts'], pin_pairs[:-1], strict=True)):
        y = top + pitch * (i + 0.5)
        page.line(left, y - pitch / 2, right, y - pitch / 2, width=0.5)
        for col, value in enumerate((signals[plc_pin], plc_pin, mil_pin)):
            ctext(page, (columns[col] + columns[col+1]) / 2, y, value, 9)
        # 記名板は上段が偶数（+）、下段が奇数（-）。
        load = [f'{terminal}（{mark}）' for terminal, mark in zip(row['terminals'], row['markings'], strict=True)]
        page.place(key, right, y, label=' / '.join(row['terminals']),
                   infos={'auxiliary1': load[1], 'auxiliary2': load[0]},
                   texts=[('auxiliary1', -117, -9 + vcenter(8), 8, True),
                          ('auxiliary2', -117, 9 + vcenter(8), 8, True)])
    page.text(30, 744, '負荷側は16点独立のa接点。各接点の端子番号に続く（　）は記名板裏面の負荷番号。', 8)
    title = pg.get('title') or (spec['model'] + ' リレー端子台')
    return [(title, page)]


def build_pages(pg, spec, symbols):
    from gen_io_page import Page, Symbol, ctext, text_w, unit_identity_header, vcenter

    if 'relay_contacts' in spec:
        return _build_relay_page(pg, spec, symbols)
    banks = {}
    for row in spec['connections']:
        banks.setdefault(row['bank'], []).append(row)
    if not 1 <= len(banks) <= 2:
        raise ValueError(f"{spec['model']}: 中継端子台図の段数が範囲外です")

    page = Page(symbols)
    width = 220 * len(banks)
    left = 640 - width // 2
    top, pitch = 85, 30
    bottom = top + pitch * max(map(len, banks.values()))
    notes = spec.get('notes', [])
    if bottom > 772 - len(notes) * 17:
        raise ValueError(f"{spec['model']}: 中継端子台の端子が1枚に収まりません")
    unit_identity_header(page, {**pg, 'model': spec['model']}, left, width)
    page.rect(left, 52, left + width, bottom, dash=False, width=1)
    page.line(left, 69, left + width, 69, width=0.5)
    page.line(left, top, left + width, top, width=0.5)

    for side, (bank, rows) in enumerate(banks.items()):
        rows = sorted(rows, key=lambda row: row['position'])
        outer = left if side == 0 else left + width
        inward = 1 if side == 0 else -1
        divider = outer + inward * 124
        inner = outer + inward * 220
        pin_x = (divider + inner) / 2
        ctext(page, (outer + inner) / 2, 60, bank, 8, True)
        ctext(page, (outer + divider) / 2, 77, '端子記名', 8)
        ctext(page, pin_x, 77, 'PLC側ピン', 8)
        page.line(divider, 69, divider, top + len(rows) * pitch, width=0.5)
        if side:
            page.line(inner, 52, inner, bottom)

        symbol = 'module_pin'
        if side:
            symbol = 'terminal_block_pin_right'
            if symbol not in symbols:
                right_pin = Symbol(symbol, '中継端子台右端子', 20, 20, 10, 10)
                right_pin.circle(-8, -4, 8)
                right_pin.terminal('t', 'e', 0, 0)
                symbols[symbol] = right_pin

        y = top
        for (pins, connectable), group in groupby(rows, key=lambda row: (row['pins'], row.get('connectable', True))):
            start = y
            for row in group:
                cy = y + pitch / 2
                name = row['terminal']
                offset = 10 if side == 0 else -18 - text_w(name, 9)
                if pins and connectable:
                    page.place(symbol, outer, cy, label=name,
                               texts=[('label', offset, vcenter(9), 9, True)])
                else:
                    ctext(page, (outer + divider) / 2, cy, name, 9)
                y += pitch
                page.line(outer, y, divider, y, width=0.5)
            # 同じピンに分岐する端子は、実物の接続口を残してピン欄だけを連結する。
            if pins:
                value = '・'.join(pins)
                size = next((s for s in (9, 8, 7) if text_w(value, s) <= 86), 7)
                lines = ['']
                for pin in pins:
                    joined = '・'.join(filter(None, (lines[-1], pin)))
                    if lines[-1] and text_w(joined, size) > 86:
                        lines.append(pin)
                    else:
                        lines[-1] = joined
                for i, line in enumerate(lines):
                    ctext(page, pin_x, (start + y) / 2 + (i - (len(lines)-1)/2) * 12, line, size)
            else:
                page.line(min(divider, inner) + 3, y - 3, max(divider, inner) - 3, start + 3, width=0.5)
            page.line(divider, y, inner, y, width=0.5)

    for i, note in enumerate(notes):
        page.text(30, 768 - (len(notes) - i) * 17, note, 8)
    return [(pg.get('title') or (spec['model'] + ' 中継端子台'), page)]
