"""異種コネクタを備えた通信・情報連携ユニットの正面図。"""
from .typography import text_width, wrap, NO_LINE_START, NO_LINE_END


def connector(symbols, kind, Symbol):
    """コネクタの部品キー。絵は renderers/connectors.py の共通部品"""
    from . import connectors
    existing = {'rj45': 'module_rj45', 'optical': 'module_optical',
                'dsub9': 'module_dsub_f', 'dsub9_male': 'module_dsub', 'coax': 'module_coax'}
    if kind in existing and existing[kind] in symbols:
        return existing[kind]
    target, gender = connectors.resolve(kind)
    return connectors.symbol(symbols, Symbol, target, gender, name='comm_' + target + ('_' + gender if gender else ''))


def connector_label_x(kind):
    """コネクタの右に書く名前の x(絵の幅 + 余白)"""
    from . import connectors
    return 5 + connectors.width(kind) + 12


def draw_notes(p, x, width, notes, *, bottom=800):
    """頁全体の注記を左端へ集約し、配線記入の定型案内を最後に置く。"""
    from .notes import drawing_text
    unique = dict.fromkeys([*getattr(p, '_footer_notes', []),
                           *(value for note in notes if (value := drawing_text(note)))])
    p._footer_notes = sorted(unique, key=lambda note: 'QET' in note and '記入' in note)
    p._footer_bottom = min(getattr(p, '_footer_bottom', bottom), bottom)
    previous = set(map(id, getattr(p, '_footer_texts', [])))
    p.texts[:] = [text for text in p.texts if id(text) not in previous]
    lines = [line for note in p._footer_notes for line in wrap(note, 1176, 8)]
    top = p._footer_bottom - max(0, len(lines) - 1) * 16
    p.communication_footer_top = top
    start = len(p.texts)
    for index, line in enumerate(lines):
        p.text(30, top + index * 16, line, 8)
    p._footer_texts = p.texts[start:]
    return top


def interface_rows(interface):
    """信号行と、位置指定された配線不可のNC行を表示順にまとめる。"""
    pins=interface.get('port_pins',[])
    meanings=interface.get('signal_labels',{})
    rows=[{'signal':signal,'pin':str(pins[i]) if i<len(pins) else '',
           'description':meanings.get(signal,''),'connectable':True}
          for i,signal in enumerate(interface.get('ports',[]))]
    if not rows:
        rows=[{'signal':item['signal'],'pin':str(item.get('pin','')),
               'description':item.get('description',item.get('code','')),'connectable':item.get('connectable', item['signal'] != 'NC')}
              for item in interface.get('pinout',[])]
    for item in sorted(interface.get('unconnected_ports',[]),key=lambda item:item.get('position',1000000)):
        row={**item,'signal':item.get('signal','NC'),'pin':str(item.get('pin','')),'connectable':False}
        position=min(max(int(item.get('position',len(rows))),0),len(rows))
        rows.insert(position,row)
    present = {row['pin'] for row in rows}
    for pin in interface.get('unconnected_pins', []):
        if str(pin) not in present:
            rows.append({'pin': str(pin), 'signal': 'NC', 'description': '', 'connectable': False})
    if interface.get('unconnected_pins'):
        rows.sort(key=lambda row: int(row['pin']) if row['pin'].isdigit() else 10000)
    return rows


def pin_table_layout(rows, width, compact=False):
    """定義済みのピン情報だけを、折返しを含む3列の小表にする。"""
    from renderers.typography import text_w
    columns = (48, round((width - 48) * 0.56, 1))
    columns += (width - sum(columns),)
    values = [('ピンNo.', '信号', '用途')]
    values.extend((row['pin'], row['signal'], row.get('description', '')) for row in rows)
    if compact:
        columns = (48, width - 48)
        values = [('ピンNo.', '信号')] + [(row['pin'], row['signal']) for row in rows]
    cells = []
    for value in values:
        lines = [[part for line in str(text).split('\n') for part in wrap(line, col - 8, 8, text_w)] or ['']
                 for text, col in zip(value, columns)]
        height = max(14 if compact else 22, max(len(line) for line in lines) * 8 * 96 / 72 + (3 if compact else 8))
        cells.append((lines, height))
    return columns, cells


