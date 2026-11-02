"""明示された境界・配線情報だけを既存図面に追加する。"""
import copy
import math
import re
from collections import defaultdict
from xml.etree import ElementTree as ET

from . import standard


NOTE_WIDTH = 170
LINE_HEIGHT = 16
PAGE_RIGHT, PAGE_BOTTOM = 1260, 820
FONT = 'MS Gothic,8,-1,5,50,0,0,0,0,0'
REPORTS = {
    '送り': ('wiring_send', '10_electric/10_allpole/100_folio_referencing/02going_arrow.elmt'),
    '受け': ('wiring_receive', '10_electric/10_allpole/100_folio_referencing/01coming_arrow.elmt'),
}


def _width(text):
    half = math.ceil(8 * 96 / 72 / 2)
    return sum(half if ord(char) < 0x2000 or 0xFF61 <= ord(char) <= 0xFF9F else half * 2
               for char in text)


def _wrap(text):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for token in re.findall(r'→|[^\s→]+|\s+', paragraph):
            if _width(token) > NOTE_WIDTH:
                for char in token:
                    if line and _width(line + char) > NOTE_WIDTH:
                        lines.append(line)
                        line = ''
                    line += char
                continue
            if line and _width(line + token) > NOTE_WIDTH:
                lines.append(line)
                line = ''
            line += token
        lines.append(line)
    return lines


def _inside(x, y, width, height, context):
    if x < 0 or y < 0 or x + width > PAGE_RIGHT or y + height > PAGE_BOTTOM:
        raise ValueError(f'{context}: 配線注記・境界ラベルが図枠外に出ます。位置または文字量を変更してください')


def _port(tag, terminal):
    return ':'.join(value.strip() for value in (tag, terminal) if value.strip())


def _connection_lines(row):
    identity = []
    terminal = _port(row['terminal_block'], row['terminal'])
    if row.get('level', '').strip():
        terminal += ' (' + row['level'].strip() + ')'
    if terminal:
        identity.append(terminal)
    if row['wire'].strip():
        identity.append('線 ' + row['wire'].strip())
    cable = row['cable'].strip()
    if row['core'].strip():
        cable += ('/' if cable else '') + '芯' + row['core'].strip()
    if cable:
        identity.append(cable)
    lines = ['  '.join(identity)] if identity else []
    unit = _port(row['unit_tag'], row['unit_terminal'])
    peer = _port(row['peer_tag'], row['peer_terminal'])
    if unit or peer:
        lines.append(' → '.join(value for value in (unit, peer) if value))
    if row['destination'].strip():
        lines.append('送り先 ' + row['destination'].strip())
    details = [caption + ' ' + row[field].strip() for field, caption in
               (('section', '線径'), ('shield', 'シールド'), ('purpose', '用途'), ('jumper', '渡り'))
               if row[field].strip()]
    if details:
        lines.append(' / '.join(details))
    return [line for text in lines for line in _wrap(text)]


def _note(page, lines, x, y, Symbol):
    if not lines:
        return
    key = 'wiring_note'
    if key not in page.sym:
        symbol = Symbol(key, '配線情報（任意入力）', NOTE_WIDTH + 8, 24, 4, 4)
        symbol.dynamic('label', -4, -4, 8)
        page.sym[key] = symbol
    page.place(key, x, y, label='\n'.join(lines),
               texts=[('label', -4, -4, 8, False, NOTE_WIDTH + 8)])


class _ImportedReport:
    def __init__(self, name, definition):
        self.name, self.definition = name, definition
        self.width, self.height = int(definition.get('width')), int(definition.get('height'))
        self.hx, self.hy = int(definition.get('hotspot_x')), int(definition.get('hotspot_y'))
        self.link_type = definition.get('link_type')
        self.terminals = {str(index): (item.get('uuid'), item.get('orientation'),
                                      float(item.get('x')), float(item.get('y')))
                          for index, item in enumerate(definition.findall('./description/terminal'))}

    def to_xml(self):
        element = ET.Element('element', name=self.name + '.elmt')
        element.append(copy.deepcopy(self.definition))
        return element


