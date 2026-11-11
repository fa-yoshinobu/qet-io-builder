"""中継端子台にケーブル接続するQ/NXの40極I/Oコネクタ展開。"""
from copy import deepcopy


def _connector_rows(pg, spec):
    from unit_catalog import unit_addrs

    if 'sections' in spec:
        section, = spec['sections']
        return section['terminals']

    rows = [dict(pin=pin, signal=address, purpose='')
            for pin, address in zip(spec['pins'], unit_addrs(pg))]
    if spec['io'] == 'in':
        commons = spec['common']
    else:
        rows.extend(dict(pin=pin, signal='V+', purpose='外部電源')
                    for pin in spec['vplus'].split('/'))
        commons = spec['com'].split('/')
    rows.extend(dict(pin=pin, signal='COM', purpose='コモン') for pin in commons)
    rows.extend(dict(pin=pin, signal='NC', purpose='', connectable=False)
                for pin in spec['unused_pins'])
    return rows


def plc_signals(pg, spec):
    return {row['pin']: row['signal'] for row in _connector_rows(pg, spec)}


def build_pages(pg, spec, symbols):
    from drawing import Page, HALF_W, IN_X, OUT_X, IN_TEXTS, OUT_TEXTS, io_table_header
    from .communication import wrap

    page = Page(symbols)
    rows = _connector_rows(pg, spec)
    output = spec.get('io') == 'out' or any(row.get('io') == 'output' for row in rows)
    # FCNのA/B列とMILの奇数/偶数列を、それぞれの端子配列のまま表示する。
    banks = {}
    unused = []
    for row in rows:
        if row.get('connectable', True):
            pin = row['pin']
            bank = int(pin) % 2 if pin.isdecimal() else pin[0]
            banks.setdefault(bank, []).append(row)
        else:
            unused.append(row['pin'])
    if len(banks) != 2:
        raise ValueError(f"{pg['model']}: I/Oコネクタのピン列を特定できません")
    pitch = 32 if max(map(len, banks.values())) > 18 else 36
    base = 'plc_out' if output else 'plc_in'
    key = f'{base}_cable_{pitch}'
    if key not in symbols:
        symbol = deepcopy(symbols[base])
        symbol.name, symbol.height, symbol.hy = key, pitch, pitch // 2
        for _, attrs in symbol.parts:
            for dim in ('y', 'y1', 'y2', 'height'):
                if dim in attrs:
                    attrs[dim] = attrs[dim] * pitch / symbols[base].height
        symbol.circle(-12 if output else 4, -4, 8)
        symbols[key] = symbol

    label = '信号' if 'sections' in spec else 'アドレス'
    for side, bank in enumerate(banks.values()):
        x = (OUT_X if output else IN_X)['plc'] + side * HALF_W
        if output:
            io_table_header(page, pg, x - 234, 230, (130, 185), ('用途', label, 'ピン'))
        else:
            io_table_header(page, pg, x + 4, 250, (45, 100), ('ピン', label, '用途'))
        for index, row in enumerate(bank):
            y = 70 + pitch / 2 + index * pitch
            page.place(key, x, y, label=row['signal'], comment=row['purpose'],
                       infos={'auxiliary1': row['pin']}, texts=OUT_TEXTS if output else IN_TEXTS)

    note = spec['note'] if 'sections' in spec else ''
    if unused:
        note += ' 本体側の空きピン：' + '・'.join(unused) + '。'
    for i, line in enumerate(reversed(wrap(note.strip(), 1180, 8))):
        page.text(30, 748 - i * 16, line, 8)
    return [(pg.get('title') or pg['model'] + ' I/Oコネクタ', page)]
