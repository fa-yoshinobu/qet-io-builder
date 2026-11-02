"""任意の配線注記と端子台接続表に使う共通データ。接続先は推測しない。"""
import csv
import io
import os
import re
import tempfile
from pathlib import Path


BOUNDARY_DEFAULTS = {'part': 1, 'x': 240, 'top': 75, 'bottom': 750,
                     'left': '盤外', 'right': '盤内'}
CONNECTION_DEFAULTS = dict.fromkeys((
    'unit_tag', 'unit_terminal', 'terminal_block', 'level', 'terminal', 'wire', 'cable', 'core',
    'section', 'shield', 'peer_tag', 'peer_terminal', 'destination', 'purpose',
    'jumper', 'reference', 'link_id'), '')
CONNECTION_DEFAULTS.update(part=1, x=95, y=110)
# 画面の入力欄(キー, 表示名)。tkinter版・Web版で共用する
CONTENT_FIELDS = {
    'boundaries': (('left', '左側の表記'), ('right', '右側の表記')),
    'connections': (('unit_tag', '対象機器タグ'), ('unit_terminal', '端子 / アドレス'),
                    ('terminal_block', '端子台名'), ('terminal', '端子台番号'), ('level', '端子段'),
                    ('wire', '線番'), ('cable', 'ケーブル番号'),
                    ('core', '芯番号 / 色'), ('section', '線径'),
                    ('shield', 'シールド'), ('peer_tag', '相手機器タグ'),
                    ('peer_terminal', '相手端子'), ('destination', '送り先 / 受け元'),
                    ('purpose', '用途'), ('jumper', '渡り線'),
                    ('reference', '送り / 受け'), ('link_id', '参照ID')),
}
POSITION_FIELDS = {
    'boundaries': (('part', '分割頁（1から）'), ('x', '横位置 x'), ('top', '上端 y'), ('bottom', '下端 y')),
    'connections': (('part', '分割頁（1から）'), ('x', '横位置 x'), ('y', '縦位置 y')),
}
CSV_COLUMNS = ('ユニット', 'タグ名', '分割頁', '端子台', '端子段', '端子番号', '機器端子', '線番',
               '用途', '相手機器', '相手端子', '送り先', 'ケーブル番号', '芯番号',
               '線径', 'シールド', '渡り')


def normalize(value):
    """指定をコピーし、既定値と入力検査を適用する。Noneは未指定として扱う。"""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError('配線設定（wiring）はオブジェクトにしてください')
    unknown = set(value) - {'boundaries', 'connections', 'terminal_plan'}
    if unknown:
        raise ValueError('配線設定に不明な項目があります: ' + ', '.join(sorted(map(str, unknown))))
    terminal_plan = value.get('terminal_plan', False)
    if not isinstance(terminal_plan, bool):
        raise ValueError('端子台接続図の追加（terminal_plan）はtrueまたはfalseにしてください')
    result = {'terminal_plan': terminal_plan}
    for name, defaults in (('boundaries', BOUNDARY_DEFAULTS), ('connections', CONNECTION_DEFAULTS)):
        records = value.get(name, [])
        if not isinstance(records, list):
            raise ValueError(f'配線設定の {name} は配列にしてください')
        result[name] = []
        for index, record in enumerate(records, 1):
            context = f'配線設定 {name} の{index}行目'
            if not isinstance(record, dict):
                raise ValueError(f'{context}はオブジェクトにしてください')
            unknown = set(record) - set(defaults)
            if unknown:
                raise ValueError(f'{context}に不明な項目があります: ' + ', '.join(sorted(map(str, unknown))))
            row = {**defaults, **record}
            part = row['part']
            if isinstance(part, bool) or not isinstance(part, int) or part < 1:
                raise ValueError(f'{context}の分割頁（part）は1以上の整数にしてください')
            for key, default in defaults.items():
                if key == 'part':
                    continue
                item = row[key]
                if isinstance(default, str):
                    if not isinstance(item, str):
                        raise ValueError(f'{context}の {key} は文字列にしてください')
                else:
                    limit = 1260 if key == 'x' else 800
                    if isinstance(item, bool) or not isinstance(item, (int, float)) or not 0 <= item <= limit:
                        raise ValueError(f'{context}の {key} は0〜{limit}の有限数にしてください')
            if name == 'boundaries' and row['top'] >= row['bottom']:
                raise ValueError(f'{context}の top は bottom より小さくしてください')
            if name == 'connections' and row['reference'] not in ('', '送り', '受け'):
                raise ValueError(f'{context}の reference は空欄・送り・受けから指定してください')
            result[name].append(row)
    return result


def _natural(value):
    return tuple((1, int(part)) if part.isdecimal() else (0, part.casefold())
                 for part in re.split(r'([0-9]+)', value.strip()))


def page_identity(page):
    """機器が1台に特定できる場合だけ、形名とタグを注記・接続表へ引き継ぐ。"""
    if page.get('model'):
        return page['model'], page.get('tag', '')
    units = [(page.get(side + '_model', ''), page.get(side + '_tag', ''))
             for side in ('left', 'right') if page.get(side + '_model')]
    return units[0] if len(units) == 1 else ('', '')


def terminal_rows(pages_rows):
    """明示した端子台名と端子番号が揃う接続を抽出する。同じ番号の別登録も保持する。"""
    rows = []
    for page, _ in pages_rows:
        model, tag = page_identity(page)
        for connection in normalize(page.get('wiring'))['connections']:
            if not connection['terminal_block'].strip() or not connection['terminal'].strip():
                continue
            values = [model, connection['unit_tag'] if connection['unit_tag'].strip() else tag,
                      str(connection['part'])]
            values += [connection[key] for key in ('terminal_block', 'level', 'terminal', 'unit_terminal', 'wire', 'purpose',
                                                  'peer_tag', 'peer_terminal', 'destination', 'cable', 'core',
                                                  'section', 'shield', 'jumper')]
            rows.append(dict(zip(CSV_COLUMNS, values)))
    return sorted(rows, key=lambda row: (_natural(row['端子台']), _natural(row['端子段']), _natural(row['端子番号'])))


def write_terminal_csv(path, rows):
    """Excelで読めるUTF-8 BOM付きCSVを、書込み成功後に置き換える。"""
    text = io.StringIO(newline='')
    writer = csv.DictWriter(text, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    content = text.getvalue().encode('utf-8-sig')
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
