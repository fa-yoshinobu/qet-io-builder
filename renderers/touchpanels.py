"""タッチパネルの電源・通信とUSB・映像・媒体を、共通コネクタで2列に配置する。"""
from . import connectors, settings
from .communication import draw_notes, pin_table_layout, draw_pin_table, wrap
from .unit_diagrams import _notes, _rails, _power_wire, _terminal_pages


def _right(section):
    kind = section.get('connector', {}).get('kind', '')
    name = section['name'].upper()
    return kind.startswith('usb') or kind in ('sd', 'hdmi', 'dvi_d', 'vga', 'audio_jack') or any(
        word in name for word in ('RGB', 'DVI', '音声'))


def _block(section):
    rows = [dict(pin=r.get('pin', ''), signal=r['signal'], description=r.get('purpose', ''))
            for r in section.get('terminals', [])]
    if not section.get('connector'):
        return section, None, 32 + 28 * sum(r['signal'].upper() != 'NC' for r in rows)
    expanded = section.get('expand') or len(rows) > 12
    table = pin_table_layout(rows, 286) if rows and not expanded else None
    return section, table, 88 + (sum(h for _, h in table[1]) if table else 0)


def build_pages(pg, spec, symbols):
    from gen_io_page import Page, Symbol, unit_identity_header, vcenter, wrap2
    from .analog import readonly_symbol
    left, right = [], []
    expanded = []
    for section in spec['sections']:
        if section.get('connector') and (section.get('expand') or len(section.get('terminals', [])) > 12):
            expanded.append(section)
        (right if _right(section) else left).append(_block(section))
    notes = _notes(spec, spec['sections'])
    if expanded:
        notes = [*notes, 'コネクタの端子展開は後続ページを参照。']
    pages = []
    pending = [left, right]
    while any(pending):
        page = Page(symbols)
        footer = draw_notes(page, 30, 1200, notes)
        limit = min(790, footer - 12)
        unit_identity_header(page, pg, 275, 620)
        page.text(287, 60, 'タッチパネル', 9, True)
        page.text(597, 60, spec.get('display', ''), 9, True)
        records = [(s, r) for blocks in pending for s, _, _ in blocks
                   if not s.get('connector') for r in s.get('terminals', [])]
        rails = _rails(page, records) if any(r.get('lane') for _, r in records) else {}
        used = [0, 0]
        ends = [90, 90]
        for side in range(2):
            x = 275 + 310 * side
            top = 90
            for section, table, height in pending[side]:
                if top + height > limit:
                    break
                page.line(x + 10, top, x + 300, top, width=0.5)
                for index, line in enumerate(wrap(section['name'], 286, 8)):
                    page.text(x + 12, top + 6 + index * 12, line, 8, True)
                if not section.get('connector'):
                    rows = [r for r in section.get('terminals', []) if r['signal'].upper() != 'NC']
                    for index, row in enumerate(rows):
                        label = wrap2(row['signal'], 94, 8)
                        purpose = wrap2(row.get('purpose', ''), 104, 7)
                        key = 'module_pin' if row.get('connectable', True) else readonly_symbol(symbols, 'module_pin')
                        pin = page.place(key, x, top + 36 + index * 28, label=label,
                                         comment=purpose, infos={'auxiliary1': row.get('pin', '')},
                                         texts=[('label', 14, vcenter(8, label.count('\n') + 1), 8, False, 116),
                                                ('auxiliary1', 138, -7, 8, False, 32),
                                                ('comment', 178, vcenter(7, purpose.count('\n') + 1), 7, False, 124)])
                        _power_wire(page, rails, row, pin)
                else:
                    connection = section['connector']
                    wired = section not in expanded
                    key = connectors.symbol(symbols, Symbol, connection['kind'], connection.get('gender', ''),
                                            wired=wired, terminal_side='right' if side else 'left')
                    page.place(key, x + 302 if side else x + 8, top + 52)
                    label_x = x + 12 if side else x + 20 + connectors.width(connection['kind'])
                    label_width = 278 - connectors.width(connection['kind'])
                    label = connection.get('label', '')
                    if label == section['name']:
                        label = ''
                    for index, line in enumerate(wrap(label, label_width, 8)):
                        page.text(label_x, top + 43 + index * 12, line, 8)
                    if table:
                        draw_pin_table(page, x + 12, top + 80, *table)
                top += height
                used[side] += 1
            ends[side] = top
        if not any(used):
            raise ValueError(pg['model'] + ': タッチパネルの端子群が1ページに収まりません')
        page.rect(275, 52, 895, max(ends), dash=False, width=1)
        if rails:
            page.extend_lanes([item[0] for item in rails.values()], bottom=limit)
        ethernet = [s for s in spec['sections'] if s.get('connector', {}).get('kind') == 'rj45']
        # 通信設定欄は機器の引出し領域より下、電源レーンの右へ配置する。
        bottom = footer - 8
        last_left = max((y + terminal[3] for key, _, x, y in page.placed if 275 <= x < 585
                         for terminal in page.sym[key].terminals.values() if terminal[1] == 'w'), default=90)
        if ethernet and last_left + 16 <= bottom - 30:
            settings.draw(page, [('IP設定', 'ip')], pg, 95, 260, bottom=bottom)
        pages.append((pg['model'] + ' タッチパネル', page))
        pending = [blocks[count:] for blocks, count in zip(pending, used)]
    pages += _terminal_pages(pg, spec, expanded, symbols) if expanded else []
    return pages
