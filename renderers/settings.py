"""機種別の通信・機器設定欄。非表示でもプロジェクトの値は保持する。"""
from functools import lru_cache
from pathlib import Path
import tomllib

SETTINGS_BOTTOM = 790
ROW_H = 30
UNIT_BOX_W = 310
LABELS = {'station': '局番・ネットワーク番号', 'ip': 'IP設定',
          'communication': '通信設定', 'dip': '機器設定'}
DRAW_LABELS = dict(LABELS, station='局番・NW No.')


@lru_cache(maxsize=1)
def profiles():
    path = Path(__file__).resolve().parents[1] / 'parts' / 'settings_fields.toml'
    with path.open('rb') as stream:
        groups = tomllib.load(stream)['groups']
    result = {}
    for group in groups:
        if not set(group['default']) <= set(group['available']) <= LABELS.keys():
            raise ValueError('設定欄の定義が不正です')
        for model in group['models']:
            if model in result:
                raise ValueError('設定欄の形名が重複しています: ' + model)
            result[model] = group
    return result


def profile(model):
    return profiles().get(str(model).upper(), {'default': [], 'available': []})


def controls(page):
    """左右の機種を別々に判定し、任意欄も表示チェックの候補として返す。"""
    kind = page.get('kind')
    if kind in ('qcomm', 'iqrcomm', 'fxcomm', 'gotoption'):
        sides = [('left_', page.get('left_model')), ('right_', page.get('right_model'))]
    elif kind in ('qbody', 'iqrbody', 'fx5body', 'gotbody', 'remotebody', 'mxbody', 'inverter'):
        sides = [('', page.get('model'))]
    else:
        return []
    visibility = page.get('settings_visibility', {})
    if not isinstance(visibility, dict) or any(type(v) is not bool for v in visibility.values()):
        raise ValueError('settings_visibilityは設定キーとtrue/falseの組で指定してください')
    result = []
    for prefix, model in sides:
        rule = profile(model)
        for key in rule['available']:
            field = prefix + key
            label = ('左側 ' if prefix == 'left_' else '右側 ' if prefix else '') + LABELS[key]
            result.append({'key': field, 'label': label,
                           'visible': visibility.get(field, key in rule['default'])})
    return result


def fields(*, model, values, prefix=''):
    page = dict(values)
    page.update(kind='qcomm' if prefix else 'gotbody')
    page[(prefix + '_model') if prefix else 'model'] = model
    stem = prefix + '_' if prefix else ''
    return [(DRAW_LABELS[c['key'].removeprefix(stem)], c['key'].removeprefix(stem))
            for c in controls(page) if c['visible'] and (not prefix or c['key'].startswith(stem))]


def values(page, prefix=''):
    return {key: page.get((prefix + '_' if prefix else '') + key, '') for key in LABELS}


def draw(p, rows, values, x0=30, x1=260, bottom=SETTINGS_BOTTOM):
    from .communication import wrap
    entries = [(label, wrap(values.get(key, '') or '（記入）', x1 - x0 - 120, 8)) for label, key in rows]
    heights = [max(ROW_H, 14 + len(lines) * 12) for _, lines in entries]
    y = bottom - sum(heights)
    for (label, lines), height in zip(entries, heights):
        p.rect(x0, y, x1, y + height, dash=False, width=0.5)
        p.text(x0 + 7, y + 8, label, 8, True)
        for index, line in enumerate(lines):
            p.text(x0 + 112, y + 8 + index * 12, line, 8)
        y += height
