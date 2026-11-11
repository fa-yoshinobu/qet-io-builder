"""MXコントローラ。端子・コネクタは既存の共通部品を使う。"""


def mxr_symbol(key, height):
    from drawing import Symbol, draw_rj45, rotate90
    from .connectors import usb_c
    symbol = Symbol(key, 'MX-R CPU', 80, height, 10, 5)
    # TSN・モーション部と一体なので、内部境界は構成ページ側で描く。
    symbol.line(-10, 0, 70, 0)
    symbol.line(-10, 0, -10, height)
    symbol.line(-10, height, 70, height)
    usb_c(symbol, 10, height - 112)
    symbol.label(10, height - 134, 'USB Type-C', 7)
    first = len(symbol.parts)
    draw_rj45(symbol, 10, height - 45)
    rotate90(symbol, first, 30, height - 45)
    symbol.label(0, height - 72, 'P3 Ethernet', 7)
    symbol.terminal('p3', 's', 30, height - 25)
    symbol.dynamic('label', -6, 20, 9, True)
    return symbol


def expansion_specs():
    from unit_catalog import read_unit_definitions
    definitions = read_unit_definitions()
    return {model: dict(spec, category=category) for category in ('mx_io', 'fx5_analog', 'fx5_comm')
            for model, spec in definitions[category].items()}


def expansion_items(pg):
    from unit_catalog import MX_CPU
    definitions = expansion_specs()
    allowed = MX_CPU.get(str(pg.get('model', '')).upper(), {}).get('compatible_modules', [])
    modules, tags = pg.get('modules', []), pg.get('module_tags', [])
    if not isinstance(modules, list) or not isinstance(tags, list):
        raise ValueError('MX-Fのmodulesとmodule_tagsは配列で指定してください')
    result = []
    address = {'X': 16, 'Y': 16}
    for index, model in enumerate(modules):
        if not isinstance(model, str):
            raise ValueError('MX-Fの増設形名は文字列で指定してください')
        if not model:
            continue
        model = model.upper()
        if model not in allowed or model not in definitions:
            raise ValueError('このMX-F構成では選択できない機器です: ' + model)
        spec = definitions[model]
        adapter = model.endswith('-ADP') or spec.get('form') == 'adapter'
        label = spec.get('network', '') or ('アナログ ' + str(len(spec['channels'])) + 'CH' if spec.get('channels') else '')
        item = dict(model=model, slot=index, tag=tags[index] if index < len(tags) else '',
                    side='left' if adapter else 'right', spec=spec, summary=label, addr='', points=0)
        ranges = []
        for key, prefix in (('inputs', 'X'), ('outputs', 'Y')):
            count = spec.get(key, 0)
            if type(count) != int:
                continue
            if count:
                item['x_start' if prefix == 'X' else 'y_start'] = f"{address[prefix]:X}"
                ranges.append(f"{prefix}{address[prefix]:02X}～{prefix}{address[prefix] + count - 1:02X}")
                address[prefix] += (count + 15) // 16 * 16
                item['points'] += count
        item['addr'] = ' / '.join(ranges)
        if spec['category'] == 'mx_io':
            item['summary'] = f"入力{spec['inputs']}点 / 出力{spec['outputs']}点 " + spec.get('output_type', '')
        result.append(item)
    left = [item for item in result if item['side'] == 'left']
    if len(left) > 6 or sum(i['spec']['category'] == 'fx5_analog' for i in left) > 4 or sum(i['spec']['category'] == 'fx5_comm' for i in left) > 2:
        raise ValueError('拡張アダプタはアナログ4台・通信2台、合計6台までです')
    if sum(item['side'] == 'right' for item in result) > 12:
        raise ValueError('現在のMX-F構成では右側増設は12台までです')
    return result


