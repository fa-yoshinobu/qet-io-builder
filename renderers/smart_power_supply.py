"""S8AS2の重複穴を省略しない分岐電源部品。"""
from xml.etree import ElementTree as ET

from .standard import stable_id
from .terminal_box import unit_header, align_unit_header


def definition(model, spec):
    from gen_io_page import Symbol

    channels = spec['output']['branches']
    groups = {g['role']: g['terminals'] for g in spec['terminal_groups']}
    if channels not in (6, 8) or len(groups['output']) != channels * 4:
        raise ValueError('S8AS2の分岐端子構成が不正です: ' + model)
    if [len(groups[k]) for k in ('input', 'signal', 'output_common')] != [5, 7, 2]:
        raise ValueError('S8AS2の入力・信号・共通端子構成が不正です: ' + model)
    symbol = Symbol(model, 'OMRON ' + model + ' DC24V分岐電源', 300, 750, 20, 30)
    symbol.rect(0, 0, 260, 700)
    unit_header(symbol, model, 260)
    symbol.label(14, 26, f"DC24V  {channels}分岐 / 合計{spec['output']['current_a']:g}A", 8)
    symbol.line(10, 38, 250, 38, thin=True)
    symbol.label(14, 60, '入力', 8)
    symbol.label(174, 60, '分岐出力', 8)
    labels = {}
    right_labels = []

    def terminal(key, item, x, y, orient):
        right = orient == 'e'
        symbol.circle(252 if right else 0, y-4, 8)
        symbol.terminal(key, orient, x, y)
        label = item['label']
        if label == '⏚':
            symbol.line(25, y-9, 25, y-1)
            symbol.line(18, y-1, 32, y-1)
            symbol.line(21, y+2, 29, y+2)
            symbol.line(23, y+5, 27, y+5)
        elif right:
            right_labels.append((key, y, label))
        else:
            symbol.label(14, y+4, label, 7)
        labels[key] = label

    for i, item in enumerate(groups['input']):
        terminal(item['id'], item, 0, 80+i*24, 'w')
    symbol.label(14, 216, '入出力信号', 8)
    for i, item in enumerate(groups['signal']):
        terminal(item['id'], item, 0, 240+i*24, 'w')
    symbol.label(14, 426, 'コモン出力', 8)
    for i, item in enumerate(groups['output_common']):
        terminal(item['id'], item, 0, 450+i*24, 'w')
    for i, item in enumerate(groups['output']):
        terminal(item['id'], item, 260, 80+i*18, 'e')
        if i % 4 == 3 and i != len(groups['output'])-1:
            symbol.line(150, 89+i*18, 250, 89+i*18, thin=True)
    symbol.label(14, 682, spec['input']['voltage'], 7)
    for key, (_, orientation, x, y) in list(symbol.terminals.items()):
        symbol.terminals[key] = (stable_id(model + '/smart_power/' + key), orientation, x, y)
    root = symbol.to_xml().find('definition')
    align_unit_header(root, 260)
    root.find('uuid').set('uuid', stable_id(model + '/smart_power'))
    for node in root.findall('./description/dynamic_text'):
        node.set('uuid', stable_id(model + '/smart_power/text/' + node.findtext('info_name')))
    for key, y, label in right_labels:
        node = ET.SubElement(root.find('description'), 'dynamic_text',
                             uuid=stable_id(model + '/smart_power/terminal_text/' + key),
                             x='166', y=str(y-8), z='5', text_from='UserText',
                             Halignment='AlignRight', Valignment='AlignTop', rotation='0',
                             text_width='80', keep_visual_rotation='false', frame='false',
                             font='MS Gothic,7,-1,5,50,0,0,0,0,0')
        ET.SubElement(node, 'text').text = label
    for key, node in zip(symbol.terminals, root.findall('./description/terminal')):
        node.set('name', labels[key])
    infos = root.find('elementInformations')
    for name, text in [('manufacturer', spec['manufacturer']), ('manufacturer_reference', model)]:
        ET.SubElement(infos, 'elementInformation', name=name, show='1').text = text
    root.find('informations').text = ('S8AS2 外部端子図。各分岐の＋/−は各2穴を個別に表示。資料: ' + spec['source'] +
                                     '\n' + '\n'.join(spec.get('wiring_notes', [])))
    return root
