"""GOT本体は最大装備を基準とした共通枠で、非搭載部分を省く。"""
import copy

from .communication import connector, connector_label_x, draw_panel


def interface(p, symbols, item, x, top, Symbol, mode='', notes=None, right_edge=None):
    item = copy.deepcopy(item)
    item.update(item.get('modes', {}).get(mode) or {})
    p.text(x + 12, top, item['name'], 8, True)
    if item['kind'] == 'terminal':
        selected = item.get('modes', {}).get(mode)
        if selected:
            item.update(selected)
        blank = len(item.get('unconnected_positions', []))
        for index in range(blank):
            p.text(x + 16, top + 32 + index * 24 - 7, 'NC（配線不可）', 8)
        pins = item.get('port_pins', [])
        for index, signal in enumerate(item.get('ports', [])):
            label = (str(pins[index]) + '  ' if pins else '') + signal
            p.place('module_pin', x, top + 32 + (index + blank) * 24, label=label,
                    texts=[('label', 14, -7, 8, False)])
    else:
        if right_edge is not None:
            from . import connectors
            from .communication import wrap
            from renderers.typography import text_w
            key = connectors.symbol(symbols, Symbol, item['kind'], terminal_side='right')
            p.place(key, right_edge - 10, top + 48)
            lines = wrap(item.get('connector_label', item['kind']),
                         right_edge - x - connectors.width(item['kind']) - 34, 8, text_w)
            for index, line in enumerate(lines):
                p.text(x + 12, top + 41 - (len(lines) - 1) * 6 + index * 12, line, 8)
        else:
            key = connector(symbols, item['kind'], Symbol)
            p.place(key, x, top + 48)
            from .communication import interface_rows, pin_table_layout, draw_pin_table
            rows = interface_rows(item)
            if item['kind'].startswith('dsub9') and rows:
                p.text(x + 8, top + 83, 'D-sub 9pin', 7)
                draw_pin_table(p, x + 112, top + 18, *pin_table_layout(rows, 128, compact=True))
            else:
                p.text(x + connector_label_x(item['kind']), top + 42,
                       item.get('connector_label', item['kind']), 8)


def checkbox(p, x, y, selected, label):
    p.text(x, y, ('■ ' if selected else '□ ') + label, 9)


LANE_X = {'P': 45, 'N': 72}       # 入出力ページと同じ P24/N24 レーンの位置
POWER_LANE = {'＋': 'P', '+': 'P', '−': 'N', '-': 'N'}


def ground_names(ports):
    """接地端子の名前。2つあれば左(上)から LG・FG(SH-081194ENG-AW 5.2 印刷158、SH-082581C 25.2.1 印刷108)。
    1つの機種は FG のみ(LG 端子なし。SH-081194ENG-AW 8.3)"""
    count = ports.count('⏚')
    names = ['LG', 'FG'] if count == 2 else ['FG'] * count
    return iter(names)


def interface_height(item, mode=''):
    if item['kind'] == 'terminal':
        selected = item.get('modes', {}).get(mode) or {}
        ports = selected.get('ports', item.get('ports', []))
        blank = len(selected.get('unconnected_positions', item.get('unconnected_positions', [])))
        return 40 + (len(ports) + blank) * 24
    if item['kind'].startswith('dsub9'):
        from .communication import interface_rows, pin_table_layout
        selected = {**item, **(item.get('modes', {}).get(mode) or {})}
        rows = interface_rows(selected)
        if rows:
            return 38 + sum(height for _, height in pin_table_layout(rows, 128, compact=True)[1])
    return 90 if item['kind'] == 'rj45' else 100


