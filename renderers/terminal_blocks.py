"""中継端子台の現物記名と、接続ケーブルを通したPLC側ピンとの対応を描く。"""
from itertools import groupby


def build_pages(pg, spec, symbols):
    from gen_io_page import Page, Symbol, ctext, text_w, unit_identity_header, vcenter

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
    if bottom > 775:
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
        for pins, group in groupby(rows, key=lambda row: row['pins']):
            start = y
            for row in group:
                cy = y + pitch / 2
                name = row['terminal']
                offset = 10 if side == 0 else -18 - text_w(name, 9)
                page.place(symbol, outer, cy, label=name,
                           texts=[('label', offset, vcenter(9), 9, True)])
                y += pitch
                page.line(outer, y, divider, y, width=0.5)
            # 同じピンに分岐する端子は、実物の接続口を残してピン欄だけを連結する。
            ctext(page, pin_x, (start + y) / 2, '・'.join(pins), 9)
            page.line(divider, y, inner, y, width=0.5)

    return [(pg.get('title') or (spec['model'] + ' 中継端子台'), page)]
