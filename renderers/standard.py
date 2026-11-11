"""QET標準記号の図形を保ち、機種の実端子・型式を割り当てる。"""
import os
import re
import tomllib
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def catalog():
    with (ROOT / 'parts/standard_symbols.toml').open('rb') as stream:
        return tomllib.load(stream)['symbols']


def collection_root(path=None):
    if path is not None:
        if not Path(path).is_dir():
            raise ValueError('指定されたQET標準コレクションがありません: ' + str(path))
        return Path(path).resolve()
    candidates = [path, os.environ.get('QET_ELEMENTS_DIR'),
                  'C:/Program Files/QElectroTech/elements',
                  'C:/Program Files (x86)/QElectroTech/elements',
                  '/usr/share/qelectrotech/elements']
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate).resolve()
    raise ValueError('QET標準コレクションがありません。--qet-elements またはQET_ELEMENTS_DIRで指定してください')


def bindings(spec, auxiliary=None):
    if spec.get('symbol_bindings'):
        if auxiliary:
            raise ValueError('この機器では補助接点構成を指定しません')
        names = set()
        for item in spec['symbol_bindings']:
            name = item['name']
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in names:
                raise ValueError('標準部品の機能名が不正または重複しています: ' + name)
            names.add(name)
            yield name, item['symbol'], item['terminals']
        return
    if auxiliary and spec['device_type'] != 'contactor':
        raise ValueError('リレーには補助接点構成を指定しません')
    coil = spec['coil']
    yield 'coil', 'coil', dict(zip(('a1', 'a2'), ([t] for t in coil['terminals'])))
    if spec['device_type'] == 'relay':
        for index, contact in enumerate(spec['contacts'], 1):
            if contact['type'] != 'changeover':
                raise ValueError('このリレーの接点方式は未対応です')
            yield f'contact_{index}', 'contact_changeover', {k: contact[k] for k in ('common', 'no', 'nc')}
    elif spec['device_type'] == 'contactor':
        contacts = spec['contacts']
        if len(contacts) != 3 or any(c['type'] != 'no' or c.get('role') != 'main' for c in contacts):
            raise ValueError('主接点3NO以外は未対応です')
        labels = {}
        for index, contact in enumerate(contacts, 1):
            labels[f'line{index}'], labels[f'load{index}'] = ([t] for t in contact['terminals'])
        yield 'main', 'main_contact_3p', labels
        choice = auxiliary or spec.get('default_auxiliary_option')
        options = spec.get('auxiliary_options', [])
        if spec.get('auxiliary_selection_required') and not choice:
            raise ValueError('補助接点構成を指定してください: ' + ', '.join(o['id'] for o in options))
        selected = next((o for o in options if o['id'] == choice), None)
        if choice and selected is None:
            raise ValueError('未対応の補助接点構成です: ' + choice)
        for index, contact in enumerate(selected['contacts'] if selected else [], 1):
            yield f'aux_{index}', 'contact_' + contact['type'], dict(zip(('first', 'second'), ([t] for t in contact['terminals'])))
    else:
        raise ValueError('未対応の標準機器です: ' + spec['device_type'])


def stable_id(value):
    return '{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'qet-io-builder/standard/' + value)) + '}'


def configured_spec(spec, configuration=None):
    options = spec.get('configuration_options', [])
    if not options:
        if configuration:
            raise ValueError('この機種では動作構成を指定しません')
        return spec
    choice = configuration or spec.get('default_configuration')
    selected = next((o for o in options if o['id'] == choice), None)
    if selected is None:
        raise ValueError('動作構成を指定してください: ' + ', '.join(o['id'] for o in options))
    result = dict(spec, symbol_bindings=selected['symbol_bindings'], configuration_id=selected['id'],
                  configuration_label=selected.get('label', selected['id']))
    if selected.get('display_ratings'):
        result['display_ratings'] = selected['display_ratings']
    return result