def build_body(pg, symbols, spec, Page, Symbol, heading, lanes=None):
    """lanes: (レーン名 {'P','N'}, レーン上端の y, 中央ぞろえの文字関数)。DC24V の機種は P24/N24 レーンへ配線する"""
    from . import settings
    from .communication import draw_notes
    from drawing import unit_identity_header
    p = Page(symbols)
    model = pg['model'].upper()
    x, right = 275, 275 + 250             # 左の列(電源・シリアル・Ethernet)と右の列(表示器・USB・SD・電池)
    unit_identity_header(p,dict(pg,model=model,kind='gotbody'),x,500)
    p.text(x+12,60,spec['series']+' タッチパネル',9,True)
    p.line(x+10,80,right+240,80,width=0.5)
    notes=[*spec.get('diagram_notes',[]),'※コネクタはケーブル単位。接続先・結線は手動で記入']

    # 左の列: 電源
    power = spec['power']
    ly = 100
    p.text(x + 12, ly, '電源入力  ' + power.get('voltage', power['supply']), 9, True)
    ports = power.get('ports', [])
    grounds = ground_names(ports)
    lane_info = lanes
    lanes = bool(lanes) and 'DC24V' in (power.get('voltage', '') + power['supply']).replace(' ', '') and any(sig in POWER_LANE for sig in ports)
    lane_tops, ground_pins = {}, []
    if lanes:
        LANE, LANE_TOP_Y, ctext = lane_info
        for name, lx in LANE_X.items():
            ctext(p, lx, 44, LANE[name], 8, True)
            lane_tops[name] = p.place('junction', lx, LANE_TOP_Y)
    for index, signal in enumerate(ports):
        y = ly + 40 + index * 24
        name = next(grounds) if signal == '⏚' else signal
        pin = p.place('module_pin', x, y, label=name if signal == '⏚' else signal,
                      texts=[('label', 14, -7, 9, False)])
        if signal == '⏚':
            ground_pins.append(pin)
            # 接地記号はフォントに依存させず線で描く(名前 LG/FG の右)
            p.line(299 + 20, y - 7, 299 + 20, y + 1)
            p.line(292 + 20, y + 1, 306 + 20, y + 1)
            p.line(295 + 20, y + 4, 303 + 20, y + 4)
            p.line(297 + 20, y + 7, 301 + 20, y + 7)
        elif lanes and signal in POWER_LANE:
            lane = POWER_LANE[signal]
            j = p.place('junction', LANE_X[lane], y)
            p.wire(lane_tops[lane], 's', j, 'n')
            lane_tops[lane] = j
            p.wire(j, 'e', pin, 't', num=LANE[lane], show=True)
    if len(ground_pins) == 2:
        # LG と FG は短絡してから接地する(SH-081194ENG-AW 5.2「Short-circuit the LG terminal and the FG terminal」)
        p.wire(ground_pins[0], 't', ground_pins[1], 't')
        notes.append('LG・FG を短絡して接地')
    if not ports:
        p.text(x + 12, ly + 40, '給電: ' + power.get('connection', power['supply']), 8)
    ly += 40 + max(1, len(ports)) * 24 + 10
    if lanes:
        p.extend_lanes([LANE_X['P'], LANE_X['N']])

    serial, ethernet, accessories = [], [], []
    for item in spec['interfaces']:
        if item['kind'] == 'rj45':
            ethernet.append(item)
        elif item['kind'] == 'sd':
            continue
        elif item['kind'].startswith('usb') or item['kind'] == 'hdmi':
            accessories.append(item)
        else:
            serial.append(item)
    mode = pg.get('serial_mode', '')
    if mode and serial:
        p.text(x + 165, ly - 4, mode, 8)
    for item in serial:
        p.line(x + 10, ly, x + 240, ly, width=0.5)
        interface(p, symbols, item, x, ly + 12, Symbol, mode, notes=notes)
        ly += interface_height(item, mode)
    for item in ethernet:
        p.line(x + 10, ly, x + 240, ly, width=0.5)
        interface(p, symbols, item, x, ly + 12, Symbol, notes=notes)
        ly += interface_height(item)

    # 右の列: 表示器・USB/HDMI・SD・電池
    display = spec.get('display', '')
    if isinstance(display, dict):
        display = display.get('screen', '') + '  ' + display.get('resolution', '')
    elif spec.get('resolution'):
        display += '  ' + spec['resolution']
    ry = 100
    p.text(right + 12, ry, display, 9, True)
    ry += 20
    for item in accessories:
        interface(p, symbols, item, right, ry, Symbol, notes=notes, right_edge=right + 250)
        ry += 90
    p.line(right + 10, ry, right + 240, ry, width=0.5)
    p.text(right + 12, ry + 15, 'SD CARD', 9, True)
    if spec.get('sd_card_supported'):
        state = pg.get('sd_card', '要確認')
        checkbox(p, right + 100, ry + 15, state == '有', '有 (' + pg.get('sd_card_model', '') + ')')
        checkbox(p, right + 100, ry + 39, state == '無', '無')
    else:
        p.text(right + 100, ry + 15, '本体スロットなし', 8)
    if spec.get('sd_card_optional'):
        p.text(right + 12, ry + 63, '別売: ' + spec.get('sd_card_option', ''), 8)
    ry += 90
    p.line(right + 10, ry, right + 240, ry, width=0.5)
    p.text(right + 12, ry + 15, 'バッテリ', 9, True)
    if spec.get('battery_supported'):
        state = pg.get('battery', '要確認')
        checkbox(p, right + 100, ry + 15, state == '装着', '有 (' + spec.get('battery_type', '') + ')')
        checkbox(p, right + 100, ry + 39, state == '非装着', '無')
    else:
        checkbox(p, right + 100, ry + 15, True, '装着不可')
    ry += 65

    bottom = max(ly, ry) + 5
    p.rect(x, 52, right + 250, bottom, dash=False, width=1)
    # 左下の記入欄(x95～325)と離した注記領域。
    draw_notes(p,335,440,notes)
    # 機種別の記入欄をP24/N24レーンの右に置く。
    settings.draw(p, settings.fields(model=pg['model'], values=pg), pg, 95, 325)
    return p


