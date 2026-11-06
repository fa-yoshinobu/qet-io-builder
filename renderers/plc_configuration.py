"""ベースを持たないPLC・カプラの装着構成。電気配線は単体図へ分ける。"""

CARD_WIDTH = 240
CARD_HEIGHT = 118
ROW_PITCH = 166
CARDS_PER_ROW = 5
ROWS_PER_PAGE = 3
NOTE_LINES_PER_PAGE = 14


def _items(configuration, page):
    """同じバス内は入力順の左→右。前面装着品は横のバスから分離する。"""
    root = configuration['root']
    groups = {bus: [] for bus in ('power', 'left', 'x', 'front', 'direct', 'legacy', 'nx')}
    entries = [dict(adapter, role='接続変換器', unit_no='', tag='', index=adapter['before_index'])
               for adapter in configuration.get('adapters', [])]
    for module in configuration['modules']:
        spec = module.get('spec', {})
        function = spec.get('function', '')
        if not function and module.get('category') == 'kv_io':
            directions = {direction for part in spec.get('pages', []) for direction in part.get('directions', [])}
            function = ('入出力ユニット' if {'input', 'output'} <= directions else
                        '出力ユニット' if spec.get('output') else '入力ユニット')
        entries.append(dict(module, role=function or '拡張ユニット', unit_no=str(module['index'] + 1)))
    for item in sorted(entries, key=lambda item: item['index']):
        groups.setdefault(item['bus'], []).append(item)
    role = root.get('spec', {}).get('function') or '本体'
    body = dict(root, role=role, bus='body', unit_no=str(page.get('unit_no', '')),
                tag=str(page.get('tag', '')))
    main = [*groups['power'], *groups['left'], *groups['x'], body]
    for bus in ('direct', 'legacy', 'nx'):
        main.extend(groups[bus])
    if configuration.get('end_cover'):
        main.append(dict(model=configuration['end_cover'], role='エンドカバー', bus='end',
                         unit_no='', tag=''))
    # 新しいバスを黙って落とさず、接続判定と描画の契約不一致を知らせる。
    known = {'power', 'left', 'x', 'front', 'direct', 'legacy', 'nx'}
    if any(items for bus, items in groups.items() if bus not in known):
        raise ValueError('構成図が対応していない接続バスです')
    return [main, groups['front']]


def _bus_label(item):
    bus = item['bus']
    return {
        'body': '本体', 'power': '本体左側 電源', 'left': '本体左側 装着',
        'x': 'CPU左側 Xバス', 'nx': '本体右側 NXバス',
        'direct': '本体右側 直接装着', 'legacy': '本体右側 変換後の拡張',
        'front': 'CPU前面 装着', 'end': '右端',
    }[bus]


def _card(page, item, x, top):
    from gen_io_page import unit_identity_header
    from .communication import wrap
    unit_identity_header(page, item, x, CARD_WIDTH, top, top + 18)
    bottom = top + CARD_HEIGHT
    page.rect(x, top + 18, x + CARD_WIDTH, bottom, dash=False, width=1)
    page.text(x + 10, top + 28, _bus_label(item), 8, True)
    lines = wrap(item['role'], CARD_WIDTH - 24, 9)
    if 53 + len(lines) * 16 > CARD_HEIGHT - 8:
        raise ValueError(item['model'] + 'の機能名が構成欄に収まりません')
    for index, line in enumerate(lines):
        page.text(x + 10, top + 53 + index * 16, line, 9, True)


def build_pages(pg, symbols):
    """接続判定済みの物理順を保持し、長い列を番号付きで継続する。"""
    import math
    import plc_configuration
    from gen_io_page import Page, KV_IO, UNIT_DIAGRAMS
    from .communication import draw_notes, wrap
    configuration = plc_configuration.resolve(pg, {'kv_io': KV_IO, 'unit_diagram': UNIT_DIAGRAMS})
    chains = _items(configuration, pg)
    rows = []
    for chain_index, chain in enumerate(chains):
        chunks = [chain[start:start + CARDS_PER_ROW] for start in range(0, len(chain), CARDS_PER_ROW)]
        for index, chunk in enumerate(chunks):
            rows.append((chunk, chain_index, index + 1, len(chunks)))
    common = [
        '構成の横幅は実寸ではありません。同じバス内は左から右の順です。番号・タグは各ユニット詳細図と対応します。',
    ]
    if chains[1]:
        common.append('CPU前面の装着品は、左右の拡張バスと別の列に示します。')
    notes = list(dict.fromkeys([*configuration.get('conditions', []), *configuration.get('warnings', [])]))
    lines = [line for note in notes for line in wrap(note, 1176, 8)]
    note_chunks = [lines[start:start + NOTE_LINES_PER_PAGE] for start in range(0, len(lines), NOTE_LINES_PER_PAGE)]
    count = max(1, math.ceil(len(rows) / ROWS_PER_PAGE), len(note_chunks))
    result = []
    for index in range(count):
        page = Page(symbols)
        notes_on_page = common + (note_chunks[index] if index < len(note_chunks) else [])
        footer_top = draw_notes(page, 30, 1200, notes_on_page)
        for local_index, (items, chain, part, total) in enumerate(rows[index * ROWS_PER_PAGE:(index + 1) * ROWS_PER_PAGE]):
            top = 34 + local_index * ROW_PITCH
            if top + CARD_HEIGHT + 24 > footer_top - 8:
                raise ValueError('構成条件の注記が構成図と重なります')
            for column, item in enumerate(items):
                _card(page, item, 30 + column * CARD_WIDTH, top)
            label = '前面装着' if chain else '左右の装着列'
            continuation = f'{label} {part}/{total}'
            if part > 1:
                continuation += '（前の列から続く）'
            if part < total:
                continuation += ' → 次の列へ続く'
            page.text(40, top + CARD_HEIGHT + 8, continuation, 8)
        if index * ROWS_PER_PAGE >= len(rows):
            page.text(40, 34, '装着構成の適用条件（続き）', 10, True)
        title = str(pg.get('title') or configuration['root']['model'] + ' 装着構成')
        if count > 1:
            title += f' ({index + 1}/{count})'
        result.append((title, page))
    return result