def bind_definition(model, spec, part, template, labels, elements=None):
    spec = dict(spec, display_ratings=spec.get('part_display_ratings', {}).get(part, spec.get('display_ratings', '')))
    records = catalog()
    if template not in records:
        raise ValueError('標準記号が参照カタログにありません: ' + template)
    if any(not isinstance(v, list) or not v or any(not isinstance(t, str) or not t for t in v) for v in labels.values()):
        raise ValueError('端子割当は空でない文字列の配列で指定してください')
    record = records[template]
    source = collection_root(elements) / record['path']
    definition = ET.parse(source).getroot()
    if definition.tag != 'definition' or definition.get('link_type') != record['link_type']:
        raise ValueError('標準記号の版・種類が参照情報と一致しません: ' + str(source))
    desc = definition.find('description')
    for terminal in desc.findall('terminal'):
        if terminal.get('uuid') in record.get('duplicate_terminal_uuids', []):
            desc.remove(terminal)
    terminals = desc.findall('terminal')
    coordinates = {(float(t.get('x')), float(t.get('y'))) for t in terminals}
    roles = record['terminal_roles']
    if len(terminals) != len(roles) or coordinates != {tuple(v) for v in roles.values()} or set(labels) != set(roles):
        raise ValueError('標準記号の端子配置が参照情報と一致しません: ' + str(source))
    for info in definition.findall('./kindInformations/kindInformation'):
        if record.get('kind', {}).get(info.get('name')) != info.text:
            raise ValueError('標準記号の接点構成が一致しません: ' + str(source))
    if record.get('export_link_type') == 'simple':
        # FM警報接点はコイルに従属せず、タグと形名を単独で表示する。
        definition.set('link_type', 'simple')
        for kinds in definition.findall('kindInformations'):
            definition.remove(kinds)
    elif record.get('export_link_type') == 'master':
        # 汎用保持スイッチにも従属接点を関連付けられるようにする。
        definition.set('link_type', 'master')
        kinds = ET.SubElement(definition, 'kindInformations')
        for name, value in record['kind'].items():
            ET.SubElement(kinds, 'kindInformation', name=name).text = value
    # 端子文字だけを置換し、操作位置などの固定表示と標準図形は保つ。
    overrides = spec.get('standard_text_overrides', {}).get(template, {})
    for item in list(desc):
        if item.tag == 'text' or item.tag == 'dynamic_text' and item.get('text_from') == 'UserText':
            text = item.get('text') if item.tag == 'text' else item.findtext('text', '')
            if text in record.get('terminal_texts', []):
                desc.remove(item)
            elif text in overrides:
                if item.tag == 'text':
                    item.set('text', overrides[text])
                else:
                    item.find('text').text = overrides[text]
    role_by_position = {tuple(v): k for k, v in roles.items()}
    identity = model + '/' + part + '/' + template + '/' + '/'.join(k + ':' + ','.join(labels[k]) for k in sorted(labels))
    if spec.get('configuration_id'):
        identity += '/configuration/' + spec['configuration_id']
    text_right = 30
    for terminal in terminals:
        role = role_by_position[(float(terminal.get('x')), float(terminal.get('y')))]
        text = '/'.join(labels[role])
        terminal.set('name', text)
        terminal.set('uuid', stable_id(identity + '/' + role))
        if template in ('coil', 'timer_on_delay', 'lamp'):
            polarity = spec.get('lamp' if template == 'lamp' else 'coil', {}).get('polarity_by_terminal', {}).get(labels[role][0])
            if polarity:
                text += ' (' + polarity + ')' if polarity in ('+', '-') else ' ' + polarity
        elif template in ('main_contact_3p', 'thermal_relay_3p'):
            text = text.replace('/', '\n')
        elif record['category'] == 'breaker':
            text = text.replace(' ', '\n')
        x, y = record.get('text_roles', {}).get(role, [float(terminal.get('x')) + 4, float(terminal.get('y')) - 9])
        if terminal.get('orientation') == 'w' and role not in record.get('text_roles', {}):
            width = max(sum(4 if ord(c) < 128 else 8 for c in line) for line in text.split('\n'))
            x = float(terminal.get('x')) - width - 4
        node = ET.SubElement(desc, 'dynamic_text', uuid=stable_id(identity + '/text/' + role),
                             x=str(x), y=str(y), z='5', text_from='UserText',
                             Halignment='AlignLeft', Valignment='AlignTop', rotation='0',
                             text_width='-1', keep_visual_rotation='false', frame='false',
                             font='MS Gothic,5,-1,5,50,0,0,0,0,0' if template == 'thermal_relay_3p' else 'MS Gothic,6,-1,5,50,0,0,0,0,0')
        ET.SubElement(node, 'text').text = text
        if template == 'transformer_1p_tapped':
            node.set('rotation', '270')
            node.set('font', 'MS Gothic,5,-1,5,50,0,0,0,0,0')
        text_right = max(text_right, x + max(sum(4 if ord(c) < 128 else 8 for c in line) for line in text.split('\n')))
    definition.find('uuid').set('uuid', stable_id(identity))
    names = definition.find('names')
    names.clear()
    display_name = model + ' ' + record['label']
    if record['category'] == 'terminal':
        terminal_names = dict.fromkeys(t for values in labels.values() for t in values)
        display_name += '（' + ' / '.join(terminal_names) + '）'
    if record['category'] == 'contact' and set(labels) == {'first', 'second'}:
        number = re.search(r'(\d+)$', part)
        display_name += (number.group(1) if number else '')
        display_name += '（' + '/'.join(labels['first']) + '–' + '/'.join(labels['second']) + '）'
    if set(labels) == {'common', 'no', 'nc'}:
        number = re.search(r'(\d+)$', part)
        contact_name = 'c接点' if template == 'contact_changeover' else record['label']
        if template == 'contact_changeover' and part.startswith('instant_contact_'):
            contact_name = '瞬時c接点'
        display_name = model + ' ' + contact_name + (number.group(1) if number else '')
        display_name += '（COM:' + '/'.join(labels['common']) + ' / a:' + '/'.join(labels['no']) + ' / b:' + '/'.join(labels['nc']) + '）'
    if spec.get('configuration_label'):
        display_name += ' [' + spec['configuration_label'] + ']'
    ET.SubElement(names, 'name', lang='ja').text = display_name
    ET.SubElement(names, 'name', lang='en').text = model + ' ' + part
    infos = definition.find('elementInformations')
    if infos is None:
        infos = ET.SubElement(definition, 'elementInformations')
    for key, value in (('designation', record['label']), ('manufacturer', spec['manufacturer']), ('manufacturer_reference', model),
                       ('description', record['label'])):
        old = infos.find(f"elementInformation[@name='{key}']")
        if old is not None:
            infos.remove(old)
        ET.SubElement(infos, 'elementInformation', name=key, show='1').text = value
    label = next((n for n in desc.findall('dynamic_text') if n.findtext('info_name') == 'label'), None)
    if label is None and record['category'] == 'terminal':
        # タグ欄がない標準PE図にも、自由記述の機器番号を表示できるようにする。
        label = ET.SubElement(desc, 'dynamic_text', uuid=stable_id(identity + '/label'),
                              x='80', y='-65', z='5', text_from='ElementInfo',
                              Halignment='AlignLeft', Valignment='AlignTop', rotation='0',
                              text_width='-1', keep_visual_rotation='false', frame='false',
                              font='MS Gothic,9,-1,5,50,0,0,0,0,0')
        ET.SubElement(label, 'text')
        ET.SubElement(label, 'info_name').text = 'label'
        if infos.find("elementInformation[@name='label']") is None:
            ET.SubElement(infos, 'elementInformation', name='label', show='1')
    if label is not None and record['category'] == 'terminal':
        # 横へ出る分岐配線を、機器番号・形名・定格で塞がない。
        label.set('x', '80')
        label.set('y', '-65')
    if label is not None and template == 'noise_filter_1p':
        # 右向きFG端子の配線経路を、タグ・形名・定格で塞がない。
        label.set('y', '-65')
    if label is not None and record['category'] in ('ammeter', 'current_transformer'):
        # 計器・CTの水平方向の配線経路に形名・定格を置かない。
        label.set('y', '-75')
    if label is not None and template == 'inductive_sensor_2output':
        # 左右に出るNO/NC配線の延長上へ機器情報を置かない。
        label.set('y', '-80')
    if label is not None:
        label.set('x', str(max(float(label.get('x')), text_right + 12)))
    x, y = (max(50, float(label.get('x'))), float(label.get('y')) + 17) if label is not None else (max(50, text_right + 12), 10)
    if label is not None and (template in ('coil', 'timer_on_delay') or record['category'] == 'switch' and definition.get('link_type') == 'master'):
        # QETがタグ下に表示する接点参照と、形名・定格が重ならないようにする。
        y = float(label.get('y')) - 34
    node = ET.SubElement(desc, 'dynamic_text', uuid=stable_id(identity + '/model'),
                         x=str(x), y=str(y), z='5', text_from='ElementInfo',
                         Halignment='AlignLeft', Valignment='AlignTop', rotation='0',
                         text_width='-1', keep_visual_rotation='false', frame='false',
                         font='MS Gothic,7,-1,5,50,0,0,0,0,0')
    ET.SubElement(node, 'text')
    ET.SubElement(node, 'info_name').text = 'manufacturer_reference'
    if spec.get('display_ratings'):
        for old in infos.findall("elementInformation[@name='comment']"):
            infos.remove(old)
        ET.SubElement(infos, 'elementInformation', name='comment', show='1').text = spec['display_ratings']
        for old in desc.findall('dynamic_text'):
            if old.findtext('info_name') == 'comment':
                desc.remove(old)
        rating = ET.SubElement(desc, 'dynamic_text', uuid=stable_id(identity + '/rating'),
                               x=str(x), y=str(y + 15), z='5', text_from='ElementInfo',
                               Halignment='AlignLeft', Valignment='AlignTop', rotation='0',
                               text_width='-1', keep_visual_rotation='false', frame='false',
                               font='MS Gothic,7,-1,5,50,0,0,0,0,0')
        ET.SubElement(rating, 'text')
        ET.SubElement(rating, 'info_name').text = 'comment'
    for node in desc.findall('dynamic_text'):
        if node.findtext('info_name') == 'designation':
            # 標準記号の用途欄も形名・定格の情報列に置き、代替フォントの幅に依存させない。
            node.set('font', 'MS Gothic,' + node.get('font').split(',', 1)[1])
            node.set('x', str(x))
            node.set('y', str(y + (30 if spec.get('display_ratings') else 15)))
            node.set('Valignment', 'AlignTop')
    original = definition.find('informations')
    if spec.get('coil'):
        note = ('コイル電圧・ソケットは別途選択。基本形式から注文SKUを推定しない。'
                if spec['coil'].get('voltage_selection_required', True)
                else 'コイル電圧は機種定義の固定定格。ソケット・使用条件は別途確認。')
    else:
        note = '定格・操作条件は機種定義と使用条件に合わせて指定。'
    original.text = (original.text or '') + '\n標準記号: QElectroTech ' + record['path'] + '\n型式・端子割当: ' + model + '\n資料: ' + spec['source'] + '\n' + note
    if spec.get('verification_note'):
        original.text += '\n' + spec['verification_note']
    for extra in spec.get('notes', []):
        original.text += '\n' + extra
    if spec.get('configuration_label'):
        original.text += '\n動作構成: ' + spec['configuration_label']
    for node in desc.findall('dynamic_text'):
        if node.findtext('info_name') == 'label':
            node.set('uuid', stable_id(identity + '/label'))
    return definition


