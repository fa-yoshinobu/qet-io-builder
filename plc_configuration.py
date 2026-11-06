"""機種JSONの接続条件からPLC・カプラのローカル装着構成を検査する。"""
import copy
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path


PARTS = Path(__file__).resolve().parent / 'parts' / 'plc'


def _catalog(definitions=None):
    if definitions is None:
        items = (json.loads(path.read_text(encoding='utf-8-sig'))
                 for maker in ('keyence', 'omron')
                 for path in (PARTS / maker).rglob('*.json'))
    else:
        if 'kv_io' in definitions or 'unit_diagram' in definitions:
            definitions = {model: spec for category in ('kv_io', 'unit_diagram')
                           for model, spec in definitions.get(category, {}).items()}
        items = []
        for model, value in definitions.items():
            items.append(value if 'definition' in value else
                         {'model': model, 'definition': value,
                          'category': value.get('configuration', {}).get('category', '')})
    result = {}
    for item in items:
        spec = item['definition']
        if spec.get('configuration'):
            model = item['model'].strip().upper()
            result[model] = {'model': model, 'spec': spec,
                             'category': item.get('category', ''),
                             **spec['configuration']}
    return result


def _root(model, catalog):
    if not isinstance(model, str) or model.strip().upper() not in catalog:
        raise ValueError(f'構成の本体形名が不明です: {model}')
    root = catalog[model.strip().upper()]
    if root.get('role') not in ('cpu', 'coupler'):
        raise ValueError(f'{root["model"]}は構成の本体として選択できません')
    return root


def roots(manufacturer=None, definitions=None):
    """CPUとカプラ本体のメニュー。別ステーションへの通信接続は扱わない。"""
    result = []
    for item in _catalog(definitions).values():
        if item.get('role') not in ('cpu', 'coupler'):
            continue
        if manufacturer and item['manufacturer'] != manufacturer:
            continue
        result.append({key: copy.deepcopy(value) for key, value in item.items()
                       if key in ('model', 'manufacturer', 'category', 'spec', 'profile', 'kind', 'role')})
        result[-1]['series'] = copy.deepcopy(item['spec'].get('series', []))
    return sorted(result, key=lambda item: item['model'])


def _option(root, child):
    rule = child.get('compatible', {}).get(root['profile'])
    bus = child.get('bus', '')
    reason = ''
    if child.get('role') != 'module':
        reason = ('接続変換器はバス切替位置へ自動表示します' if child.get('role') == 'adapter'
                  else 'CPU・カプラは別構成の本体として選択してください')
    elif rule is None:
        reason = f'{root["model"]}のローカル装着対象ではありません'
    elif rule.get('blocked'):
        reason = rule['blocked']
    elif bus not in root.get('buses', {}):
        reason = f'{root["model"]}には{bus}バスがありません'
    return {'model': child['model'], 'category': child['category'], 'bus': bus,
            'allowed': not reason, 'reason': reason,
            'conditions': list(dict.fromkeys([*child.get('conditions', []),
                                              *(rule or {}).get('conditions', [])]))}


def options(root_model, definitions=None):
    """同一メーカーの装着候補。未確定・非対応候補は理由付きで返す。"""
    catalog = _catalog(definitions)
    root = _root(root_model, catalog)
    return sorted([_option(root, child) for child in catalog.values()
                   if child.get('manufacturer') == root['manufacturer']
                   and child.get('role') in ('module', 'adapter')], key=lambda item: item['model'])


def _version(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+)*', value.strip()):
        raise ValueError(label + 'は数字と小数点で指定してください')
    # メーカーの機能版は小数表記。11.6と11.60、1.3と1.30を同じ版として扱う。
    parts = [Decimal('0.' + part) if index == 1 else int(part)
             for index, part in enumerate(value.strip().split('.'))]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _minimum(actual, minimum, label, conditions):
    if not minimum:
        return
    conditions.append(f'{label}は{minimum}以上')
    if actual in (None, ''):
        return
    actual_version, minimum_version = _version(actual, label), _version(minimum, label)
    length = max(len(actual_version), len(minimum_version))
    if actual_version + (0,) * (length - len(actual_version)) < minimum_version + (0,) * (length - len(minimum_version)):
        raise ValueError(f'{label} {actual}は必要な{minimum}以上を満たしません')


def _parallel(page, name, count):
    if name not in page:
        return [''] * count
    values = page[name]
    if not isinstance(values, list) or len(values) != count or not all(isinstance(v, str) for v in values):
        raise ValueError(name + 'はmodulesと同じ件数の文字列配列にしてください')
    return values


