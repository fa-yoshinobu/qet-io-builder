"""保存済みQETのコイル・接点リンクからa/b横表を更新する。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import math
import os
import shutil
import tempfile
from xml.etree import ElementTree as ET

import gen_io_page as g
from renderers.standard import collection_root

OWNER = 'qet_io_xref_owner'


def infos(element):
    return {n.get('name'): n.text or '' for n in element.findall('./elementInformations/elementInformation')}


def put_info(element, name, value):
    parent = element.find('elementInformations')
    if parent is None:
        parent = ET.SubElement(element, 'elementInformations')
    node = parent.find("elementInformation[@name='%s']" % name)
    if node is None:
        node = ET.SubElement(parent, 'elementInformation', name=name, show='0')
    node.text = str(value)


def definitions(root):
    result = {}
    def visit(category, path):
        path += category.get('name') + '/'
        for node in category.findall('element'):
            result['embed://' + path + node.get('name')] = node.find('definition')
        for child in category.findall('category'):
            visit(child, path)
    for category in root.findall('./collection/category'):
        visit(category, '')
    return result


def location(page, folio, element):
    x, y = float(element.get('x')), float(element.get('y'))
    col = math.floor((x - 20) / float(page.get('colsize', '60')))
    row = math.floor((y - 20) / float(page.get('rowsize', '80')))
    if not (0 <= col < int(page.get('cols', '17')) and 0 <= row < int(page.get('rows', '10'))):
        raise ValueError('接点が図枠の参照範囲外です: ' + infos(element).get('label', element.get('uuid')))
    if row >= 26:
        raise ValueError('27行以上の図枠には対応していません')
    return f'{folio}-{chr(65 + row)}{col + 1}'


def update(root, dx=None, dy=None):
    """ツリー内の管理対象表とコイルの参照ラベルだけ変更する。配線・部品位置は変更しない。"""
    defs = definitions(root)
    pages = sorted(root.findall('diagram'), key=lambda p: int(p.get('order', '0')))
    records = g.read_unit_definitions()['standard_device']
    elements, managed, by_uuid = [], [], {}
    for folio, page in enumerate(pages, 1):
        for element in page.findall('./elements/element'):
            if OWNER in infos(element):
                managed.append((page, element))
                continue
            uid = element.get('uuid')
            if uid in by_uuid:
                raise ValueError('部品の固有IDが重複しています: ' + str(uid))
            definition = defs.get(element.get('type'))
            if definition is None and element.get('type', '').startswith('common://'):
                definition = ET.parse(collection_root() / element.get('type')[9:]).getroot()
            if definition is None:
                if element.find('links_uuids/link_uuid') is not None:
                    raise ValueError('関連付いた部品の定義が見つかりません: ' + element.get('type', ''))
                continue
            kind = {n.get('name'): n.text for n in definition.findall('./kindInformations/kindInformation')}
            item = dict(page=page, folio=folio, el=element, definition=definition, kind=kind)
            by_uuid[uid] = item
            elements.append(item)
    masters = {uid: item for uid, item in by_uuid.items() if item['definition'].get('link_type') == 'master'
               and item['kind'].get('type') == 'coil'}
    if not masters and not managed:
        return 0
    linked = {uid: set() for uid in masters}
    for uid, item in by_uuid.items():
        for link in item['el'].findall('./links_uuids/link_uuid'):
            other = link.get('uuid')
            if other not in by_uuid:
                raise ValueError('関連付け先が見つかりません: ' + str(other))
            if uid in masters:
                linked[uid].add(other)
            if other in masters:
                linked[other].add(uid)
    old = {}
    for page, table in managed:
        uid = infos(table)[OWNER]
        if uid in old:
            raise ValueError('同じコイルの管理表が複数あります: ' + uid)
        old[uid] = table

    collection = root.find('collection')
    if collection is None:
        collection = ET.SubElement(root, 'collection')
    category = collection.find("category[@name='qet_io_xrefs']")
    if category is None:
        category = ET.SubElement(collection, 'category', name='qet_io_xrefs')
        names = ET.SubElement(category, 'names')
        ET.SubElement(names, 'name', lang='ja').text = 'a・b接点参照表（外部更新）'

    # 使用端子を調べ、c接点の未使用側を参照欄に掲載しない。
    wired = set()
    for page in pages:
        id_map = {}
        for item in elements:
            if item['page'] is not page:
                continue
            terms = item['definition'].findall('./description/terminal')
            positions = {(float(t.get('x')), float(t.get('y'))): t.get('uuid') for t in terms}
            for terminal in item['el'].findall('./terminals/terminal'):
                position = (float(terminal.get('x')), float(terminal.get('y')))
                id_map[terminal.get('id')] = (item['el'].get('uuid'), positions.get(position))
        for wire in page.findall('./conductors/conductor'):
            for end in ('1', '2'):
                if wire.get('element' + end):
                    wired.add((wire.get('element' + end), wire.get('terminal' + end)))
                elif wire.get('terminal' + end) in id_map:
                    wired.add(id_map[wire.get('terminal' + end)])

    for uid, master in masters.items():
        element, page = master['el'], master['page']
        data = dict(infos(master['definition']), **infos(element))
        model, label = data.get('manufacturer_reference', ''), data.get('label', '')
        spec = records.get(model.upper(), {})
        poles = spec.get('contacts', []) if spec.get('device_type') == 'relay' else []
        groups = [{'pins': set(c['common'] + c['no'] + c['nc']), 'a': [], 'b': []} for c in poles]
        contacts = sorted(linked[uid], key=lambda key: (by_uuid[key]['folio'], float(by_uuid[key]['el'].get('x')), key))
        for other in contacts:
            item = by_uuid[other]
            if item['definition'].get('link_type') != 'slave':
                raise ValueError('コイルの関連先が接点ではありません: ' + other)
            state = item['kind'].get('state')
            if state not in ('NO', 'NC', 'SW'):
                raise ValueError('未対応の接点種別です: ' + str(state))
            terminals = item['definition'].findall('./description/terminal')
            names = {t.get('name') for t in terminals if t.get('name')}
            index = next((i for i, group in enumerate(groups) if names and names <= group['pins']), None)
            if index is None and poles:
                raise ValueError(f'{label}: 接点端子 {sorted(names)} が {model} の極と一致しません')
            if index is None:
                # 多極主接点は端子の並びごとに1列。端子名がない機器もIDで区別する。
                count = int(item['kind'].get('number', '1'))
                for _ in range(count):
                    groups.append({'pins': names or {other}, 'a': [], 'b': []})
                indices = range(len(groups) - count, len(groups))
            else:
                indices = [index]
            reference = location(item['page'], item['folio'], item['el'])
            rows = ['a' if state == 'NO' else 'b'] if state != 'SW' else ['a', 'b']
            if state == 'SW' and index is not None and poles:
                used = {t.get('name') for t in terminals if (other, t.get('uuid')) in wired}
                selected = [row for row, key in (('a', 'no'), ('b', 'nc')) if used & set(poles[index][key])]
                rows = selected or rows
            for i in indices:
                for row in rows:
                    if reference not in groups[i][row]:
                        groups[i][row].append(reference)
        if not groups:
            groups = [{'pins': set(), 'a': [], 'b': []}]
        rows = [[', '.join(group[row]) for group in groups] for row in ('a', 'b')]
        wc = max(g.REF_WC, math.ceil(max(g.text_w(text, 6) for row in rows for text in row) + 6))
        width, height = 10 + wc * len(groups), 24
        name = 'xref_' + uid.strip('{}').replace('-', '')
        symbol = g.Symbol(name, 'a・b接点参照表 ' + label, width + 4, height + 4, 2, 2)
        symbol.rect(0, 0, width, height)
        symbol.line(0, 12, width, 12, thin=True)
        for x in [10] + [10 + wc * n for n in range(1, len(groups))]:
            symbol.line(x, 0, x, height, thin=True)
        def centered(cx, baseline, text, size):
            symbol.label(cx - g.text_w(text, size) / 2, baseline, text, size)
        for r, row in enumerate(rows):
            centered(5, 9 + r * 12, ('a', 'b')[r], 7)
            for n, text in enumerate(row):
                centered(10 + wc * (n + .5), 9 + r * 12, text, 6)
        definition_node = symbol.to_xml()
        definition_node.find('./definition/informations').text = 'qet-io-builder管理表。保存した図面から外部更新する。'
        existing = category.find("element[@name='%s.elmt']" % name)
        if existing is not None:
            if uid not in old:
                raise ValueError('管理表の部品名が既存部品と衝突しています: ' + name)
            category.remove(existing)
        category.append(definition_node)
        x, y = float(element.get('x')), float(element.get('y'))
        previous = old.get(uid)
        if previous is not None:
            metadata = infos(previous)
            tx = float(previous.get('x')) + x - float(metadata['qet_io_xref_master_x'])
            ty = float(previous.get('y')) + y - float(metadata['qet_io_xref_master_y'])
        else:
            horizontal = int(element.get('orientation', '0')) % 2 == 1
            tx = x + (dx if dx is not None else float(data.get('qet_io_xref_dx', -20 if horizontal else 55)))
            ty = y + (dy if dy is not None else float(data.get('qet_io_xref_dy', 35 if horizontal else -16)))
        holder = g.Page({name: symbol})
        holder.place(name, tx, ty, infos={OWNER: uid, 'qet_io_xref_master_x': str(x), 'qet_io_xref_master_y': str(y)})
        table = holder.elements[0]
        table.set('type', 'embed://qet_io_xrefs/' + name + '.elmt')
        if previous is not None:
            table.set('uuid', previous.get('uuid'))
        page.find('elements').append(table)
        # 標準自動参照の表示だけ止める。コイル・接点のリンクと機器情報は保つ。
        label_ids = set(json.loads(data.get('qet_io_xref_labels', '[]')))
        model_ids = {t.get('uuid') for t in master['definition'].findall('./description/dynamic_text')
                     if t.findtext('info_name') == 'manufacturer_reference'}
        for text in element.findall('./dynamic_texts/dynamic_elmt_text'):
            is_label = text.findtext('info_name') == 'label' or text.get('uuid') in label_ids
            is_model = text.findtext('info_name') == 'manufacturer_reference' or text.get('uuid') in model_ids
            if is_label or is_model:
                if data.get('qet_io_xref_coil_caption') != '1':
                    orientation = int(element.get('orientation', '0')) % 4
                    tx = -g.text_w(label if is_label else model, 9 if is_label else 7) / 2
                    ty = -64 if is_label else -43
                    local_x, local_y = [(tx, ty), (ty, -tx), (-tx, -ty), (-ty, tx)][orientation]
                    text.set('x', str(local_x)); text.set('y', str(local_y))
                    text.set('rotation', str((-orientation * 90) % 360))
                if is_model:
                    text.set('text_from', 'ElementInfo')
                    if text.find('info_name') is None:
                        ET.SubElement(text, 'info_name').text = 'manufacturer_reference'
                    continue
                label_ids.add(text.get('uuid'))
                text.set('text_from', 'UserText')
                for info_name in text.findall('info_name'):
                    text.remove(info_name)
                value = text.find('text')
                if value is None:
                    value = ET.SubElement(text, 'text')
                value.text = label
        put_info(element, 'qet_io_xref_labels', json.dumps(sorted(label_ids)))
        put_info(element, 'qet_io_xref_coil_caption', '1')

    for page, table in managed:
        page.find('elements').remove(table)
        owner = infos(table)[OWNER]
        if owner not in masters:
            node = category.find("element[@name='%s']" % table.get('type', '').split('/')[-1])
            if node is not None:
                category.remove(node)
    # フッタ固定の標準参照が並行して出ないよう、コイル種別のみラベル追従にする。
    for xref in root.findall(".//xref[@type='coil']"):
        xref.set('snapto', 'label')
    return len(masters)


def update_file(source, output=None, dx=None, dy=None):
    source = Path(source).resolve()
    output = Path(output).resolve() if output else source.with_name(source.stem + '_xref.qet')
    root = ET.parse(source, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()
    count = update(root, dx, dy)
    output.parent.mkdir(parents=True, exist_ok=True)
    if source == output:
        backup = source.with_suffix(source.suffix + '.bak')
        n = 1
        while backup.exists():
            backup = source.with_suffix(source.suffix + f'.bak{n}')
            n += 1
        shutil.copy2(source, backup)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix='.qet.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            ET.ElementTree(root).write(stream, encoding='utf-8', xml_declaration=True)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return output, count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output', nargs='?')
    parser.add_argument('--in-place', action='store_true', help='元ファイルを更新する（バックアップ作成）')
    parser.add_argument('--dx', type=float, help='初回のコイルから表までの横距離（省略時は向きから配置）')
    parser.add_argument('--dy', type=float, help='初回のコイルから表までの縦距離（省略時は向きから配置）')
    args = parser.parse_args()
    if args.in_place and args.output:
        parser.error('--in-placeと出力ファイルの同時指定はできません')
    try:
        path, count = update_file(args.source, args.source if args.in_place else args.output, args.dx, args.dy)
    except (ValueError, OSError, ET.ParseError) as error:
        parser.exit(1, str(error) + '\n')
    print(f'{count}個の参照表を更新: {path}')
