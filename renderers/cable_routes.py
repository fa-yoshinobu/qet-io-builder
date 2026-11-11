"""I/O図と別紙の端子台図を、実際のケーブルとコネクタ単位で対応付ける。"""

from . import keyence, terminal_blocks


def select_cable(spec, model, cable):
    for choice in spec['compatible']:
        if model in choice['models'] and cable == choice['cable']:
            return choice
    raise ValueError('このPLC・中継端子台に対応するケーブルを選んでください')


def check_page(pg, spec):
    from renderers.typography import text_w

    choice = select_cable(spec, pg.get('plc_model'), pg.get('cable'))
    fields = {'plc_tag': 'PLC側タグ', 'tag': '端子台タグ', 'cable_tag': 'ケーブル番号'}
    if choice.get('ports') or choice.get('branches'):
        fields['tag2'] = '2台目の端子台タグ'
    if choice.get('ports'):
        fields['cable_tag2'] = '2本目のケーブル番号'
        select_cable(spec, pg['plc_model'], pg.get('cable2', pg['cable']))
    for key, label in fields.items():
        value = pg.get(key)
        if not isinstance(value, str) or not value.strip() or value.splitlines() != [value]:
            raise ValueError(label + 'を1行で入力してください')
        if text_w(value, 9) > 360:
            raise ValueError(label + 'が図面の接続表示に収まる長さにしてください')
    tags = [pg[key].strip() for key in ('plc_tag', 'tag', 'tag2') if key in fields]
    if len(set(tags)) != len(tags):
        raise ValueError('PLC側と各端子台には別々のタグを指定してください')
    if choice.get('ports') and pg['cable_tag'].strip() == pg['cable_tag2'].strip():
        raise ValueError('L側とH側でケーブル番号が重複しています')
    if 'start' in pg:
        value = str(pg['start'])
        if not value or any(ch not in '0123456789ABCDEFabcdef' for ch in value):
            raise ValueError('先頭XYは0以上の16進数で入力してください')
    return choice


def circuits(pg, spec, choice):
    """1本のケーブルにつき、使用するPLC口と端子台を列挙する。"""
    ports = choice.get('ports', [''])
    for i, port in enumerate(ports):
        part = pg
        selected = choice
        if i:
            part = dict(pg, tag=pg['tag2'], cable_tag=pg['cable_tag2'], cable=pg.get('cable2', pg['cable']))
            selected = select_cable(spec, pg['plc_model'], part['cable'])
        block = spec
        if selected.get('pin_numbering') == 'sequential_banks':
            # KV-CのPLC側は片列1～17・他列18～34。MILのピン番号は奇偶交互。
            def plc_pin(pin):
                n = int(pin)
                return str((n + 1) // 2 if n % 2 else 17 + n // 2)
            block = dict(spec, connections=[dict(row, pins=[plc_pin(p) for p in row['pins']])
                                            for row in spec['connections']])
        if selected.get('unused_terminals'):
            unused = selected['unused_terminals']
            block = dict(block, connections=[dict(row, connectable=False) if row['terminal'] in unused else row
                                             for row in block['connections']])
        if selected.get('notes'):
            block = dict(block, notes=[*block.get('notes', []), *selected['notes']])
        targets = [(part['tag'], None)]
        if selected.get('branches'):
            targets = list(zip((pg['tag'], pg['tag2']), selected['branches'], strict=True))
        yield part, port, selected, block, targets


def plc_definition(pg, port):
    from unit_catalog import KV_IO, UNIT_DIAGRAMS, io_unit
    from . import cable_io

    model = pg['plc_model']
    io_pg = dict(pg, model=model, tag=pg['plc_tag'], cable_layout=True)
    if model in KV_IO:
        spec = KV_IO[model]
        if port:
            spec = dict(spec, pages=[next(s for s in spec['pages'] if s['section'] == port)])
        signals = {p: signal for s in spec['pages'] for half in s['halves'] for p, signal in half}
        return io_pg, spec, signals, keyence.build_pages
    spec = UNIT_DIAGRAMS[model] if model in UNIT_DIAGRAMS else io_unit(model)
    return io_pg, spec, cable_io.plc_signals(io_pg, spec), cable_io.build_pages


def build_sheets(pg, spec, choice, symbols, cable_ids):
    sheets, references = [], []
    for part, port, cable, block, targets in circuits(pg, spec, choice):
        number = part['cable_tag'].strip()
        if number in cable_ids:
            raise ValueError(f'中継端子台のケーブル番号が重複しています: {number}')
        cable_ids.add(number)
        io_pg, unit, _, renderer = plc_definition(part, port)
        io = renderer(io_pg, unit, symbols)
        sheets.extend(io)
        ends = []
        for tag, branch in targets:
            location = branch['connector'] if branch else ''
            block_pg = dict(part, tag=tag, branch=branch)
            diagrams = terminal_blocks.build_pages(block_pg, block, symbols)
            if port or location:
                diagrams = [(f'{title} {tag} {location or port}', sheet) for title, sheet in diagrams]
            sheets.extend(diagrams)
            ends.append((tag, location, diagrams))
        references.append((part, port, cable, block, io, ends))
    return sheets, references


def label_sheets(reference, nums):
    from renderers.typography import text_w

    pg, port, cable, block, io, ends = reference
    source = f"{pg['plc_tag']}（{pg['plc_model']}）{port or 'I/Oコネクタ'}"
    if len(ends) > 1:
        source += "（CN1）"
    cable_name = f"{pg['cable_tag']}  {cable['cable_manufacturer']}  {cable['cable']}"
    def page_refs(sheets):
        return '・'.join(str(nums[id(sheet)]) for _, sheet in sheets)
    def line(sheet, y, value, bold=False):
        size = 9 if text_w(value, 9) <= 1190 else 8
        if text_w(value, size) > 1190:
            raise ValueError('接続先の表示が長いため、端子台またはPLCのタグを短くしてください')
        sheet.text(30, y, value, size, bold)
    peers = []
    for tag, location, sheets in ends:
        endpoint = f"{tag}（{block['model']}）コネクタ"
        if location:
            endpoint = f"{location} → {endpoint}"
        for _, sheet in sheets:
            line(sheet, 773, f"ケーブル  {cable_name}     相手図  p.{page_refs(io)}", True)
            line(sheet, 793, f"{source}  ↔  {endpoint}")
        peers.append((endpoint, page_refs(sheets)))
    for _, sheet in io:
        if len(peers) == 1:
            target, pages = peers[0]
            line(sheet, 773, f"ケーブル  {cable_name}     相手図  p.{pages}", True)
            line(sheet, 793, f"{source}  ↔  {target}")
        else:
            line(sheet, 773, f"ケーブル  {cable_name}     {source}", True)
            line(sheet, 793, '     ／     '.join(f'{target}  相手図 p.{pages}' for target, pages in peers))


def iolist_rows(pg, spec, choice):
    for part, port, _, block, targets in circuits(pg, spec, choice):
        _, _, signals, _ = plc_definition(part, port)
        for tag, branch in targets:
            if branch:
                endpoints = ((pin, f"{tag} {branch['connector']} MIL {mil}")
                             for pin, mil in terminal_blocks.relay_branch_pins(block, branch))
            else:
                endpoints = ((pin, f"{tag} {row['bank']} {row['terminal']}")
                             for row in block['connections'] if row.get('connectable', True) for pin in row['pins']
                             if signals[pin] != 'NC')
            for pin, endpoint in endpoints:
                yield [part['plc_tag'], signals[pin], '', '', ' '.join(filter(None, (port, pin))), endpoint, '']
