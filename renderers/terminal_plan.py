"""明示登録された外部端子台の接続だけを、編集可能な一覧図へまとめる。"""
from project_wiring.data import normalize, terminal_rows

from .wiring import _width


COLUMNS = [('タグ名', 90), ('端子台', 90), ('端子段', 65), ('端子番号', 75),
           ('機器端子', 100), ('線番', 95), ('用途', 160), ('相手先', 250),
           ('ケーブル / 芯線', 265)]
LEFT, TOP, HEADER_HEIGHT, BOTTOM = 40, 60, 30, 790
LINE_HEIGHT = 16


def _wrap(value, width):
    lines = []
    for paragraph in str(value).split('\n'):
        line, used = '', 0
        for char in paragraph:
            size = _width(char)
            if line and used + size > width:
                lines.append(line)
                line, used = '', 0
            line += char
            used += size
        lines.append(line)
    return lines


def _cells(row):
    peer = ':'.join(row[key] for key in ('相手機器', '相手端子') if row[key].strip())
    peer = '\n'.join(value for value in (peer, row['送り先']) if value.strip())
    cable = ' / '.join(row[key] for key in ('ケーブル番号', '芯番号') if row[key].strip())
    cable = '\n'.join([cable] + [caption + ' ' + row[key] for key, caption in
                                (('線径', '線径'), ('シールド', 'シールド'), ('渡り', '渡り'))
                                if row[key].strip()]).strip()
    return [row[key] for key in ('タグ名', '端子台', '端子段', '端子番号', '機器端子', '線番', '用途')] + [peer, cable]


def build_pages(pages_rows, symbols, Page, table, heading):
    """terminal_plan指定ページの登録端子だけを表にし、行を分断せずページ分割する。"""
    selected = [(page, rows) for page, rows in pages_rows
                if normalize(page.get('wiring'))['terminal_plan']]
    records = terminal_rows(selected)
    chunks, chunk, used = [], [], 0
    available = BOTTOM - TOP - HEADER_HEIGHT
    for row in records:
        cells = [_wrap(value, width - 20) for value, (_, width) in zip(_cells(row), COLUMNS)]
        height = max(30, max(map(len, cells)) * LINE_HEIGHT + 12)
        if height > available:
            raise ValueError(f"端子台 {row['端子台']} {row['端子段']} {row['端子番号']}: 接続図の1行が1ページに収まりません。文字量を減らしてください")
        if chunk and used + height > available:
            chunks.append(chunk)
            chunk, used = [], 0
        chunk.append((cells, height))
        used += height
    if chunk:
        chunks.append(chunk)

    result = []
    for index, rows in enumerate(chunks, 1):
        title = '端子台接続図' + (f' {index}/{len(chunks)}' if len(chunks) > 1 else '')
        page = Page(symbols)
        heading(page, title, x=LEFT)
        table(page, LEFT, TOP, COLUMNS, [], head_size=8)
        y = TOP + HEADER_HEIGHT
        for cells, height in rows:
            x = LEFT
            for (_, width), lines in zip(COLUMNS, cells):
                page.line(x, y, x, y + height, width=0.8)
                for line_index, text in enumerate(lines):
                    page.text(x + 6, y + (height - len(lines) * LINE_HEIGHT) / 2 + line_index * LINE_HEIGHT, text, 8)
                x += width
            page.line(x, y, x, y + height, width=0.8)
            y += height
            page.line(LEFT, y, x, y, width=0.8)
        result.append((title, page))
    return result