def resolve(page, definitions=None, complete=True):
    """保存済み構成も検査し、描画に必要な実ユニット・変換器と条件を返す。"""
    if not isinstance(page, dict):
        raise ValueError('PLC構成はオブジェクトで指定してください')
    catalog = _catalog(definitions)
    root = _root(page.get('model'), catalog)
    if page.get('kind') != root['kind']:
        raise ValueError(f'{root["model"]}の構成種別は{root["kind"]}です')
    selected = page.get('modules', [])
    if not isinstance(selected, list) or not all(isinstance(m, str) and m.strip() for m in selected):
        raise ValueError('modulesは空でない形名の文字列配列にしてください')
    tags = _parallel(page, 'module_tags', len(selected))
    buses = _parallel(page, 'module_buses', len(selected))
    versions = _parallel(page, 'module_versions', len(selected))
    modes = _parallel(page, 'module_modes', len(selected))
    for name in ('cpu_version', 'software_version'):
        if page.get(name) not in (None, ''):
            _version(page[name], name)
    for index, version in enumerate(versions):
        if version:
            _version(version, f'装着ユニット{index + 1}の機能版')
    conditions = list(root.get('conditions', []))
    warnings = list(root.get('warnings', []))
    _minimum(page.get('cpu_version'), root.get('min_cpu'), root['model'] + '本体機能版', conditions)
    _minimum(page.get('software_version'), root.get('min_software'), '設定ソフト版', conditions)
    modules, adapters = [], []
    bus_counts, model_counts, group_counts, adapter_counts = Counter(), Counter(), Counter(), Counter()
    current_bus = root.get('native_bus')
    io_supply = root.get('io_supply', False)
    io_points = 0
    previous_rank = -1
    for index, value in enumerate(selected):
        model = value.strip().upper()
        if model not in catalog:
            raise ValueError(f'装着ユニット{index + 1}の形名が不明です: {value}')
        child = catalog[model]
        mode = modes[index]
        if mode and mode not in child['spec'].get('module', {}).get('modes', {}):
            raise ValueError(f'{model}で選択できない通信方式です: {mode}')
        if child.get('role') == 'adapter':
            transition = child.get('from_bus', '') + '>' + child.get('bus', '')
            if (root['profile'] not in child.get('compatible', {})
                    or current_bus != child.get('from_bus')
                    or root.get('transitions', {}).get(transition) != model):
                raise ValueError(f'{model}はこの位置へ接続できません')
            if buses[index] and buses[index] != child['bus']:
                raise ValueError(f'{model}の変換後バスは{child["bus"]}です')
            adapter_counts[model] += 1
            if adapter_counts[model] > root.get('adapter_limit', 1):
                raise ValueError(f'{model}の変換器台数上限を超えています')
            adapters.append({'model': model, 'before_index': index, 'bus': child['bus']})
            current_bus = child['bus']
            continue
        option = _option(root, child)
        if not option['allowed']:
            raise ValueError(f'{model}: {option["reason"]}')
        rule = child['compatible'][root['profile']]
        bus = option['bus']
        if buses[index] and buses[index] != bus:
            raise ValueError(f'{model}の接続先は{bus}バスです（指定: {buses[index]}）')
        bus_counts[bus] += rule.get('slots', child.get('slots', 1))
        model_counts[model] += 1
        limit = rule.get('max_count', child.get('max_count'))
        if limit is not None and model_counts[model] > limit:
            raise ValueError(f'{root["model"]}の{model}は最大{limit}台です')
        group = child.get('count_group')
        if group:
            group_counts[group] += 1
            if group_counts[group] > root.get('group_limits', {}).get(group, float('inf')):
                raise ValueError(f'{group}の装着上限を超えています')
        order = root.get('ordered_buses', [])
        if bus in order:
            rank = order.index(bus)
            if rank < previous_rank:
                raise ValueError('高速バスのユニットは旧型バス/変換器よりCPU側に並べてください')
            previous_rank = rank
        adapter = root.get('adapters', {}).get(bus)
        if adapter and not any(a['model'] == adapter for a in adapters):
            adapters.append({'model': adapter, 'before_index': index, 'bus': bus})
        if current_bus and bus in root.get('transition_buses', []):
            if current_bus != bus:
                adapter = root.get('transitions', {}).get(current_bus + '>' + bus)
                if not adapter:
                    raise ValueError(f'{current_bus}から{bus}へ接続する変換器がありません')
                adapter_counts[adapter] += 1
                if adapter_counts[adapter] > root.get('adapter_limit', 1):
                    raise ValueError(f'{adapter}は1構成につき{root.get("adapter_limit", 1)}台までです')
                adapters.append({'model': adapter, 'before_index': index, 'bus': bus})
            current_bus = bus
        conditions.extend(option['conditions'])
        if child.get('requires_io_supply') and not io_supply:
            message = f'{model}よりCPU側にI/O電源追加供給ユニットを選択してください'
            if complete:
                raise ValueError(message)
            warnings.append(message)
        if child.get('provides_io_supply'):
            io_supply = True
        # デジタルI/O点数は既存の端子定義から数え、機種別の点数表を二重に持たない。
        if bus in root.get('count_buses', []) and child['category'] == 'kv_io':
            io_points += sum(isinstance(row, (list, tuple)) and len(row) > 1
                             and isinstance(row[1], str) and row[1].isdigit()
                             for section in child['spec'].get('pages', [])
                             for half in section.get('halves', []) for row in half)
        _minimum(page.get('cpu_version'), rule.get('min_cpu'), root['model'] + '本体機能版', conditions)
        _minimum(versions[index], rule.get('min_unit'), model + 'ユニット機能版', conditions)
        _minimum(page.get('software_version'), rule.get('min_software'), '設定ソフト版', conditions)
        for version_rule in rule.get('version_rules', []):
            if (versions[index] and _version(versions[index], model)
                    >= _version(version_rule['unit_at_least'], model)
                    and (not version_rule.get('unit_below') or _version(versions[index], model)
                         < _version(version_rule['unit_below'], model))):
                _minimum(page.get('cpu_version'), version_rule.get('min_cpu'),
                         root['model'] + '本体機能版', conditions)
                _minimum(page.get('software_version'), version_rule.get('min_software'),
                         '設定ソフト版', conditions)
                if version_rule.get('max_cpu'):
                    maximum = version_rule['max_cpu']
                    conditions.append(f'{model}の指定ユニット版の確認範囲は本体機能版{maximum}まで')
                    actual = page.get('cpu_version')
                    if actual and _version(actual, '本体機能版') > _version(maximum, '本体機能版'):
                        raise ValueError(f'{model}ユニット版{versions[index]}のCPU対応表は{maximum}までです。'
                                         '指定CPU版との組合せは確認範囲外です')
        modules.append({'index': index, 'model': model, 'tag': tags[index].strip(), 'bus': bus,
                        'category': child['category'], 'spec': child['spec']})
    for bus, limit in root.get('buses', {}).items():
        if bus_counts[bus] > limit:
            raise ValueError(f'{root["model"]}の{bus}バスは最大{limit}台/スロットです（選択{bus_counts[bus]}）')
    for bus, count in root.get('required_buses', {}).items():
        if bus_counts[bus] != count:
            message = f'{root["model"]}には{bus}バスの電源ユニットを{count}台選択してください'
            if complete:
                raise ValueError(message)
            warnings.append(message)
    total = sum(bus_counts[bus] for bus in root.get('count_buses', []))
    if root.get('max_modules') is not None and total > root['max_modules']:
        raise ValueError(f'{root["model"]}の拡張ユニットは合計{root["max_modules"]}台/スロットまでです')
    if root.get('unsegmented_limit') is not None and total > root['unsegmented_limit']:
        message = (f'{root["model"]}の機器全体上限は{root["max_modules"]}台ですが、'
                   f'{root["unsegmented_limit"] + 1}台以上には増設段の指定が必要です。'
                   f'現在の構成画面では{root["unsegmented_limit"]}台まで生成できます')
        if complete:
            raise ValueError(message)
        warnings.append(message)
    if root.get('max_io') is not None and io_points > root['max_io']:
        raise ValueError(f'{root["model"]}の追加デジタルI/Oは{root["max_io"]}点までです（選択{io_points}点）')
    end_cover = root.get('end_cover', '')
    if root.get('end_on_bus') and not bus_counts[root['end_on_bus']]:
        end_cover = ''
    return {'root': {**{key: root[key] for key in ('model', 'spec', 'category', 'profile', 'manufacturer', 'kind')},
                     'tag': str(page.get('tag', '')).strip()},
            'modules': modules, 'adapters': adapters, 'end_cover': end_cover,
            'conditions': list(dict.fromkeys(conditions)), 'warnings': list(dict.fromkeys(warnings))}


def validate(page, definitions=None, complete=True):
    """不正構成はValueError。正常時は明示された接続・版・給電条件を返す。"""
    return resolve(page, definitions, complete=complete)['conditions']
