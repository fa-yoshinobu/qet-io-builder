"""リモート機器の通信・電源と、配線可能なコネクタ端子の表示。"""
import copy
import math
import re
import uuid


CONNECTOR_LABELS = {
    'm12_a_5': 'M12 Aコード 5極', 'm12_x_8': 'M12 Xコード 8極',
    'm12_l_5': 'M12 Lコード 5極', '7_8_5': '7/8インチ 5極',
    'econ_4': 'e-CON 4極', 'terminal_3': '電源端子台 3極',
    'terminal_40': '端子台 40極', 'fcn_40': 'FCN 40極',
    'one_touch_5': 'ワンタッチ 5極', 'power_5': '電源コネクタ 5極', 'rj45': 'RJ-45',
}
GENDERS = {'male': 'オス', 'female': 'メス', 'unspecified': ''}

def connector_label(item):
    kind = item.get('connector_type', '')
    return CONNECTOR_LABELS.get(kind, kind) + ' ' + GENDERS.get(item.get('gender', ''), '')


def connector_symbol(symbols, Symbol, kind, gender='', wired=True):
    """リモート機器のコネクタ(原点は絵の中心、端子 cable は左)。絵は renderers/connectors.py の共通部品"""
    from . import connectors
    gender = gender if gender in ('male', 'female') else ''
    return connectors.symbol(symbols, Symbol, kind, gender, name='remote_connector_' + kind + ('_' + gender if gender else ''),
                             center=True, terminal='cable', wired=wired)


def compact_connector(symbols, Symbol, kind, gender=''):
    # コネクタページではピンを端子として並べるので、絵には端子を付けない
    key = connector_symbol(symbols, Symbol, kind, gender, wired=False)
    small = key + '_small'
    if small not in symbols:
        s = copy.deepcopy(symbols[key]); s.name = small
        for tag, attrs in s.parts:
            for field in list(attrs):
                # 座標(x, y, x1…xn, y1…yn)と大きさ・角丸を縮める
                if re.fullmatch(r'[xy]\d*|width|height|diameter|rx|ry', field):
                    attrs[field] = round(float(attrs[field]) * 0.55, 2)
        s.terminals = {k: ('{' + str(uuid.uuid4()) + '}', value[1], value[2] * 0.55, value[3] * 0.55) for k, value in s.terminals.items()}
        s.width = round(s.width * 0.55); s.height = round(s.height * 0.55)
        s.hx = round(s.hx * 0.55); s.hy = round(s.hy * 0.55)
        symbols[small] = s
    return small


def draw_connector(p, symbols, Symbol, item, x, y, wired=True):
    kind = item.get('connector_type', 'terminal_3')
    if kind == 'rj45' and wired:
        p.place('module_rj45', x, y)
    else:
        p.place(connector_symbol(symbols, Symbol, kind, item.get('gender', ''), wired), x + 24, y)