def draw_pin_table(p, x, y, columns, cells):
    from renderers.typography import TEXT_MARGIN, text_w
    from drawing import vcenter
    width = sum(columns)
    bottom = y + sum(height for _, height in cells)
    p.rect(x, y, x + width, bottom, dash=False, width=0.7)
    for boundary in [sum(columns[:i]) for i in range(1, len(columns))]:
        p.line(x + boundary, y, x + boundary, bottom, width=0.5)
    for index, (row, height) in enumerate(cells):
        if index:
            p.line(x, y, x + width, y, width=0.5)
        left = x
        for lines, col in zip(row, columns):
            top = y + height / 2 + vcenter(8, len(lines))
            for line_index, line in enumerate(lines):
                if line:
                    p.text(round(left + (col - text_w(line, 8)) / 2 - TEXT_MARGIN, 1),
                           round(top + line_index * 8 * 96 / 72, 1), line, 8, index == 0)
            left += col
        y += height


def draw_panel(p, symbols, spec, x, Symbol, pg, prefix):
    """機器の箱と端子・コネクタを描き、箱の右端を返す(記入欄は呼び出し側で左下に置く)"""
    interfaces = spec['interfaces']
    compact = spec.get('panel_compact', False)
    pitch = 22 if compact else 25
    rows_by_interface=[interface_rows(item) for item in interfaces]
    # 箱の幅は全機種で同じ(settings.UNIT_BOX_W)。
    from .settings import UNIT_BOX_W
    width = UNIT_BOX_W
    tables = [pin_table_layout(rows, width - connector_label_x(item['kind']) - 10, compact=item['kind'].startswith('dsub9') and 'PROFIBUS' not in spec.get('network', ''))
              if item['kind'] != 'terminal' and rows else None
              for item, rows in zip(interfaces, rows_by_interface)]
    heights=[]
    for item,rows,table in zip(interfaces,rows_by_interface,tables):
        if item['kind']=='terminal':
            heights.append(36+len(rows)*pitch)
        elif table:
            heights.append(max(108 if compact else 118, 40 + sum(h for _, h in table[1])))
        else:
            heights.append(max(80 if compact else 100,36+len(rows)*22))
    function_lines = wrap(spec.get('network', ''), width - 24, 9)
    function_height = max(32, 12 + len(function_lines) * 14) if function_lines else 0
    notes_top = draw_notes(p,x,width,[*spec.get('diagram_notes', []),'※接続先・配線方式はQETで記入'])
    bottom = 52 + function_height + sum(heights) + 10
    if bottom > notes_top - 8:
        for index, table in enumerate(tables):
            if table and not interfaces[index]['kind'].startswith('dsub9'):
                columns, cells = table
                cells = [(row, max(20, max(map(len, row)) * 8 * 96 / 72 + 8)) for row, _ in cells]
                tables[index] = columns, cells
                heights[index] = max(108 if compact else 118, 40 + sum(h for _, h in cells))
        bottom = 52 + function_height + sum(heights) + 10
    if bottom > notes_top - 8:
        raise ValueError('通信ユニットのピン表と注記が1ページに収まりません')
    p.rect(x, 52, x + width, bottom, dash=False, width=1)
    for index, line in enumerate(function_lines):
        p.text(x + 12, 60 + index * 14, line, 9, True)
    top = 52 + function_height
    labels = {'rj45': 'RJ-45', 'optical': '光ファイバ', 'dsub9': 'D-sub 9pin',
              'dsub15': 'D-sub 15pin', 'dsub25': 'D-sub 25pin',
              'gpib': 'IEEE 488 24pin', 'usb': 'USB Mini-B', 'sd': 'SD/SDHC'}
    for interface, height, rows, table in zip(interfaces, heights, rows_by_interface, tables):
        if top != 52:
            p.line(x + 10, top, x + width - 10, top, width=0.5)
        if interface['name'] != spec.get('network'):
            p.text(x + 12, top + 8, interface['name'], 8, True)
        kind = interface['kind']
        if kind == 'terminal':
            for index,row in enumerate(rows):
                label=(row['pin']+'  ' if row['pin'] else '')+row['signal']
                y=top+39+index*pitch
                if row['connectable']:
                    p.place('module_pin',x,y,label=label,comment=row.get('description',''),
                            texts=[('label',14,-7,8,False),('comment',120,-7,7,False)])
                else:
                    p.text(x+14,y-7,label,8)
                    if row.get('description'):
                        p.text(x+120,y-7,row['description'],7)
        else:
            p.place(connector(symbols, kind, Symbol), x, top + (49 if compact else 59))
            label = interface.get('connector_label', labels.get(kind, kind))
            if table:
                label_lines = wrap(label, connector_label_x(kind) - 20, 7)
                for index, line in enumerate(label_lines):
                    p.text(x+12,top+(78 if compact else 88)+index*12,line,7)
                draw_pin_table(p, x + connector_label_x(kind), top + 30, *table)
            else:
                p.text(x + connector_label_x(kind), top + (40 if compact else 48), label, 7)
        top += height
    return x + width