def export_model(model, spec, output, auxiliary=None, elements=None, configuration=None):
    # 全構成と標準記号を検証してからファイルを書き出す。
    spec = configured_spec(spec, configuration)
    if spec.get('component_style') == 'swallow_transformer':
        if auxiliary:
            raise ValueError('トランスには補助接点構成を指定しません')
        from .swallow_transformer import definition
        definitions = [('unit', definition(model, spec, elements))]
    elif spec.get('component_style') in ('terminal_box', 'ethernet_switch'):
        if auxiliary:
            raise ValueError('箱型電子機器には補助接点構成を指定しません')
        if spec['component_style'] == 'ethernet_switch':
            from .ethernet_switch import definition
        else:
            from .terminal_box import definition
        definitions = [('unit', definition(model, spec))]
    else:
        assigned = list(bindings(spec, auxiliary))
        definitions = [(part, bind_definition(model, spec, part, template, labels, elements))
                       for part, template, labels in assigned]
    name = re.sub(r'[<>:"/\\|?*]', '-', model)
    folder = Path(output) / name
    if auxiliary:
        folder = folder / auxiliary
    if spec.get('configuration_id'):
        folder = folder / spec['configuration_id']
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for part, definition in definitions:
        path = folder / (part + '.elmt')
        ET.indent(definition, space='  ')
        ET.ElementTree(definition).write(path, encoding='utf-8', xml_declaration=True)
        paths.append(path)
    return paths
