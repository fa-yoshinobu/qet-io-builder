"""保護器・コンセント・補正タップ付きトランスの外部端子図。"""
import copy
from xml.etree import ElementTree as ET

from .standard import collection_root, stable_id
from .terminal_box import unit_header, align_unit_header


def definition(model, spec, elements=None):
    from gen_io_page import Symbol, text_w

    primary, secondary = spec['external_terminals']['primary'], spec['external_terminals']['secondary']
    if not 3 <= len(primary) <= 5 or not 0 <= len(secondary) <= 5:
        raise ValueError('トランスの端子数が対応範囲外です')
    sym = Symbol(model, model + ' 単相複巻トランス', 340, 330, 10, 30)
    sym.rect(0, 0, 320, 290)
    unit_header(sym, model, 320)
    sym.label(16, 24, '単相複巻  ' + str(spec['ratings']['capacity_va']) + 'VA', 8)
    sym.line(10, 36, 310, 36, thin=True)
    sym.label(16, 56, '一次', 8)
    sym.label(270, 56, '二次', 8)
    pin_labels = {}
    for side, labels in [('primary', primary), ('secondary', secondary)]:
        for i, label in enumerate(labels):
            y = 80 + i * 30
            key = side + str(i)
            right = side == 'secondary'
            sym.circle(312 if right else 0, y - 4, 8)
            sym.terminal(key, 'e' if right else 'w', 320 if right else 0, y)
            if label == '⏚':
                gx = 292 if right else 28
                sym.line(gx, y-9, gx, y-1)
                sym.line(gx-7, y-1, gx+7, y-1)
                sym.line(gx-4, y+2, gx+4, y+2)
                sym.line(gx-2, y+5, gx+2, y+5)
            else:
                sym.label(300-text_w(label, 8) if right else 20, y+4, label, 8)
            pin_labels[key] = label
    # 標準のシールド付き変圧器を機能表示に使用。内部回路を省略した外部端子図なので接続点は複製しない。
    filename = 'transformator_ekr_2.elmt' if spec['electrostatic_shield'] else 'transformator_1f_2.elmt'
    source = collection_root(elements) / ('10_electric/10_allpole/330_transformers_power_supplies/10_transformers/' + filename)
    original = ET.parse(source).getroot()
    icon = []
    for node in original.findall('./description/*'):
        if node.tag not in ('arc', 'line'):
            continue
        node = copy.deepcopy(node)
        for attr in ('x', 'x1', 'x2'):
            if node.get(attr) is not None:
                node.set(attr, str(float(node.get(attr)) + 160))
        for attr in ('y', 'y1', 'y2'):
            if node.get(attr) is not None:
                node.set(attr, str(float(node.get(attr)) + 128))
        icon.append(node)
    if spec.get('outlet'):
        sym.rect(144, 168, 32, 24)
        sym.line(153, 174, 153, 182)
        sym.line(166, 174, 166, 182)
        sym.circle(158, 185, 4)
    features = spec['diagram_features']
    for i, text in enumerate(features):
        sym.label(16, 226 + i*18, text, 7)
    for key, (_, orient, x, y) in list(sym.terminals.items()):
        sym.terminals[key] = (stable_id(model + '/transformer/' + key), orient, x, y)
    root = sym.to_xml().find('definition')
    align_unit_header(root, 320)
    root.find('uuid').set('uuid', stable_id(model + '/transformer'))
    desc = root.find('description')
    desc.extend(icon)
    for terminal, key in zip(desc.findall('terminal'), sym.terminals):
        terminal.set('name', pin_labels[key])
    for node in desc.findall('dynamic_text'):
        node.set('uuid', stable_id(model + '/transformer/text/' + node.findtext('info_name')))
    root.find('informations').text = ('QElectroTech標準のシールド付き変圧器を機能表示に使用した外部端子図。内部結線は省略。'
                                     '資料: ' + spec['source'] + '\n' + original.findtext('informations', ''))
    infos = root.find('elementInformations')
    for name, value in [('manufacturer', spec['manufacturer']), ('manufacturer_reference', model),
                        ('comment', spec['display_ratings'])]:
        ET.SubElement(infos, 'elementInformation', name=name, show='1').text = value
    return root
