"""パルス・MX-Fの実端子を、既存IOと同じ連続した表で描く。"""
import math
import copy


def terminal_rows(pg, spec, annotations=None):
    rows = copy.deepcopy(spec['signal_terminals'])
    if spec.get('fixed_io_start') and any(int(pg.get(key, '0') or '0', 16) for key in ('x_start', 'y_start')):
        raise ValueError('MX-F本体の内蔵I/O先頭アドレスは0000H固定です')
    seen = set()
    for annotation in annotations or []:
        try:
            index = int(annotation.get('No.', '')) - 1
        except ValueError:
            raise ValueError('端子CSVのNo.は1からの整数で指定してください') from None
        if index in seen or not 0 <= index < len(rows):
            raise ValueError('端子CSVのNo.が重複しているか範囲外です')
        seen.add(index)
        rows[index]['description'] = annotation.get('用途', '')
    for row in rows:
        row['terminal'] = row['signal']
        if row.get('address_prefix'):
            prefix = row['address_prefix']
            offset = int(pg.get('x_start' if prefix == 'X' else 'y_start', '0') or '0', 16)
            if offset < 0:
                raise ValueError('開始アドレスは0以上の16進数で指定してください')
            row['signal'] = f"{prefix}{offset + row['address']:02X}"
    return rows


def build_pages(pg, spec, symbols, annotations=None):
    from gen_io_page import Page, io_table_header, IN_TEXTS, comment_text, wrap2
    from .analog import readonly_symbol
    rows = terminal_rows(pg, spec, annotations)
    if pg['kind'] == 'mxio' and 'plc_in_mx' not in symbols:
        symbol = copy.deepcopy(symbols['plc_in'])
        symbol.name, symbol.height, symbol.hy = 'plc_in_mx', 38, 19
        for tag, attrs in symbol.parts:
            for key in ('y', 'y1', 'y2', 'height'):
                if key in attrs:
                    attrs[key] = float(attrs[key]) * 38 / 40
        symbols[symbol.name] = symbol
    pages = []
    for start in range(0, len(rows), 36):
        part = rows[start:start + 36]
        half = math.ceil(len(part) / 2)
        p = Page(symbols)
        for side in range(2 if len(part) > 1 else 1):
            x = 275 + side * 620
            io_table_header(p, pg, x + 4, 250, (45, 100),
                            ('端子記号' if pg['kind'] == 'mxio' else '端子', 'アドレス' if pg['kind'] == 'mxio' else '信号', '用途'))
            if pg['kind'] == 'mxio':
                section = part[side * half:(side + 1) * half]
                output = any(r.get('address_prefix') == 'Y' for r in section)
                label = (f"出力{spec['outputs']}点 " + spec['output_type'] + ' ' + spec['output_voltage']
                         if output else f"入力{spec['inputs']}点 DC24V シンク/ソース")
                p.text(30 + side * 620, 782, label, 8)
        for index, row in enumerate(part):
            side, position = divmod(index, half)
            purpose = wrap2(row.get('description', ''), 140, 8)
            base = 'plc_in_mx' if pg['kind'] == 'mxio' else 'plc_in'
            key = base if row.get('connectable', True) else readonly_symbol(symbols, base)
            texts = [('label', 56, 0, 8, True) if t[0] == 'label' else t
                     for t in IN_TEXTS if t[0] != 'comment']
            mxf = pg['kind'] == 'mxio'
            p.place(key, 275 + side * 620, (89 + position * 38) if mxf else (90 + position * 40),
                    label=row['signal'] if not mxf or row.get('address_prefix') else '', comment=purpose,
                    infos={'auxiliary1': row['terminal'] if mxf else str(row.get('pin', ''))},
                    texts=texts + [comment_text(purpose, 110, 140, 8, 38 if mxf else 40)])
        if spec.get('diagram_note'):
            note = spec['diagram_note']
            if pg['kind'] == 'mxio':
                note += ' ' + spec['terminal_type']
                if spec.get('output_current'):
                    note += ' / 出力定格 ' + spec['output_current']
            p.text(30, 800, note, 7 if pg['kind'] == 'mxio' else 8)
        title = pg.get('title') or pg['model'] + (' 入出力' if pg['kind'] == 'mxio' else ' パルス端子')
        if len(rows) > 36:
            title += f' ({start // 36 + 1}/{math.ceil(len(rows) / 36)})'
        pages.append((title, p))
    return pages
