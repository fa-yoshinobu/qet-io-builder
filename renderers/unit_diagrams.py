"""メーカー資料の実端子・ポートから単体接続図を作る。"""
from .typography import _clean_split, cell_wrap, fit_cell
import copy
import math


def validate(model, spec):
    from .connectors import resolve
    if spec.get('manufacturer') not in ('keyence', 'omron'):
        raise ValueError(f'{model}: メーカーが不正です')
    if not isinstance(spec.get('series'), list) or not spec['series'] or not all(isinstance(s, str) and s for s in spec['series']):
        raise ValueError(f'{model}: シリーズが不正です')
    if not isinstance(spec.get('function'), str) or not spec['function']:
        raise ValueError(f'{model}: 機能名がありません')
    if not isinstance(spec.get('sections'), list) or not spec['sections']:
        raise ValueError(f'{model}: 端子・ポートがありません')
    for section in spec['sections']:
        if not isinstance(section.get('name'), str) or not isinstance(section.get('terminals', []), list):
            raise ValueError(f'{model}: 端子群が不正です')
        if section.get('connector'):
            resolve(section['connector']['kind'], section['connector'].get('gender', ''))
        pins = set()
        identifier = 'wire' if section.get('cable_cores') else 'pin'
        for row in section.get('terminals', []):
            if not all(isinstance(row.get(key, ''), str) for key in (identifier, 'signal', 'purpose', 'power_group')) or not row.get('signal'):
                raise ValueError(f'{model}: 端子情報が不正です')
            pin = row.get(identifier, '').strip()
            if identifier == 'wire' and not pin:
                raise ValueError(f'{model}: {section["name"]}の芯線識別がありません')
            if pin and pin in pins:
                raise ValueError(f'{model}: {section["name"]}の端子・芯線識別が重複しています: {pin}')
            pins.add(pin)
            if row.get('lane') not in (None, '', 'P', 'N'):
                raise ValueError(f'{model}: 電源極性が不正です')
            if row.get('lane') and row.get('connectable', True) is False:
                raise ValueError(f'{model}: 接続不可端子に給電はできません')


def terminal_records(spec):
    return [(section, row) for section in spec['sections'] for row in section.get('terminals', [])]


def _notes(spec, sections):
    notes = [spec.get('note', '')]
    for section in sections:
        rows = [r for r in section.get('terminals', []) if r['signal'].upper() == 'NC']
        unused = [r['pin'] for r in rows if r.get('pin')]
        if unused:
            notes.append(section['name'] + '：' + '・'.join(unused) + 'は接続しない。')
        elif rows:
            notes.append(section['name'] + '：NC端子は接続しない。')
    return notes


def _rails(page, records, offset=0):
    from .box_layout import PowerRails
    return PowerRails(page, records, offset)


def _power_wire(page, rails, row, terminal):
    rails.connect(row, terminal)


