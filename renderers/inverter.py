"""インバータの主回路・制御回路。実端子ごとに接続点を残す。"""


def build_body(pg, spec, symbols):
    from gen_io_page import Page, Symbol, unit_identity_header, text_w, TEXT_MARGIN, PX_PER_PT
    from .communication import draw_notes, wrap
    from . import connectors, settings
    p = Page(symbols)
    terminals = {}
    left, right, middle = 400, 840, 620
    unit_identity_header(p, pg, left, right - left)
    p.rect(left, 52, right, 748, dash=False, width=1)
    p.text(left + 12, 60, spec['function'], 9, True)
    p.text(left + 12, 78, spec['supply'] + ' / ND ' + str(spec['capacity_kw']) + 'kW', 8)
    p.line(middle, 96, middle, 748, width=0.5)
    if 'inverter_pin_right' not in symbols:
        symbol = Symbol('inverter_pin_right', 'インバータ右端子', 20, 20, 10, 10)
        symbol.circle(-8, -4, 8)
        symbol.terminal('t', 'e', 0, 0)
        symbol.dynamic('label', -65, -7, 8)
        symbols[symbol.name] = symbol
    for side in ('left', 'right'):
        edge, inner = (left, middle) if side == 'left' else (right, middle)
        y = 100
        for group in spec['terminal_groups'][side]:
            if y != 100:
                p.line(min(edge, inner) + 10, y, max(edge, inner) - 10, y, width=0.5)
            p.text(min(edge, inner) + 12, y + 3, group['name'], 8, True)
            y += 24
            for signal, meaning in group['terminals']:
                key = 'module_pin' if side == 'left' else 'inverter_pin_right'
                offset = 14 if side == 'left' else -22 - text_w(signal, 8)
                meaning_x = left + 76 if side == 'left' else middle + 12
                meaning_right = middle - 12 if side == 'left' else right + offset - 8
                lines = wrap(meaning, meaning_right - meaning_x, 8, text_w)
                row_height = max(18, len(lines) * 12 + 6)
                cy = y + (row_height - 18) / 2
                ground = signal == 'PE'
                pin = p.place(key, edge, cy, label='' if ground else signal, comment='',
                              texts=[('label', offset, -7, 8, False)])
                terminals.setdefault((side, group['name'], signal), []).append(pin)
                if ground:
                    gx = edge + (23 if side == 'left' else -23)
                    p.line(gx, cy - 9, gx, cy)
                    for width, dy in ((16, 0), (10, 3), (4, 6)):
                        p.line(gx - width / 2, cy + dy, gx + width / 2, cy + dy)
                for index, line in enumerate(lines):
                    p.text(meaning_x, cy - 7 - (len(lines) - 1) * 6 + index * 12, line, 8)
                y += row_height
        if side == 'right':
            for port in spec['ports']:
                p.line(middle + 10, y, right - 10, y, width=0.5)
                key = connectors.symbol(symbols, Symbol, port['kind'], terminal_side='right')
                p.place(key, right - 10, y + 28)
                lines = wrap(port['name'], right - middle - connectors.width(port['kind']) - 34, 8, text_w)
                for index, line in enumerate(lines):
                    p.text(middle + 12, y + 21 - (len(lines) - 1) * 6 + index * 12, line, 8)
                y += 54
            if y > 748:
                raise ValueError('インバータの端子・コネクタが枠内に収まりません: ' + pg['model'])
        elif y > 610:
            raise ValueError('インバータの入力端子が設定欄に重なります: ' + pg['model'])
    jumper_labels = {}
    for jumper in spec.get('factory_jumpers', []):
        side, group = jumper['side'], jumper['group']
        first, second = jumper['terminals']
        a = terminals[(side, group, first)][0]
        b = terminals[(side, group, second)][jumper.get('to_occurrence', 0)]
        p.wire(a, 't', b, 't', '短絡片')
        wire, ys = jumper_labels.setdefault((side, group), (p.conductors[-1], []))
        ys.extend((a[3], b[3]))
    for (side, _), (wire, ys) in jumper_labels.items():
        wire.set('displaytext', '1')
        wire.set('userx', str(left - 24 - text_w('短絡片', 8) - 2 * TEXT_MARGIN if side == 'left' else right + 20))
        label_y = ((min(ys) + max(ys)) / 2 - 8 * PX_PER_PT / 2 - TEXT_MARGIN
                   if side == 'left' else min(ys) - 8 * PX_PER_PT - 2 * TEXT_MARGIN - 2)
        wire.set('usery', str(label_y))
        wire.set('rotation', '0')
    settings.draw(p, settings.fields(model=pg['model'], values=pg), pg,
                  x0=left + 12, x1=middle - 12, bottom=735)
    draw_notes(p, 30, 1180, spec['diagram_notes'])
    return p
