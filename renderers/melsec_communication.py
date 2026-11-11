"""MELSECの通信ユニット接続図。"""

from unit_catalog import (
    FX5_COMM, IQR_COMM, Q_COMM
)
from drawing import (
    FX_IN_TEXTS, HALF_W, Page, Symbol, UNIT_BOX_BOTTOM, UNIT_BOX_W,
    unit_identity_header, vcenter
)


def comm_settings(p, pg, spec, x, prefix):
    """通信ユニットの機種別記入欄。非表示項目の値は保持する。"""
    from renderers import settings
    model = pg.get(prefix + "_model", "")
    from .box_layout import finish_box
    frame = next(shape for shape in reversed(p.shapes) if shape.get('type') == 'Rectangle'
                 and float(shape.get('x1')) == x and float(shape.get('y1')) == 52)
    finish_box(p, x, x + UNIT_BOX_W, float(frame.get('y2')),
               settings.fields(model=model, values=pg, prefix=prefix), settings.values(pg, prefix),
               limit=min(790, getattr(p, 'communication_footer_top', 800) - 8))

def build_q_comm_page(pg, symbols):
    from renderers.communication import draw_notes, interface_rows
    p = Page(symbols)
    definitions = {'iqrcomm': IQR_COMM, 'qcomm': Q_COMM, 'fxcomm': FX5_COMM}[pg['kind']]
    for side, field in enumerate(("left_model", "right_model")):
        model = pg.get(field, "").strip().upper()
        if not model:
            continue
        spec = definitions[model]
        x = 275 + side * HALF_W
        prefix='left' if side==0 else 'right'
        identity={'kind':pg['kind'],'model':model,'tag':pg.get(prefix+'_tag',''),
                  'slot':pg.get(prefix+'_slot',''),'unit_no':pg.get(prefix+'_unit_no','')}
        if spec.get('panel_interfaces'):
            from renderers.communication import draw_panel
            right=draw_panel(p, symbols, spec, x, Symbol, pg, prefix)
            unit_identity_header(p,identity,x,right-x)
            comm_settings(p, pg, spec, x, 'left' if side == 0 else 'right')
            continue
        unit_identity_header(p,identity,x,UNIT_BOX_W)
        if pg['kind'] in ('qcomm', 'iqrcomm') and spec.get('interfaces'):
            p.rect(x, 52, x + UNIT_BOX_W, 84 + len(spec['interfaces']) * 225, dash=False, width=1)
            p.text(x+12,60,spec['network'],8,True)
            for k in range(1, len(spec['interfaces'])):
                p.line(x, 84 + k * 225, x + UNIT_BOX_W, 84 + k * 225, width=0.5)
            signals = {'SDA':'TXD+', 'SDB':'TXD-', 'RDA':'RXD+', 'RDB':'RXD-', 'SG':'GND', 'SLD':'シールド', 'FG':'接地'}
            for channel, interface in enumerate(spec['interfaces']):
                top = 94 + channel * 225
                p.text(x + 12, top, interface['name'], 8, True)
                if interface['kind'] == 'dsub9':
                    y = top + 90
                    plug = p.place('module_dsub_f', x, y)
                    p.text(x + 15, y + 40, 'D-sub 9pin メス', 8)
                else:
                    for i, port in enumerate(interface['ports']):
                        y = top + 34 + i * 24
                        plc = p.place('module_pin', x, y, label=port, comment=signals.get(port, ''),
                                      texts=[('label',14,-7,8,False), ('comment',72,-7,8,False)])
        elif pg['kind'] in ('qcomm', 'iqrcomm') and spec.get('connector_type'):
            kind = spec['connector_type']
            if kind == 'terminal':
                bottom = 117 + len(interface_rows(spec)) * 36 + (20 if spec.get('unconnected_pins') else 0)
            else:
                bottom = 152 + len(spec['ports']) * 115 - 40
                if spec.get('power_ports'):
                    bottom = 417 + len(spec['power_ports']) * 36
            p.rect(x, 52, x + UNIT_BOX_W, bottom, dash=False, width=1)
            p.text(x + 12, 62, spec['network'], 8, True)
            if kind == 'terminal':
                for i, row in enumerate(interface_rows(spec)):
                    y = 117 + i * 36
                    label=(row['pin']+'  ' if row['pin'] else '')+row['signal']
                    if row['connectable']:
                        p.place('module_pin',x,y,label=label,texts=[('label',14,-7,8,False)])
                    else:
                        p.text(x+14,y-7,label+'（接続しない）',8)
            else:
                for i, port in enumerate(spec['ports']):
                    y = 152 + i * 115
                    plug = p.place('module_' + kind, x, y)
                    label = spec.get('connector_label', {'rj45': 'RJ-45', 'coax': '同軸 F形', 'optical': '光ファイバ'}[kind])
                    p.text(x + 58, y - 15, port, 8, True)
                    p.text(x + 58, y + 3, label, 8)
                for i, port in enumerate(spec.get('power_ports', [])):
                    y = 417 + i * 36
                    plc = p.place('module_pin', x, y, label=port, texts=[('label',14,-7,8,False)])
                if spec.get('power_ports'):
                    p.text(x + 12, 377, '外部電源', 8, True)
        elif pg['kind'] == 'fxcomm':
            serial = not (model == 'FX5-232ADP' or spec.get('connection', '').startswith('MINI-DIN'))
            p.rect(x, 52, x + UNIT_BOX_W, 102 + len(spec['ports']) * 50 - 10 if serial else 242, dash=False, width=1)
            p.text(x + 12, 60, spec['network'], 8, True)
            if model == 'FX5-232ADP' or spec.get('connection', '').startswith('MINI-DIN'):
                dsub = model == 'FX5-232ADP'
                plug = p.place('module_dsub' if dsub else 'module_minidin', x, 172)
                p.text(x + 15, 212, 'D-sub 9pin オス' if dsub else 'MINI-DIN 8pin メス', 8)
            else:
                signals = {'RDA':'RXD+', 'RDB':'RXD-', 'SDA':'TXD+', 'SDB':'TXD-', 'SG':'GND'}
                for i, port in enumerate(spec['ports']):
                    y = 102 + i * 50
                    plc = p.place('module_pin', x, y, label=port, comment=signals.get(port, ''),
                                  texts=[('label',14,-7,8,False), ('comment',72,-7,8,False)])
        else:
          p.rect(x,52,x+UNIT_BOX_W,122+len(spec['ports'])*60,dash=False,width=1)
          p.text(x+12,60,spec['network'],8,True)
          for i, port in enumerate(spec["ports"]):
            y = 102 + i * 60
            is_terminal = spec['network'] == 'CC-Link' or spec.get('terminal_labels', False)
            label = port if is_terminal else f"PORT{i + 1}"
            comment = "" if is_terminal else port
            plc = p.place("fx_in", x, y, label=label, comment=comment,
                          texts=FX_IN_TEXTS + [("comment", 64, vcenter(8), 8, False)])
        if spec.get('unconnected_pins') and not spec.get('unconnected_ports'):
            for i,pin in enumerate(spec['unconnected_pins']):
                p.text(x+14,bottom-35+i*18,str(pin)+'  NC（接続しない）',8)
        notes=['※接続先・配線方式はQETで記入']+list(spec.get('diagram_notes',[]))
        if spec.get('shield_ground_connected') or any(i.get('shield_ground_connected') for i in spec.get('interfaces',[])):
            notes.append('SLD・FG 内部接続')
        draw_notes(p,x,UNIT_BOX_W,notes)
        comm_settings(p, pg, spec, x, "left" if side == 0 else "right")
    return p