def _terminal_pages(pg, spec, sections, symbols, *, cable_cores=False):
    from drawing import Page, IN_X, ROW_PITCH, io_table_header, vcenter
    from renderers.typography import wrap2
    from .communication import draw_notes
    records = [(section, row) for section in sections for row in section.get('terminals', [])
               if row['signal'].upper() != 'NC']
    if not records:
        return []
    notes = _notes(spec, sections)
    footer_top = draw_notes(Page(symbols), 30, 1200, notes)
    available = footer_top - 8 - 70
    capacity = max(1, min(17, int((available - 22) // ROW_PITCH)))
    # 小さい端子群は分断しない。特に独立COMを対応するIOと同じ列に保持する。
    columns, column, height = [], [], 0
    for section in sections:
        rows = [row for row in section.get('terminals', []) if row['signal'].upper() != 'NC']
        # 長いコネクタも末尾のCOMだけを次ページへ送らず、信号を含め均等に分割する。
        count = math.ceil(len(rows) / capacity) if rows else 0
        per = math.ceil(len(rows) / count) if count else 1
        for start in range(0, len(rows), per):
            part = rows[start:start + per]
            required = 22 + len(part) * ROW_PITCH
            if column and height + required > available:
                columns.append(column)
                column, height = [], 0
            column.append((section, part))
            height += required
    if column:
        columns.append(column)
    pages = []
    for start in range(0, len(columns), 2):
        page = Page(symbols)
        draw_notes(page, 30, 1200, notes)
        for side, column in enumerate(columns[start:start + 2]):
            rows = [(section, row) for section, part in column for row in part]
            x = IN_X['plc'] + side * 620
            io_table_header(page, pg, x + 4, 250, (45, 150), ('芯線' if cable_cores else '端子', '信号', '用途'))
            rails = _rails(page, rows, side * 620)
            top = 70
            for section, part in column:
                page.rect(x + 4, top, x + 254, top + 22, dash=False, width=1)
                page.text(x + 12, top + 3, wrap2(section['name'], 230, 7), 7, True)
                top += 22
                for row in part:
                    pin = row['wire'].replace(' ', '\n') if cable_cores else row.get('pin', '')
                    purpose, purpose_size = fit_cell(row.get('purpose', ''), 94)
                    label, label_size = fit_cell(row['signal'], 96)
                    texts = [('auxiliary1', 10, vcenter(8, pin.count('\n') + 1), 8, False),
                             ('label', 56, vcenter(label_size, label.count('\n') + 1), label_size, True, 98),
                             ('comment', 160, vcenter(purpose_size, purpose.count('\n') + 1), purpose_size, False, 94)]
                    from .analog import readonly_symbol
                    key = 'plc_in_unit' if row.get('connectable', True) else readonly_symbol(symbols, 'plc_in_unit')
                    terminal = page.place(key, x, top + ROW_PITCH / 2,
                                          label=label, comment=purpose,
                                          infos={'auxiliary1': pin}, texts=texts)
                    _power_wire(page, rails, row, terminal)
                    top += ROW_PITCH
            if rails:
                page.extend_lanes([r[0] for r in rails.values()], bottom=min(790, footer_top - 16))
        pages.append((pg['model'] + ' ' + spec['function'], page))
    return pages


def _connector_pages(pg, spec, sections, symbols):
    from drawing import Page, Symbol, unit_identity_header, ctext
    from . import connectors
    from .communication import draw_notes, pin_table_layout, draw_pin_table, wrap
    blocks = []
    for section in sections:
        rows = [dict(pin=r.get('pin', ''), signal=r['signal'], description=r.get('purpose', ''))
                for r in section.get('terminals', [])]
        # 端子展開が長いコネクタは、実接続点のあるIO表を別ページにする。
        if not section.get('connector'):
            blocks.append((section, 'terminal', 36 + len(rows) * 32))
        elif len(rows) > 12 or section.get('expand'):
            blocks.append((section, None, 108))
        else:
            layout = pin_table_layout(rows, 230) if rows else None
            blocks.append((section, layout, 120 + (sum(h for _, h in layout[1]) if layout else 0)))
    pages = []
    pending = list(blocks)
    while pending:
        page = Page(symbols)
        footer = draw_notes(page, 30, 1200, _notes(spec, sections))
        bottom = min(790, footer - 12)
        unit_identity_header(page, pg, 275, 310)
        ctext(page, 430, 69, spec['function'], 9, True)
        top = 94
        used = 0
        records = [(s, r) for s in sections if not s.get('connector') for r in s.get('terminals', [])]
        rails = _rails(page, records)
        for section, layout, height in pending:
            if top + height > bottom:
                break
            for index, line in enumerate(wrap(section['name'], 286, 8)):
                page.text(287, top + index * 14, line, 8, True)
            if layout == 'terminal':
                from .analog import readonly_symbol
                rows = [r for r in section.get('terminals', []) if r['signal'].upper() != 'NC']
                for index, row in enumerate(rows):
                    y = top + 34 + index * 32
                    key = 'module_pin' if row.get('connectable', True) else readonly_symbol(symbols, 'module_pin')
                    from renderers.typography import wrap2
                    from drawing import vcenter
                    label = wrap2(row['signal'], 108, 8)
                    purpose = wrap2(row.get('purpose', ''), 76, 8)
                    terminal = page.place(key, 275, y, label=label, comment=purpose,
                                          infos={'auxiliary1': row.get('pin', '')},
                                          texts=[('label', 14, vcenter(8, label.count('\n') + 1), 8, False, 132),
                                                 ('auxiliary1', 154, -7, 8, False, 42),
                                                 ('comment', 202, vcenter(8, purpose.count('\n') + 1), 8, False, 96)])
                    _power_wire(page, rails, row, terminal)
                top += height
                used += 1
                continue
            connection = section['connector']
            key = connectors.symbol(symbols, Symbol, connection['kind'], connection.get('gender', ''),
                                    wired=not (len(section.get('terminals', [])) > 12 or section.get('expand')))
            page.place(key, 283, top + 48)
            label = connection.get('label', '')
            if label and label != section['name']:
                for index, line in enumerate(wrap(label, 270 - connectors.width(connection['kind']), 8)):
                    page.text(302 + connectors.width(connection['kind']), top + 42 + index * 14, line, 8)
            if layout:
                draw_pin_table(page, 345, top + 88, *layout)
            top += height
            used += 1
        if not used:
            raise ValueError(pg['model'] + ': コネクタ表が1ページに収まりません')
        from .box_layout import finish_box
        finish_box(page, 275, 585, top, limit=bottom)
        if rails:
            page.extend_lanes([r[0] for r in rails.values()], bottom=bottom)
        pages.append((pg['model'] + ' ' + spec['function'] + ' ポート', page))
        pending = pending[used:]
    return pages


def build_pages(pg, spec, symbols):
    validate(pg['model'], spec)
    if 'plc_in_unit' not in symbols:
        symbol = copy.deepcopy(symbols['plc_in'])
        symbol.name = 'plc_in_unit'
        for kind, attributes in symbol.parts:
            if kind == 'line' and attributes.get('x1') == 104:
                attributes.update(x1=154, x2=154)
        symbol.circle(4, -4, 8)
        symbols[symbol.name] = symbol
    if spec['function'] == 'タッチパネル':
        from .touchpanels import build_pages as touchpanel_pages
        pages = touchpanel_pages(pg, spec, symbols)
        return [(title + (f' ({i + 1}/{len(pages)})' if len(pages) > 1 else ''), page)
                for i, (title, page) in enumerate(pages)]
    connectors = [s for s in spec['sections'] if s.get('connector')]
    terminals = [s for s in spec['sections'] if not s.get('connector') or len(s.get('terminals', [])) > 12 or s.get('expand')]
    short_terminals = [s for s in spec['sections'] if not s.get('connector')]
    if connectors and sum(len(s.get('terminals', [])) for s in short_terminals) <= 12:
        terminals = [s for s in terminals if s.get('connector')]
        connectors = short_terminals + connectors
    pages = _terminal_pages(pg, spec, terminals, symbols) if terminals else []
    if connectors:
        pages = _connector_pages(pg, spec, connectors, symbols) + pages
    if not pages:
        raise ValueError(pg['model'] + ': 描画する実端子・コネクタがありません')
    return [(title + (f' ({i + 1}/{len(pages)})' if len(pages) > 1 else ''), page) for i, (title, page) in enumerate(pages)]