def build_options(pg, symbols, definitions, Page, Symbol, heading):
    from drawing import unit_identity_header
    from .settings import UNIT_BOX_W, SETTINGS_BOTTOM
    p = Page(symbols)
    box_bottoms = {}
    for side, key in enumerate(('left_model', 'right_model')):
        model = pg.get(key, '').upper()
        if not model:
            continue
        spec = copy.deepcopy(definitions[model])
        spec['panel_compact'] = True
        notes = list(spec.get('diagram_notes', []))
        modules = spec.get('module_interfaces', {})
        if modules:
            # 通信モジュールを載せる機種: 選んだモジュールのコネクタを描く
            module = pg.get(('left' if side == 0 else 'right') + '_module', '').upper()
            if module in modules:
                spec['interfaces'] = modules[module]
                notes.append(spec.get('module_interfaces_basis', ''))
            else:
                notes.insert(0, '通信モジュール(' + '・'.join(modules) + ')を選ぶとコネクタを表示')
        if not spec['interfaces'] and not modules:
            notes.insert(0, '外部配線端子なし')
        if spec.get('adapter_required', {}).get('GOT3000'):
            notes.append('GOT3000: GT37-IF2000経由')
        elif 'GOT3000' not in spec.get('compatible_series', []):
            notes.append('GOT3000への適用は未対応')
        spec['diagram_notes'] = [note for note in notes if note]
        x = 275 + side * 620
        prefix = 'left' if side == 0 else 'right'
        unit_identity_header(p,{'model':model,'kind':'gotoption','tag':pg.get(prefix+'_tag',''),
                                'unit_no':pg.get(prefix+'_unit_no','')},x,UNIT_BOX_W)
        draw_panel(p, symbols, spec, x, Symbol, pg, prefix)
        box_bottoms[x] = None if model in ('GT01-RS4-M', 'GT10-9PT5S') else 422
        # 機種別の表示指定に従い、オプションの左下へ詰めて配置する。
        from . import settings
        rows = settings.fields(model=model, values=pg, prefix=prefix)
        settings.draw(p, rows, settings.values(pg, prefix), x - 245, x - 15)
    full_bottom = min(SETTINGS_BOTTOM, getattr(p, 'communication_footer_top', 800) - 8)
    for shape in p.shapes:
        if shape.get('type') == 'Rectangle' and float(shape.get('y1')) == 52:
            x = float(shape.get('x1'))
            if x in box_bottoms:
                shape.set('y2', str(box_bottoms[x] or full_bottom))
    return p
