"""メーカー定義とQET標準記号で、配線済みの自己保持回路を作る。PDFは出力しない。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
from xml.etree import ElementTree as ET

import gen_io_page as g
from renderers import standard


class Imported(g.Symbol):
    def __init__(self, name, definition, roles):
        super().__init__(name, name, int(definition.get('width')), int(definition.get('height')),
                         int(definition.get('hotspot_x')), int(definition.get('hotspot_y')))
        self.definition = definition
        by_position = {tuple(v): k for k, v in roles.items()}
        for terminal in definition.findall('./description/terminal'):
            x, y = float(terminal.get('x')), float(terminal.get('y'))
            self.terminals[by_position[(x, y)]] = (terminal.get('uuid'), terminal.get('orientation'), x, y)

    def to_xml(self):
        element = ET.Element('element', name=self.name + '.elmt')
        element.append(copy.deepcopy(self.definition))
        return element


def make(output, horizontal_coils=False):
    records = g.read_unit_definitions()['standard_device']
    symbols = {k: v for k, v in g.build_symbols().items() if k in ('junction', 'node')}
    catalog = standard.catalog()
    models = [('start', 'HW1B-M110G', None), ('stop', 'HW1B-M101R', None),
              ('relay', 'MY2N', None), ('contactor', 'SD-T12', '1a1b'),
              ('lamp', 'M22N-BN-TGA-GC', None)]
    for alias, model, auxiliary in models:
        spec = copy.deepcopy(records[model.upper()])
        if alias in ('relay', 'contactor'):
            # 電圧選択はこの作図例だけの指定。機種の基本定義は変更しない。
            spec['display_ratings'] = '作図例: DC24V' + (' / 補助1a1b' if auxiliary else '')
        for part, template, labels in standard.bindings(spec, auxiliary):
            name = alias + '_' + part
            definition = standard.bind_definition(model, spec, part, template, labels)
            symbols[name] = Imported(name, definition, catalog[template]['terminal_roles'])

    page = g.Page(symbols)

    def position(x, y):
        if horizontal_coils:
            return (3 * {120: 45, 210: 110, 230: 140, 280: 150, 360: 210, 460: 270, 590: 300, 700: 360}[y],
                    {150: 220, 350: 340, 650: 480, 1010: 650}[x])
        return x, y

    def wire(a, ta, b, tb, *args):
        directions = {'n': 'w', 's': 'e', 'e': 's', 'w': 'n'}
        if horizontal_coils:
            if a[1].name == 'junction': ta = directions[ta]
            if b[1].name == 'junction': tb = directions[tb]
        page.wire(a, ta, b, tb, *args)

    def place(name, x, y, label):
        placed = page.place(name, *position(x, y), label=label)
        element = page.elements[-1]
        definition = symbols[name].definition
        infos = element.find('elementInformations')
        for info in definition.findall('./elementInformations/elementInformation'):
            if info.get('name') != 'label':
                old = infos.find("elementInformation[@name='%s']" % info.get('name'))
                if old is not None:
                    infos.remove(old)
                infos.append(copy.deepcopy(info))
        for text in definition.findall('./description/dynamic_text'):
            text = copy.deepcopy(text)
            text.tag = 'dynamic_elmt_text'
            # 情報列を端子から離し、タグ・形名・定格の順と参照用の高さを保つ。
            if name.endswith('_coil') and text.findtext('info_name') in ('label', 'manufacturer_reference', 'comment'):
                text.set('x', '90')
                text.set('y', {'label': '-10', 'manufacturer_reference': '7', 'comment': '22'}[text.findtext('info_name')])
                text.set('rotation', '0')
            element.find('dynamic_texts').append(text)
        if horizontal_coils:
            element.set('orientation', '3')
            terminals = definition.findall('./description/terminal')
            for text in element.findall('./dynamic_texts/dynamic_elmt_text'):
                field = text.findtext('info_name')
                tx, ty = 30, {'label': 25, 'manufacturer_reference': 42, 'comment': 57}.get(field, 72)
                if text.get('text_from') == 'UserText':
                    value = text.findtext('text', '').split()[0]
                    terminal = next((t for t in terminals if t.get('name') == value), None)
                    if terminal is not None:
                        tx = float(terminal.get('y')) - 5
                        ty = -float(terminal.get('x')) - (30 if name.endswith('_coil') else 18)
                # 記号を270度回し、文字を逆回転して読める向きを保つ。
                text.set('x', str(-ty)); text.set('y', str(tx))
                text.set('rotation', '90')
        return placed

    def link(master, *contacts):
        by_uuid = {el.get('uuid'): el for el in page.elements}
        for contact in contacts:
            for a, b in ((master, contact), (contact, master)):
                element = by_uuid[a[0]]
                links = element.find('links_uuids')
                if links is None:
                    links = ET.SubElement(element, 'links_uuids')
                ET.SubElement(links, 'link_uuid', uuid=b[0])

    node = lambda x, y: page.place('junction', *position(x, y))
    if horizontal_coils:
        page.text(24, 22, '自己保持・接触器・運転表示', 11, True)
        page.text(24, 45, 'DC24V / 国産メーカー部品・実端子番号', 8)
    else:
        page.text(70, 22, '国産メーカー部品による自己保持・接触器駆動回路', 13, True)
        page.text(70, 53, 'DC24V / 標準記号・実端子番号・メーカー型式・コイルと接点の関連付けを確認', 9)
    page.text(114 if horizontal_coils else 80, 60 if horizontal_coils else 95, 'P24 (+24V)', 9, True)
    page.text(1050 if horizontal_coils else 80, 60 if horizontal_coils else 707, 'N24 (0V)', 9, True)
    tops = [node(x, 120) for x in (150, 650, 1010)]
    bottoms = [node(x, 700) for x in (150, 650, 1010)]
    for rail, number in ((tops, 'P24'), (bottoms, 'N24')):
        for a, b in zip(rail, rail[1:]):
            wire(a, 'e', b, 'w', number)
        if horizontal_coils:
            top = page.place('junction', rail[0][2], 80)
            bottom = page.place('junction', rail[-1][2], 790)
            page.wire(top, 's', rail[0], 'n', number)
            page.wire(rail[-1], 's', bottom, 'n', number)
    stop = place('stop_nc', 150, 210, 'S0 停止')
    start = place('start_pushbutton', 150, 360, 'S1 起動')
    hold = place('relay_contact_1', 350, 360, 'K1 自己保持')
    relay = place('relay_coil', 150, 590, 'K1')
    drive = place('relay_contact_2', 650, 230, 'K1 接触器駆動')
    contactor = place('contactor_coil', 650, 590, 'KM1')
    running = place('contactor_aux_1', 1010, 230, 'KM1 運転確認')
    lamp = place('lamp_lamp', 1010, 590, 'H1 運転（緑）')
    upper, lower = node(150, 280), node(150, 460)
    hold_upper, hold_lower = node(350, 280), node(350, 460)
    for a, ta, b, tb in [
        (tops[0], 's', stop, 'first'), (stop, 'second', upper, 'n'),
        (upper, 's', start, 'first'), (start, 'second', lower, 'n'),
        (upper, 'e', hold_upper, 'w'), (hold_upper, 's', hold, 'no'),
        (hold, 'common', hold_lower, 'n'), (hold_lower, 'w', lower, 'e'),
        (lower, 's', relay, 'a1'), (relay, 'a2', bottoms[0], 'n'),
        (tops[1], 's', drive, 'no'), (drive, 'common', contactor, 'a1'),
        (contactor, 'a2', bottoms[1], 'n'),
        (tops[2], 's', running, 'first'), (running, 'second', lamp, 'first'),
        (lamp, 'second', bottoms[2], 'n'),
    ]:
        wire(a, ta, b, tb)
    link(relay, hold, drive)
    link(contactor, running)
    if horizontal_coils:
        page.text(1100, 700, '起動: S1 / 停止: S0', 8)
        page.text(1100, 720, '保存後に参照表を更新', 8)
        page.text(1100, 740, '作図用サンプル', 8)
    else:
        page.text(70, 745, '操作: S1でK1励磁 → 9–5で自己保持 → 12–8でKM1励磁 → 13–14でH1点灯。S0で解除。', 9)
        page.text(70, 772, '作図確認用。主回路・保護協調・サーマル/モータ容量の選定は含まない。リレー番号は本体ピン番号。', 8)
    page.finish()
    cfg = dict(project_title='国産制御部品 動作確認サンプル', date='20261028', author='', revision='',
               front_pages=False, drawing_no='EX-001')
    project, _ = g.build_project(cfg, [])
    category = project.find('./collection/category/category')
    category.clear()
    category.set('name', 'plc_io')
    names = ET.SubElement(category, 'names')
    ET.SubElement(names, 'name', lang='ja').text = '制御部品サンプル'
    for name in {p[0] for p in page.placed} | {'node'}:
        category.append(symbols[name].to_xml())
    g.add_diagram(project, cfg, '自己保持・接触器・運転表示', 1, page)
    project.find('diagram').append(copy.deepcopy(project.find('./newdiagrams/xrefs')))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(project, space='  ')
    ET.ElementTree(project).write(output, encoding='utf-8', xml_declaration=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', default='_review/control_sample/control_sample.qet')
    parser.add_argument('--horizontal-coils', '--horizontal-ladder', action='store_true', help='P24左・N24右の横方向回路にする')
    args = parser.parse_args()
    print(make(args.output, args.horizontal_coils))
