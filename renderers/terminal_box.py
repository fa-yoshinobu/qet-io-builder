"""多分岐電子機器の接続可能な箱型部品。"""
from xml.etree import ElementTree as ET
import math


def unit_header(symbol, model, width):
    """接続点を動かさず、箱の上へ編集可能な管理情報の3欄を足す。"""
    from renderers.typography import text_w, PX_PER_PT
    from drawing import vcenter
    symbol.height += 18
    symbol.hy += 18
    symbol.rect(0, -18, width, 18)
    first, second = round(width * .33), round(width * .57)
    symbol.line(first, -18, first, 0, thin=True)
    symbol.line(second, -18, second, 0, thin=True)
    symbol.label(6, -9+7*PX_PER_PT/2, 'ユニットNo.', 7)
    number_x = 6 + text_w('ユニットNo.', 7)
    symbol.dynamic('auxiliary1', number_x, -9+vcenter(7), 7)
    symbol.dynamic('label', first, -9+vcenter(7), 7, True)
    # Qtは半角文字送りを整数pixelへ丸めるため、連続値のem幅では長い形名が枠を越える。
    def model_width(size):
        return len(model) * math.ceil(size * PX_PER_PT / 2)
    size = next((s for s in (8,7,6) if model_width(s) <= width-second-8),6)
    symbol.label(second+(width-second-model_width(size))/2, -9+size*PX_PER_PT/2, model, size, True)


def align_unit_header(xml, width):
    first, second = round(width * .33), round(width * .57)
    for node in xml.findall('./description/dynamic_text'):
        info = node.findtext('info_name')
        if info in ('label','auxiliary1'):
            node.set('Halignment','AlignHCenter')
            node.set('text_width',str(second-first if info=='label' else first-float(node.get('x'))))


def definition(model, spec):
    from drawing import Symbol
    from renderers.typography import text_w
    from .standard import stable_id
    symbol = Symbol(model, model + ' 電子式保護器', 300, 450, 20, 20)
    symbol.rect(0, 0, 260, 410)
    unit_header(symbol, model, 260)
    symbol.label(16, 46, spec['input']['voltage'] + '  ' + spec['display_ratings'], 8)
    symbol.line(10, 58, 250, 58, thin=True)
    symbol.label(16, 76, '電源・制御入力', 8)
    symbol.label(150, 76, '分岐出力・警報', 8)
    rows = {'input': 0, 'output': 0}
    labels = {}
    for group in spec['terminal_groups']:
        side = 'input' if group['role'] == 'input' else 'output'
        for item in group['terminals']:
            index = rows[side]
            y = 100 + 26 * index
            tx, circle_x, orient = (0, 0, 'w') if side == 'input' else (260, 252, 'e')
            symbol.circle(circle_x, y - 4, 8)
            key = side + str(index)
            symbol.terminal(key, orient, tx, y)
            symbol.label(14 if side == 'input' else 246 - text_w(item['label'], 8), y + 4, item['label'], 8)
            labels[key] = item['label']
            rows[side] += 1
    if max(rows.values()) > 10:
        raise ValueError('箱型部品の端子数が上限を超えています')
    for index, note in enumerate(spec.get('diagram_notes', [])):
        symbol.label(16, 376 + index * 15, note, 8)
    for key, (_, orientation, x, y) in list(symbol.terminals.items()):
        symbol.terminals[key] = (stable_id(model + '/box/' + key), orientation, x, y)
    xml = symbol.to_xml().find('definition')
    align_unit_header(xml, 260)
    xml.find('uuid').set('uuid', stable_id(model + '/box'))
    for node in xml.findall('./description/dynamic_text'):
        node.set('uuid', stable_id(model + '/box/text/' + node.findtext('info_name')))
    xml.find('informations').text = '多分岐電子機器の自作端子図。資料: ' + spec['source'] + '\n' + '\n'.join(spec.get('wiring_notes', []))
    infos = xml.find('elementInformations')
    for name, text in [('manufacturer', spec['manufacturer']), ('manufacturer_reference', model)]:
        ET.SubElement(infos, 'elementInformation', name=name, show='1').text = text
    for key, terminal in zip(symbol.terminals, xml.findall('./description/terminal')):
        terminal.set('name', labels[key])
    return xml
