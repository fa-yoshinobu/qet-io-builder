"""KV固有の端子配列を使い、共通の記号・寸法で配線する。"""
import copy

def draw_half(page, pg, spec, section, side):
    from drawing import HALF_W, IN_X, OUT_X, IN_TEXTS, OUT_TEXTS, ROW_PITCH, LANE, LANE_TOP_Y, ctext, io_table_header, output_lane_labels, FX_IN_X, FX_OUT_X
    from renderers.relay_references import tb_label, line_no

    output = section['directions'][side] == 'output' if 'directions' in section else spec['output']
    positions = dict(OUT_X, P=FX_OUT_X['inner'], N=FX_OUT_X['outer']) if output else dict(IN_X, P=FX_IN_X['outer'], N=FX_IN_X['inner'])
    x = {key: value + side * HALF_W for key, value in positions.items()}
    labels = section.get('labels', [''] * len(section['halves']))
    pin_label = labels[side] + spec['connection']
    key, texts = ('plc_out_kv', OUT_TEXTS) if output else ('plc_in_kv', IN_TEXTS)
    if output:
        io_table_header(page, pg, x['plc'] - 234, 230, (130, 185), ('用途', '信号', pin_label))
        load_lane = 'P' if spec['output_type'] == 'sink' else 'N'
        common_lane = 'N' if load_lane == 'P' else 'P'
        lanes = {load_lane: x['P'], common_lane: x['N']}
    else:
        io_table_header(page, pg, x['plc'] + 4, 250, (45, 100), (pin_label, '信号', '用途'))
        common_lane = spec['input_common']
        load_lane = 'N' if common_lane == 'P' else 'P'
        lanes = {name: x[name] for name in ('P', 'N')}
    cable_layout = pg.get('cable_layout')
    if not cable_layout:
        if output:
            output_lane_labels(page, x['P'], LANE[load_lane], x['N'], LANE[common_lane])
        else:
            for name, lx in lanes.items():
                ctext(page, lx, 44, LANE[name], 8, True)
        page.text(x['tb'] - 18, 46, pg.get('tb_name', 'TB'), 8, True)
        previous = {name: page.place('junction', lx, LANE_TOP_Y) for name, lx in lanes.items()}
    top = 70
    for pin, signal in section['halves'][side]:
        if signal == 'NC':
            continue
        common = signal.startswith('C')
        height = ROW_PITCH
        y = top + height / 2
        top += height
        terminal = page.place(key, x['plc'], y,
                              label=signal, comment='コモン' if common else '',
                              infos={'auxiliary1': pin}, texts=texts)
        if cable_layout:
            continue
        line_no(page, x['num'], y)
        tb = page.place('tb_terminal', x['tb'], y, label=tb_label(pg, pin=pin),
                        texts=[('label', -10, -22, 7, False)])
        lane = common_lane if common else load_lane
        node = page.place('junction', lanes[lane], y)
        page.wire(previous[lane], 's', node, 'n')
        previous[lane] = node
        if output:
            page.wire(terminal, 't', tb, 'w', num=LANE[lane] if common else '', show=common)
            if common:
                page.wire(tb, 'e', node, 'w')
            else:
                load = page.place('load_coil', x['load'], y)
                page.wire(tb, 'e', load, 'w', num=signal, show=True)
                page.wire(load, 'e', node, 'w')
        else:
            page.wire(tb, 'e', terminal, 't', num=LANE[lane] if common else '', show=common)
            if common:
                page.wire(node, 'e', tb, 'w')
            else:
                contact = page.place('contact_a', x['contact'], y)
                page.wire(node, 'e', contact, 'w')
                page.wire(contact, 'e', tb, 'w', num=signal, show=True)
    if not cable_layout:
        page.extend_lanes(lanes.values(), bottom=790)
    if output and section.get('output_group_sizes'):
        group_top = 70
        for count in section['output_group_sizes'][side]:
            group_bottom = group_top + count * ROW_PITCH
            page.rect(x['plc'] - 104, group_top, x['plc'] - 4, group_bottom, dash=False, width=1.8)
            group_top = group_bottom