def build_body(pg, spec, symbols):
    from drawing import Page, Symbol, unit_identity_header
    from .connectors import symbol as connector
    from .hmi import checkbox
    from . import settings
    p = Page(symbols)
    x, right = 275, 585
    unit_identity_header(p, pg, x, right - x)
    p.text(x + 12, 62, f"MX-F {spec['max_axes']}軸 / {spec['program_memory_mb']}MB", 9, True)
    p.text(x + 12, 84, '入力16点 DC24V シンク/ソース', 8)
    p.text(x + 12, 102, '出力16点 ' + spec['output_type'] + ' ' + spec['output_voltage'], 8)
    p.line(x + 10, 126, right - 10, 126, width=0.5)
    p.text(x + 12, 134, '電源入力 DC24V', 8, True)
    for index, signal in enumerate(spec['power_ports']):
        y = 166 + index * 25
        p.place('module_pin', x, y, label='' if signal == '⏚' else signal, comment='',
                texts=[('label', 14, -7, 8, False)])
        if signal == '⏚':
            p.line(x + 24, y - 10, x + 24, y)
            for width, dy in ((16, 0), (10, 3), (4, 6)):
                p.line(x + 24 - width / 2, y + dy, x + 24 + width / 2, y + dy)
    y = 248
    for port in spec['ports']:
        p.line(x + 10, y, right - 10, y, width=0.5)
        p.text(x + 12, y + 12, port['name'], 8, True)
        p.place('module_rj45', x, y + 57)
        p.text(x + 68, y + 50, 'RJ-45', 8)
        y += 90
    p.line(x + 10, y, right - 10, y, width=0.5)
    p.text(x + 12, y + 12, 'USB2.0 Type-C', 8, True)
    p.place(connector(symbols, Symbol, 'usb_c', 'female'), x + 14, y + 52)
    y += 80
    p.line(x + 10, y, right - 10, y, width=0.5)
    p.text(x + 12, y + 20, 'バッテリ', 8)
    checkbox(p, x + 100, y + 20, pg.get('battery') == '装着', '有 (FX3U-32BL)')
    checkbox(p, x + 100, y + 44, pg.get('battery') == '非装着', '無')
    p.text(x + 12, y + 78, 'SD CARD', 8)
    checkbox(p, x + 100, y + 78, pg.get('sd_card') == '有', '有 (' + pg.get('sd_card_model', '') + ')')
    checkbox(p, x + 100, y + 102, pg.get('sd_card') == '無', '無')
    p.line(x + 10, y + 133, right - 10, y + 133, width=0.5)
    p.text(x + 12, y + 147, '内蔵I/O X00～X0F / Y00～Y0F', 8)
    p.text(x + 12, y + 169, 'ネットワーク 0400H / モーション 0420H', 8)
    items = expansion_items(pg)
    obstacles_bottom = 52
    for side, bx, width, title in [('left', 30, 230, '左側 拡張アダプタ'), ('right', 680, 410, '右側 増設ユニット')]:
        selected = [item for item in items if item['side'] == side]
        if not selected:
            continue
        p.text(bx, 490 if side == 'left' else 62, title, 8, True)
        for index, item in enumerate(selected):
            # 左の電源・LAN・USBから図枠までの引出し範囲を空ける。
            top = 516 + index * 44 if side == 'left' else 92 + index * 44
            unit_identity_header(p, dict(kind='mxio', model=item['model'], tag=item['tag'], unit_no=str(item['slot'] + 1)), bx, width, top, top + 18)
            p.rect(bx, top + 18, bx + width, top + 39, dash=False, width=0.5)
            p.text(bx + 10, top + 24, item['summary'], 8)
            if side == 'right':
                obstacles_bottom = max(obstacles_bottom, top + 39)
            if item['addr']:
                p.text(bx + 210, top + 24, item['addr'], 8)
    from .box_layout import finish_box
    finish_box(p, x, right, y + 192, settings.fields(model=pg['model'], values=pg), pg,
               settings_x=680, settings_width=410, obstacles_bottom=obstacles_bottom)
    from .communication import draw_notes
    draw_notes(p, 30, 1200, ['出力定格 ' + spec['output_current']])
    return p
