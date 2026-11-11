"""電源の機種JSONから、QETに配置できる単体.elmt部品を生成する。"""
import argparse
import json
import sys
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gen_io_page import Symbol, draw_rj45
from renderers.terminal_box import unit_header, align_unit_header


def definition(model, spec):
    if spec.get('component_style') == 'smart_power_supply':
        from renderers.smart_power_supply import definition as smart_definition
        return smart_definition(model, spec)
    counts = {'input': 0, 'output': 0}
    for group in spec['terminal_groups']:
        side = 'input' if group['role'] == 'input' else 'output'
        counts[side] += sum(t.get('connectable') is not False for t in group['terminals'])
    compact = not spec.get('interfaces') and max(counts.values()) <= 5
    height = 150 if compact else 300
    first_y, pitch = (76, 14) if compact else (90, 28)
    symbol = Symbol(model, 'OMRON ' + model + ' DC24V電源', 280, height + 40, 20, 20)
    symbol.rect(0, 0, 240, height)
    unit_header(symbol, model, 240)
    output = spec['output']
    symbol.label(16, 22 if compact else 44, f"DC{output['voltage_v']:g}V  {output['current_a']:g}A", 9)
    if compact:
        symbol.label(16, 37, spec['input']['voltage'], 7)
    symbol.line(10, 43 if compact else 54, 230, 43 if compact else 54, thin=True)
    symbol.label(16, 58 if compact else 71, '入力', 8)
    symbol.label(171, 58 if compact else 71, '出力', 8)
    rows = {'input': 0, 'output': 0}
    terminal_labels = {}
    right_labels = []
    for group in spec['terminal_groups']:
        side = 'input' if group['role'] == 'input' else 'output'
        for terminal in group['terminals']:
            if terminal.get('connectable') is False:
                continue
            index = rows[side]
            y = first_y + index * pitch
            point_x, orient = (0, 'w') if side == 'input' else (240, 'e')
            circle_x = 0 if side == 'input' else 232
            symbol.circle(circle_x, y - 4, 8)
            key = side + '_' + str(index)
            symbol.terminal(key, orient, point_x, y)
            terminal_labels[key] = terminal['label']
            if terminal['label'] == '⏚':
                gx = 26 if side == 'input' else 214
                symbol.line(gx, y - 9, gx, y - 1)
                symbol.line(gx - 7, y - 1, gx + 7, y - 1)
                symbol.line(gx - 4, y + 2, gx + 4, y + 2)
                symbol.line(gx - 2, y + 5, gx + 2, y + 5)
            elif side == 'output':
                right_labels.append((key, y, terminal['label']))
            else:
                symbol.label(14, y + 4, terminal['label'], 8)
            rows[side] += 1
    for port in spec.get('interfaces', []):
        if port['kind'] != 'rj45':
            raise ValueError('未対応の電源コネクタ: ' + port['kind'])
        for index in range(port.get('ports', 1)):
            y = 90 + rows['output'] * 28
            draw_rj45(symbol, 190, y)
            key = 'network_' + str(index)
            symbol.terminal(key, 'e', 230, y)
            terminal_labels[key] = port['name']
            symbol.label(105, y + 4, 'Ethernet', 8)
            rows['output'] += 1
    if max(rows.values()) > 7:
        raise ValueError('電源部品の固定枠に端子が収まりません: ' + model)
    if not compact:
        symbol.label(16, 285, spec['input']['voltage'], 8)
    for key, (_, orient, x, y) in list(symbol.terminals.items()):
        stable_uuid = '{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'qet-io-builder/power/' + model + '/' + key)) + '}'
        symbol.terminals[key] = (stable_uuid, orient, x, y)
    element = symbol.to_xml().find('definition')
    align_unit_header(element, 240)
    element.find('uuid').set('uuid', '{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'qet-io-builder/power/' + model)) + '}')
    for node in element.findall('./description/dynamic_text'):
        node.set('uuid', '{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'qet-io-builder/power/' + model + '/text/' + node.findtext('info_name'))) + '}')
    for key, y, label in right_labels:
        node = ET.SubElement(element.find('description'), 'dynamic_text',
                             uuid='{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'qet-io-builder/power/' + model + '/terminal_text/' + key)) + '}',
                             x='146', y=str(y-9), z='5', text_from='UserText',
                             Halignment='AlignRight', Valignment='AlignTop', rotation='0', text_width='80',
                             keep_visual_rotation='false', frame='false', font='MS Gothic,8,-1,5,50,0,0,0,0,0')
        ET.SubElement(node, 'text').text = label
    element.find('informations').text = 'OMRON DC24V電源 自作回路図部品。資料: ' + spec['source']
    for key, terminal in zip(symbol.terminals, element.findall('./description/terminal')):
        terminal.set('name', terminal_labels[key])
    return element


def export(root=ROOT / 'parts/power_supply/omron'):
    outputs = []
    for path in sorted(root.glob('*/power_supply/*.json')):
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if data['category'] != 'power_supply':
            raise ValueError('電源以外の定義です: ' + str(path))
        target = path.parent.parent / 'elements' / (data['model'] + '.elmt')
        target.parent.mkdir(parents=True, exist_ok=True)
        xml = definition(data['model'], data['definition'])
        ET.indent(xml, space='  ')
        ET.ElementTree(xml).write(target, encoding='utf-8', xml_declaration=True)
        outputs.append(target)
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='定義ルート（従来の対象: parts/power_supply/omron）。各シリーズの elements へ出力')
    args = parser.parse_args(argv)
    print('Exported', len(export(args.root)), 'QET parts')


if __name__ == '__main__':
    main()