def build_body(pg, symbols, spec, Page, Symbol, heading):
    from drawing import unit_identity_header
    from .communication import draw_notes, text_width, wrap
    from .settings import UNIT_BOX_W, SETTINGS_BOTTOM
    p = Page(symbols)
    extension = spec.get('module_role') == 'extension'
    x=275
    widths = [12 + text_width(i['name'] + '  ' + connector_label(i), 8) for i in spec.get('power_connectors', [])]
    widths += [80 + text_width(sig, 8) for i in spec.get('power_connectors', []) for _, sig in i.get('pins', [])]
    right=x+max([UNIT_BOX_W]+[w+15 for w in widths])
    unit_identity_header(p,dict(pg,kind='remotebody'),x,right-x)
    function='増設ユニット' if extension else spec.get('function', spec.get('network','')+' リモートIO')
    lines=wrap(function,right-x-24,9)
    function_height=max(28,12+len(lines)*14)
    for index,line in enumerate(lines):
        p.text(x+12,60+index*14,line,9,True)
    p.line(x+10,52+function_height,right-10,52+function_height,width=0.5)
    y=52+function_height+20
    notes=[]
    for item in spec.get('power_connectors', []):
        p.text(x + 12, y, item['name'] + '  ' + connector_label(item), 8, True)
        # 電源コネクタはピンを端子として並べるので、絵はピンの右に置く参考図(端子なし)
        draw_connector(p, symbols, Symbol, item, x + 205, y + 35, wired=False)
        y += 28
        blocked = set(item.get('no_connect_pins', []) + item.get('non_connectable_pins', []))
        for pin, signal in item.get('pins', []):
            if str(pin) in blocked:
                p.text(x + 16, y - 7, f'{pin}  {signal}（配線不可）', 8)
            else:
                p.place('module_pin', x, y, label=str(pin), comment=signal,
                        texts=[('label', 14, -7, 8, False), ('comment', 80, -7, 8, False)])
            y += 23
        for note in item.get('notes', []):
            notes.append(item['name']+'：'+note)
        y += 15
    if not spec.get('power_connectors'):
        for pin, signal in spec.get('power_ports', []):
            p.place('module_pin', x, y, label=str(pin), comment=signal,
                    texts=[('label', 14, -7, 8, False), ('comment', 80, -7, 8, False)])
            y += 25
    if not extension:
        for item in spec.get('network_connectors', []):
            if item.get('pins'):
                p.text(x + 12, y, item['name'] + ' CC-Link', 8, True)
                draw_connector(p, symbols, Symbol, item, x + 205, y + 35, wired=False)
                y += 25
                for pin, signal in item['pins']:
                    if str(pin) in item.get('no_connect_pins', []):
                        p.text(x + 16, y - 7, f'{pin}  NC', 8)
                    else:
                        p.place('module_pin', x, y, label=str(pin), comment=signal,
                                texts=[('label',14,-7,8,False), ('comment',80,-7,8,False)])
                    y += 23
                y += 15
                continue
            y += 20
            draw_connector(p, symbols, Symbol, item, x, y)
            p.text(x + 64, y - 10, item['name'], 8, True)
            p.text(x + 64, y + 8, connector_label(item), 8)
            y += 40
    notes += list(spec.get('power_notes', [])) + list(spec.get('wiring_notes', []))
    if spec.get('note'):
        notes.append(spec['note'])
    if spec.get('network_condition'):
        notes.append(spec['network_condition'])
    if extension:
        notes.append('主ユニットの増設コネクタに接続（独立通信ポートなし）')
    p.rect(x, 52, right, max(y + 30, 220), dash=False, width=1)
    draw_notes(p,x,right-x,notes)
    if not extension:
        from . import settings
        settings.draw(p, settings.fields(model=pg['model'], values=pg), pg)
    p.stretch_boxes(bottom=min(SETTINGS_BOTTOM,getattr(p,'communication_footer_top',800)-8))
    return p


def connector_pages(pg, symbols, spec, Page, Symbol, heading):
    blocks = []
    for item in spec.get('io_connectors', []):
        pins = item.get('pins', [])
        for start in range(0, len(pins), 6):
            blocks.append((item, pins[start:start + 6], start))
    pages = []
    for start in range(0, len(blocks), 8):
        p = Page(symbols)
        heading(p, pg.get('title', pg['model']) + ' I/Oコネクタ端子')
        p.text(30, 800, '※NC・アキには配線しない', 8)
        for i, (item, pins, offset) in enumerate(blocks[start:start + 8]):
            side, slot = divmod(i, 4)
            x, y = 275 + side * 620, 82 + slot * 174
            p.rect(x, y, x + 265, y + 156, dash=False, width=1)
            p.place(compact_connector(symbols, Symbol, item.get('connector_type', 'terminal_3'), item.get('gender', '')), x + 26, y + 25)
            p.text(x + 62, y + 6, item['name'] + (f'（続き {offset + 1}～）' if offset else ''), 8, True)
            p.text(x + 62, y + 23, connector_label(item), 7)
            if item.get('notes'):
                # 注記は箱の中の右側へ(左は端子からの配線範囲なので空ける)
                from .communication import wrap
                lines = [part for note in item['notes'] for part in wrap(note, 92, 7)]
                for line, part in enumerate(lines[:9]):
                    p.text(x + 160, y + 40 + line * 12, part, 7)
            blocked = set(item.get('no_connect_pins', []) + item.get('non_connectable_pins', []))
            for j, (pin, signal) in enumerate(pins):
                py = y + 48 + j * 18
                if str(pin) in blocked:
                    if str(pin) in item.get('unconfirmed_pins', []):
                        p.text(x + 16, py - 7, f'{pin}  接続不可', 7)
                    else:
                        p.text(x + 16, py - 7, f'{pin}  {signal}（配線不可）', 7)
                else:
                    p.place('module_pin', x, py, label=str(pin), comment=signal,
                            texts=[('label', 14, -7, 7, False), ('comment', 72, -7, 7, False)])
        pages.append((pg.get('title', pg['model']) + f' コネクタ端子 {len(pages) + 1}', p))
    return pages
