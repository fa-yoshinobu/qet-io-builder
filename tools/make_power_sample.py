"""登録済み電源を、端子数に合わせて1冊の確認用QETへまとめる。"""
import argparse
import copy
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gen_io_page as gen
from tools.export_power_supply_elements import definition
from tools.make_control_sample import Imported


def make(output):
    specs = gen.read_unit_definitions()['power_supply']
    symbols = {k: v for k, v in gen.build_symbols().items() if k in ('node', 'junction')}
    groups = {'小型枠': [], '多端子・通信': [], '分岐電源': []}
    for i, model in enumerate(sorted(specs)):
        root = definition(model, specs[model])
        frame = root.find('./description/rect[@y="0"]')
        group = '小型枠' if frame.get('height') == '150' else '分岐電源' if specs[model].get('component_style') == 'smart_power_supply' else '多端子・通信'
        roles = {str(j): [float(p.get('x')), float(p.get('y'))]
                 for j, p in enumerate(root.findall('./description/terminal'))}
        name = 'power_' + str(i)
        symbols[name] = Imported(name, root, roles)
        groups[group].append((name, model, 'AVR' + str(i+1)))
    cfg = gen.project_config(dict(project_title='DC24V電源 部品一覧', date='20261030', front_pages=False))
    project, _ = gen.build_project(cfg, [])
    category = project.find('./collection/category/category')
    category.clear()
    category.set('name', 'plc_io')
    names = ET.SubElement(category, 'names')
    ET.SubElement(names, 'name', lang='ja').text = 'DC24V電源'
    for symbol in symbols.values():
        category.append(symbol.to_xml())
    number = 0
    for title, models in groups.items():
        per_page = {'小型枠': 6, '多端子・通信': 4, '分岐電源': 2}[title]
        for start in range(0, len(models), per_page):
            page = gen.Page(symbols)
            for i, (name, model, tag) in enumerate(models[start:start+per_page]):
                x = 130 + (i % 2)*610
                y = 80 + (i // 2)*(230 if per_page == 6 else 360)
                page.place(name, x, y, label=tag)
                element = page.elements[-1]
                for text in symbols[name].definition.findall('./description/dynamic_text'):
                    text = copy.deepcopy(text)
                    text.tag = 'dynamic_elmt_text'
                    element.find('dynamic_texts').append(text)
                frame = symbols[name].definition.find('./description/rect[@y="0"]')
                if y + float(frame.get('height')) > 820:
                    raise ValueError('部品が図枠を超えています: ' + model)
            page.finish()
            number += 1
            gen.add_diagram(project, cfg, 'DC24V電源 ' + title, number, page)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(project, space='  ')
    ET.ElementTree(project).write(output, encoding='utf-8', xml_declaration=True)
    return output, len(specs), number


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(make(parser.parse_args().output))
