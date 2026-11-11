"""コネクタの絵(renderers/connectors.py の共通部品)を、QET に置ける単体 .elmt 部品として書き出す。
使い方: python tools/export_connector_elements.py parts/connectors/elements
QET の「ユーザーコレクション」にフォルダごとコピーすると、図面に手で置ける。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import uuid
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
from gen_io_page import Symbol
from renderers import connectors

# 性別で絵が変わるもの(ピンの塗り)は オス・メス を両方書き出す
GENDERED = {'dsub9', 'dsub15', 'dsub25', 'minidin8', 'minidin6', 'handheld32', 'handheld42',
            'm12_a_5', 'm12_x_8', 'm12_l_5', '7_8_5', 'econ_4', 'fcn_40', 'power_5'}
GENDER_JA = {'male': 'オス', 'female': 'メス'}


def definition(kind, gender):
    symbols = {}
    key = connectors.symbol(symbols, Symbol, kind, gender)
    symbol = symbols[key]
    label = connectors.CONNECTORS[kind][0] + (' ' + GENDER_JA[gender] if gender else '')
    for name, (_, orient, x, y) in list(symbol.terminals.items()):
        stable = '{' + str(uuid.uuid5(uuid.NAMESPACE_URL, f'qet-io-builder/connector/{key}/{name}')) + '}'
        symbol.terminals[name] = (stable, orient, x, y)
    element = symbol.to_xml().find('definition')
    element.find('uuid').set('uuid', '{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'qet-io-builder/connector/' + key)) + '}')
    for name in element.findall('./names/name'):
        if name.get('lang') == 'ja':
            name.text = label
    element.find('informations').text = 'コネクタ正面図(qet-io-builder 共通部品 renderers/connectors.py)'
    return key, element


def export(target=ROOT / 'parts/connectors/elements'):
    target.mkdir(parents=True, exist_ok=True)
    outputs = []
    for kind in connectors.CONNECTORS:
        for gender in (('male', 'female') if kind in GENDERED else ('',)):
            key, xml = definition(kind, gender)
            ET.indent(xml, space='  ')
            path = target / (key + '.elmt')
            ET.ElementTree(xml).write(path, encoding='utf-8', xml_declaration=True)
            outputs.append(path)
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path, help='出力先フォルダー（従来の出力先: parts/connectors/elements）')
    args = parser.parse_args(argv)
    print('Exported', len(export(args.output_dir)), 'connector parts')


if __name__ == '__main__':
    main()