def _report_symbol(page, reference):
    name, source = REPORTS[reference]
    if name not in page.sym:
        definition = ET.parse(standard.collection_root() / source).getroot()
        infos = definition.find('elementInformations')
        if infos is None:
            infos = ET.SubElement(definition, 'elementInformations')
        ET.SubElement(infos, 'elementInformation', name='qet_io_standard_source', show='0').text = source
        for text in definition.findall('./description/dynamic_text'):
            text.set('font', FONT)
            text.set('x', '6')
            text.set('y', '-11.5')
            text.set('text_width', str(NOTE_WIDTH - 19))
            text.set('Halignment', 'AlignLeft')
        page.sym[name] = _ImportedReport(name, definition)
    return name


def apply(page, wiring, part, Symbol, context=''):
    """正規化済み設定の1始まり分割頁を追加し、送り・受けの参照情報を返す。"""
    references = []
    for index, row in enumerate(wiring['boundaries'], 1):
        if row['part'] != part:
            continue
        where = f'{context} 境界{index}'.strip()
        x, top, bottom = row['x'], row['top'], row['bottom']
        labels = [_wrap(row[side]) if row[side].strip() else [] for side in ('left', 'right')]
        height = max((len(lines) * LINE_HEIGHT for lines in labels), default=0)
        positions = [(x - max((_width(line) for line in labels[0]), default=0) - 8, labels[0]),
                     (x + 8, labels[1])]
        _inside(x, top, 0, bottom - top, where)
        for lx, lines in positions:
            if lines:
                _inside(lx, top - height - 4, max(map(_width, lines)), height, where)
        page.line(x, top, x, bottom, width=0.5, dash=True)
        for lx, lines in positions:
            if lines:
                page.text(lx, top - height - 4, '\n'.join(lines), 8)

    for index, row in enumerate(wiring['connections'], 1):
        if row['part'] != part:
            continue
        where = f'{context} 接続{index}'.strip()
        reference, link_id = row['reference'], row['link_id'].strip()
        if bool(reference) != bool(link_id):
            raise ValueError(f'{where}: 送り・受けとlink_idは両方指定してください')
        x, y = row['x'], row['y']
        lines = _connection_lines(row)
        caption_height = 32 if reference else 0
        height = caption_height + len(lines) * LINE_HEIGHT
        if lines or reference:
            _inside(x, y, NOTE_WIDTH, height, where)
            for px, py, width, previous_height, previous in getattr(page, 'wiring_note_boxes', []):
                if x < px + width and px < x + NOTE_WIDTH and y < py + previous_height and py < y + height:
                    raise ValueError(f'{where}: 配線注記が {previous} と重なります。x・yの位置を調整してください')
        if reference:
            key = _report_symbol(page, reference)
            page.place(key, x + 13, y + 12,
                       texts=[('label', 6, -11.5, 8, False, NOTE_WIDTH - 19)])
            references.append(dict(page=page, element=page.elements[-1], reference=reference,
                                   link_id=link_id, context=where))
        _note(page, lines, x, y + caption_height, Symbol)
        if lines or reference:
            if not hasattr(page, 'wiring_note_boxes'):
                page.wiring_note_boxes = []
            page.wiring_note_boxes.append((x, y, NOTE_WIDTH, height, where))
    return references


def link_references(references):
    """同じIDの送り・受けを別ページの1対として検証してからQET標準リンクを付ける。"""
    groups = defaultdict(list)
    for item in references:
        groups[item['link_id']].append(item)
    for link_id, pair in groups.items():
        where = pair[0]['context']
        if len(pair) != 2:
            raise ValueError(f'{where}: link_id {link_id} は送り・受けの2個で指定してください（{len(pair)}個）')
        if {item['reference'] for item in pair} != {'送り', '受け'}:
            raise ValueError(f'{where}: link_id {link_id} は送りと受けを1個ずつ指定してください')
        if pair[0]['page'] is pair[1]['page']:
            raise ValueError(f'{where}: link_id {link_id} の送り・受けは別ページに置いてください')
    for pair in groups.values():
        for source, target in (pair, pair[::-1]):
            links = source['element'].find('links_uuids')
            if links is None:
                links = ET.SubElement(source['element'], 'links_uuids')
            target_uuid = target['element'].get('uuid')
            if not any(item.get('uuid') == target_uuid for item in links.findall('link_uuid')):
                ET.SubElement(links, 'link_uuid', uuid=target_uuid)
    return len(groups)