def build_nano_body(pg, spec, symbols):
    from drawing import Symbol, Page, unit_identity_header, ctext, FX_IN_X, LANE, LANE_TOP_Y
    from .connectors import draw

    body = spec['body']
    key = 'plc_in_kv_nano_body_' + ('connector' if body.get('connector_power') else body['power'])
    if key not in symbols:
        symbol = Symbol(key, 'KV Nano 本体', 350, 680, 20, 5)
        symbol.rect(-20, 0, 350, 680)
        symbol.label(10, 28, 'CPU', 10, True)
        symbol.line(-20, 48, 330, 48, thin=True)
        symbol.label(4, 68, '電源入力（コネクタ）' if body.get('connector_power') else '電源入力', 8, True)
        power = ['AC_L', 'AC_N', 'FG'] if body['power'] == 'A' else ['24V', '0V', 'FG']
        for i, name in enumerate(power):
            y = 95 + i * 32
            symbol.circle(-20, y - 4, 8)
            symbol.terminal(name, 'w', -20, y)
            color = {'24V': '赤', '0V': '黒', 'FG': '緑'}[name] if body.get('connector_power') else ''
            symbol.label(-6, y + 4, name + ('（' + color + '）' if color else ''), 8)
        symbol.label(95, 99, 'AC100～240V' if body['power'] == 'A' else 'DC24V', 8)
        service = body['power'] == 'A'
        if service:
            symbol.line(-20, 190, 330, 190, thin=True)
            symbol.label(4, 210, 'サービス電源出力', 8, True)
        for i, name in enumerate(('24V', '0V') if service else ()):
            y = 240 + i * 32
            symbol.circle(-20, y - 4, 8)
            symbol.terminal('service:' + name, 'w', -20, y)
            symbol.label(-6, y + 4, name, 8)
        symbol.line(-20, 310, 330, 310, thin=True)
        symbol.label(4, 330, 'USB通信', 8, True)
        draw(symbol, body['usb_connector'], -12, 365)
        symbol.terminal('USB', 'w', -12, 365)
        symbol.label(45, 369, 'USB Type-B', 8)
        symbol.line(-20, 410, 330, 410, thin=True)
        symbol.label(4, 430, 'シリアル通信（RS-232C）', 8, True)
        draw(symbol, body['serial_connector'], -12, 470)
        symbol.terminal('SERIAL', 'w', -12, 470)
        symbol.label(45, 474, 'モジュラー 6ピン', 8)
        symbols[key] = symbol
    page = Page(symbols)
    unit_identity_header(page, pg, 280, 350)
    cpu = page.place(key, 300, 52)
    purposes = {'+5V': 'KV-D30給電専用', 'RD': '受信', 'SD': '送信', 'SG': '信号グランド', 'GND': 'グランド'}
    for i, (pin, signal) in enumerate([['No.', '信号']] + body['serial_pins']):
        y = 548 + i * 22
        page.rect(380, y, 610, y + 22, dash=False, width=0.5)
        for cut in (415, 475):
            page.line(cut, y, cut, y + 22, width=0.5)
        values = (pin, signal, '用途' if not i else purposes[signal])
        for value, left, right in zip(values, (380, 415, 475), (415, 475, 610)):
            ctext(page, (left + right) / 2, y + 11, value, 8)
    from .box_layout import PowerRails
    rails = PowerRails(page, [(None, {'lane': name}) for name in ('P', 'N')])
    if body['power'] == 'D':
        for name, terminal in (('P', '24V'), ('N', '0V')):
            rails.connect({'lane': name}, cpu, terminal)
    rails.finish(755)
    note = '+5V出力はKV-D30への給電専用。'
    if body['power'] == 'A':
        note += 'サービス電源出力は外部P24／N24へ接続しない。'
    page.text(30, 772, note, 8)
    page.text(30, 800, '内蔵I/Oは同じユニットNo.・タグ名の入出力配線図を参照。SG・GNDは電源入力0Vと非絶縁。', 8)
    return page


