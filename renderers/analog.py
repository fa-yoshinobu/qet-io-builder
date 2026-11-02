"""アナログの信号端子と、配線しない実在端子の共通表示行。"""
import copy


def nc_rows(spec):
    """機種別のNC定義を統合する。電源コネクタのNCは本体図で表示する。"""
    scopes = {item['name']: index + 1 for index, item in enumerate(spec.get('channel_connectors', []))}
    scopes.update({label: index + 1 for index, label in enumerate(spec.get('channel_labels', []))})
    records = list(spec.get('unconnected_ports', []))
    for item in spec.get('unused_pins', []):
        connector = item.get('connector', '')
        if spec.get('channel_connectors'):
            if connector not in scopes:
                continue
            item = dict(item, channel=scopes[connector])
        records.append(item)
    rows, seen = [], set()
    for item in records:
        identity = (item.get('connector', ''), str(item.get('pin', '')), item.get('channel'), item.get('channel_position'))
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(dict(item, signal='NC', pin=str(item.get('pin', '')),
                         description='接続しない', connectable=False))
    return rows


def channel_rows(spec, index):
    """CHごとの信号行に、確認済みのNC行を実在位置で挿入する。"""
    direction = spec['channels'][index]
    templates = (spec['terminals_by_channel'][index] if spec.get('terminals_by_channel') else
                 spec.get('terminals_by_direction', {}).get(direction, spec['terminals']))
    pins = spec.get('pins_by_channel')
    rows = [dict(signal=template.format(n=index + 1), template=template,
                 pin=str(pins[index][position]) if pins else '', connectable=True)
            for position, template in enumerate(templates)]
    records = [item for item in nc_rows(spec) if item.get('channel') == index + 1]
    for item in sorted(records, key=lambda row: row.get('channel_position', len(rows))):
        rows.insert(item.get('channel_position', len(rows)), item)
    return rows


def extra_rows(spec):
    return list(spec.get('auxiliary_terminals', [])) + [item for item in nc_rows(spec) if not item.get('channel')]


def readonly_symbol(symbols, key):
    name = key + '_readonly'
    if name not in symbols:
        symbol = copy.deepcopy(symbols[key])
        symbol.name = name
        symbol.terminals = {}
        symbol.parts = [(tag, attrs) for tag, attrs in symbol.parts
                        if not (tag == 'line' and attrs.get('x1') == 0 and attrs.get('x2') == 4)]
        symbols[name] = symbol
    return name
