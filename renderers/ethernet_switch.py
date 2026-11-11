"""産業用ハブの共通外枠。LANはケーブル単位の接続点にする。"""
import math
from xml.etree import ElementTree as ET
from .terminal_box import unit_header, align_unit_header


def _lines(text, width):
    lines, line, size = [], '', 0
    for char in text:
        step = 5 if ord(char) < 128 else 10
        if char == '\n' or size + step > width:
            lines.append(line)
            line, size = '', 0
        if char != '\n':
            line += char
            size += step
    return lines + [line]


def definition(model, spec):
    from drawing import Symbol, draw_rj45
    from .standard import stable_id

    ports = spec.get('ports', [])
    if not 1 <= len(ports) <= 8 or any(p.get('type') != 'rj45' for p in ports):
        raise ValueError('ハブはRJ-45の1～8ポートに対応します')
    if len({p['label'] for p in ports}) != len(ports):
        raise ValueError('ハブのポート名が重複しています')
    groups = [('power', spec['power']['terminals'])]
    if spec.get('ground'):
        groups.append(('ground', [spec['ground']]))
    groups.append(('alarm', spec.get('alarm', {}).get('terminals', [])))
    terminals = [(kind, i, item) for kind, items in groups for i, item in enumerate(items)]
    if not 1 <= len(terminals) <= 7:
        raise ValueError('ハブの電源・接地・警報は計1～7端子に対応します')
    if any(not item.get('label') or not item.get('function') for _, _, item in terminals):
        raise ValueError('ハブの端子名・用途を指定してください')
    rating_lines = _lines(spec['display_ratings'], 230)
    voltage_lines = _lines(spec['power']['voltage'], 230)
    if len(rating_lines) > 2 or len(voltage_lines) > 2:
        raise ValueError('ハブの定格・電源表示は各2行以内で指定してください')

    compact = len(ports) <= 5
    power_bottom = max(180, math.ceil((122 + 20*(len(terminals)-1) + 24)/10)*10) if compact else 250
    lan_first = power_bottom + 50
    footer = lan_first + (len(ports)-1)*50 + 30 if compact else 680
    height = footer + 70
    symbol = Symbol(model, model + ' スイッチングハブ', 300, height + 40, 20, 20)
    symbol.rect(0, 0, 260, height)
    unit_header(symbol, model, 260)
    for i, line in enumerate(rating_lines):
        symbol.label(12, 42 + i * 12, line, 7)
    symbol.line(0, 66, 260, 66, thin=True)
    symbol.label(12, 80, '電源・接地・警報', 8)
    for i, line in enumerate(voltage_lines):
        symbol.label(12, 94 + i * 12, line, 7)
    labels = {}
    for row, (kind, index, item) in enumerate(terminals):
        y = 122 + 20 * row
        key = kind + str(index)
        symbol.circle(0, y - 4, 8)
        symbol.terminal(key, 'w', 0, y)
        if item['label'] == '⏚':
            # MS Gothic単独では接地文字が欠けるため、同じ記号を線で描く。
            symbol.line(25, y - 8, 25, y + 1)
            symbol.line(18, y + 1, 32, y + 1)
            symbol.line(20, y + 4, 30, y + 4)
            symbol.line(22, y + 7, 28, y + 7)
        else:
            symbol.label(18, y + 3, item['label'], 8)
        function = item['function']
        if kind == 'ground' and 'ねじ' in item.get('connection_type', ''):
            function += '（筐体ねじ）'
        for i, line in enumerate(_lines(function, 150)):
            symbol.label(94, y - 3 + i * 10, line, 7)
        labels[key] = item['label']
    symbol.line(0, power_bottom, 260, power_bottom, thin=True)
    symbol.label(12, power_bottom + 20, 'Ethernet', 8)
    for index, port in enumerate(ports):
        y = lan_first + index * 50
        draw_rj45(symbol, 14, y)
        key = 'lan' + str(index)
        symbol.terminal(key, 'w', 14, y)
        symbol.label(72, y - 2, 'PORT ' + port['label'] + '  RJ-45', 8)
        symbol.label(72, y + 13, port['speed'], 7)
        labels[key] = 'PORT ' + port['label']
    symbol.line(0, footer, 260, footer, thin=True)
    symbol.label(12, footer + 20, 'アンマネージド' if not spec['managed'] else 'マネージド', 8)
    dip = spec.get('dip_switches', [])
    dip_text = 'DIP: ' + ' / '.join(p['label'] + '=' + (str(p['selected']) if p.get('selected') is not None else '（記入）') for p in dip)
    if not dip and spec.get('alarm', {}).get('display_note'):
        symbol.label(12, footer + 38, spec['alarm']['display_note'], 7)

    for key, (_, orientation, x, y) in list(symbol.terminals.items()):
        symbol.terminals[key] = (stable_id(model + '/switch/' + key + '/' + labels[key]), orientation, x, y)
    xml = symbol.to_xml().find('definition')
    align_unit_header(xml, 260)
    xml.find('uuid').set('uuid', stable_id(model + '/switch'))
    xml.find('informations').text = ('共通外枠による自作ハブ端子図。LANはケーブル単位の接続点。'
                                    '\n電源: ' + spec['power']['voltage'] + '\n資料: ' + spec['source']
                                    + '\n' + '\n'.join(spec.get('notes', []))
                                    + '\n' + spec.get('alarm', {}).get('note', '')
                                    + '\n' + '\n'.join('DIP ' + p['label'] + ': ' + p['function'] for p in dip)
                                    + '\n' + spec.get('verification_note', ''))
    infos = xml.find('elementInformations')
    for name, text in [('manufacturer', spec['manufacturer']), ('manufacturer_reference', model),
                       ('comment', spec['display_ratings'])]:
        ET.SubElement(infos, 'elementInformation', name=name, show='1').text = text
    for terminal, key in zip(xml.findall('./description/terminal'), symbol.terminals):
        terminal.set('name', labels[key])
    for node in xml.findall('./description/dynamic_text'):
        node.set('uuid', stable_id(model + '/switch/' + node.findtext('info_name')))
    if dip:
        node = ET.SubElement(xml.find('description'), 'dynamic_text', uuid=stable_id(model + '/switch/dip'),
                             x='12', y=str(footer + 27), z='5', text_from='UserText',
                             Halignment='AlignLeft', Valignment='AlignTop', rotation='0', text_width='-1',
                             keep_visual_rotation='false', frame='false', font='MS Gothic,7,-1,5,50,0,0,0,0,0')
        ET.SubElement(node, 'text').text = '\n'.join(_lines(dip_text, 230))
    return xml