def build_module(pg, spec, symbols):
    from drawing import Page, Symbol, unit_identity_header, ctext, BORDER_COLS, COL_SIZE, FX_IN_X, LANE, LANE_TOP_Y
    from . import connectors, settings
    from .communication import draw_notes, pin_table_layout, draw_pin_table, wrap

    module = spec['module']
    modes = module.get('modes', {})
    mode = pg.get('communication_mode', '') or next(iter(modes), '')
    if mode and mode not in modes:
        raise ValueError('このユニットに対応する通信方式を選択してください')
    interfaces = modes[mode] if modes else module.get('interfaces', [])
    notes = [module.get('note', '')]
    notes += [port['name'] + 'のピン' + '・'.join(port['unused']) + 'は接続しない。'
              for port in interfaces if port.get('unused')]
    page = Page(symbols)
    notes_top = draw_notes(page, 30, BORDER_COLS * COL_SIZE - 40, notes)
    x, width = 275, settings.UNIT_BOX_W
    bottom = min(790, notes_top - 8)
    unit_identity_header(page, pg, x, width)
    ctext(page, x + width / 2, 68, module['function'], 9, True)
    top = 88
    from .box_layout import PowerRails, finish_box
    rails = PowerRails(page, [(None, row) for row in module.get('power', [])])
    if module.get('power'):
        page.text(x + 12, top, '電源入力 DC24V', 8, True)
        for index, power in enumerate(module['power']):
            y = top + 42 + index * 32
            terminal = page.place('module_pin', x, y, label=power['signal'], texts=[('label', 14, -7, 8, False)])
            rails.connect(power, terminal)
        top += 142
        rails.finish(bottom)
    for port in interfaces:
        page.text(x + 12, top, port['name'], 8, True)
        rows = [dict(row, connectable=True) for row in port.get('pinout', [])]
        terminal = port['kind'] == 'terminal'
        if not terminal:
            key = connectors.symbol(symbols, Symbol, port['kind'], port.get('gender', ''))
            page.place(key, x + 3, top + 54)
            label = port.get('connector_label', connectors.CONNECTORS[port['kind']][0])
            if port.get('gender'):
                label += ' ' + ('オス' if port['gender'] == 'male' else 'メス')
            page.text(x + 8 + connectors.width(port['kind']) + 14, top + 46, label, 8)
        if rows:
            table_width = width if terminal else width - 80
            columns, cells = pin_table_layout(rows, table_width)
            table_x, table_y = (x, top + 32) if terminal else (x + 70, top + 94)
            draw_pin_table(page, table_x, table_y, columns, cells)
            if terminal:
                y = table_y + cells[0][1]
                for row, (_, height) in zip(rows, cells[1:]):
                    page.place('module_pin', x, y + height / 2)
                    y += height
            top = table_y + sum(height for _, height in cells) + 36
        else:
            top += 120
    if top > bottom:
        raise ValueError('端子表が1ページに収まりません')
    end = top
    if module.get('description'):
        lines = wrap(module['description'], width - 24, 8)
        for i, line in enumerate(lines):
            page.text(x + 12, 96 + i * 16, line, 8)
        end = max(end, 96 + len(lines) * 16 + 16)
    if module.get('display'):
        page.rect(x + 30, 160, x + width - 30, 220, dash=False, width=0.7)
        ctext(page, x + width / 2, 190, '表示部', 9)
        for i, label in enumerate(('M', '◀ ▶', '▲ ▼', 'Enter')):
            left = x + 30 + i * 64
            page.rect(left, 242, left + 58, 272, dash=False, width=0.7)
            ctext(page, left + 29, 257, label, 8)
        end = max(end, 290)
    finish_box(page, x, x + width, end, module.get('settings', []), pg, limit=bottom)
    return pg['model'] + ' ' + module['function'], page


def build_analog(pg, spec, symbols):
    from drawing import Page, IN_X, IN_TEXTS, ROW_PITCH, io_table_header
    from .communication import draw_notes

    page = Page(symbols)
    x = IN_X['plc']
    io_table_header(page, pg, x + 4, 250, (45, 100), ('端子', '信号', '用途'))
    for index, row in enumerate(spec['analog']['terminals']):
        page.place('plc_in_kv', x, 90 + index * ROW_PITCH,
                   label=row['signal'], comment=row['purpose'],
                   infos={'auxiliary1': row['pin']}, texts=IN_TEXTS)
    draw_notes(page, 30, 950, [spec['note']])
    return [(pg['model'] + ' ' + spec['analog']['function'], page)]


def build_pages(pg, spec, symbols):
    from drawing import Page

    if spec.get('module'):
        return [build_module(pg, spec, symbols)]
    for base in ('plc_in', 'plc_out'):
        key = base + '_kv'
        if key not in symbols:
            symbol = copy.deepcopy(symbols[base])
            symbol.name = key
            symbol.circle(4 if base == 'plc_in' else -12, -4, 8)
            symbols[key] = symbol
    if spec.get('analog'):
        return build_analog(pg, spec, symbols)
    pages = [(pg['model'] + ' 本体', build_nano_body(pg, spec, symbols))] if spec.get('body') and not pg.get('cable_layout') else []
    sections = spec['pages']
    if (pg.get('cable_layout') and spec.get('body') and len(sections) == 2
            and all(len(section['halves']) == 1 for section in sections)
            and [section.get('directions') for section in sections] == [['input'], ['output']]):
        sections = [dict(section='内蔵I/O', directions=['input', 'output'], labels=['入力', '出力'],
                         halves=[section['halves'][0] for section in sections])]
    for section in sections:
        page = Page(symbols)
        for side in range(len(section['halves'])):
            draw_half(page, pg, spec, section, side)
        nc_pins = [pin for half in section['halves'] for pin, signal in half if signal == 'NC']
        note = ('' if pg.get('cable_layout') else 'DC24V配線例。') + spec['note']
        if nc_pins:
            note += ' NCピン' + '・'.join(sorted(nc_pins, key=int)) + 'は接続しない。'
        page.text(30, 750 if pg.get('cable_layout') else 800, note, 8)
        title = ' '.join(filter(None, (pg['model'], section['section'], section.get('bank'), '入出力配線図')))
        pages.append((title, page))
    return pages
