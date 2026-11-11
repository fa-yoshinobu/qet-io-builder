"""箱型機器の外枠・給電レーン・設定欄の共通配置。"""
from . import settings


class PowerRails(dict):
    """給電を配線した極だけを描く。別ページの端子から空レーンを作らない。"""
    def __init__(self, page, records, offset=0):
        super().__init__()
        self.page, self.offset = page, offset
        self.groups = list(dict.fromkeys(row.get('power_group', 'main') for _, row in records
                                        if row.get('lane') and row.get('connectable', True)))

    def connect(self, row, terminal, terminal_name='t'):
        if not row.get('lane') or row.get('connectable', True) is False:
            return
        from drawing import FX_IN_X, LANE, LANE_TOP_Y
        from .typography import text_w, TEXT_MARGIN, PX_PER_PT
        group, name = row.get('power_group', 'main'), row['lane']
        index = self.groups.index(group)
        key = (group, name)
        if key not in self:
            x = FX_IN_X['outer' if name == 'P' else 'inner'] + index * 90 + self.offset
            suffix = '' if len(self.groups) == 1 else ('U' if group == 'unit' else 'I' if group == 'io' else str(index + 1))
            label = LANE[name] + suffix
            self.page.power_lane_label(x, label)
            self[key] = [x, self.page.place('junction', x, LANE_TOP_Y), label]
        x, previous, label = self[key]
        _, _, dx, dy = terminal[1].terminals[terminal_name]
        y = terminal[3] + dy
        node = self.page.place('junction', x, y)
        self.page.wire(previous, 's', node, 'n')
        self.page.wire(node, 'e', terminal, terminal_name, num=label, show=True)
        wire = self.page.conductors[-1]
        wire.set('userx', str(round(terminal[2] + dx - 12 - text_w(label, 8) - 2 * TEXT_MARGIN, 1)))
        wire.set('usery', str(round(y - 8 * PX_PER_PT - 2 * TEXT_MARGIN - 2, 1)))
        self[key][1] = node

    def finish(self, bottom=790):
        if self:
            self.page.extend_lanes([value[0] for value in self.values()], bottom=bottom)


def finish_box(page, left, right, content_end, rows=(), values=None, *, limit=790,
               minimum=160, settings_x=None, settings_width=None, obstacles_bottom=52,
               draw_frame=True):
    """内容に外枠を合わせ、右引出し範囲の下へ設定欄の下端をそろえる。"""
    bottom = max(content_end, minimum)
    x = right + 65 if settings_x is None else settings_x
    width = min(310, 1220 - x) if settings_width is None else settings_width
    if rows:
        if width < 200 or x + width > 1240:
            raise ValueError('機器右側の設定欄が収まりません。機器を別ページに分けてください')
        height = sum(h for _, _, h in settings.layout(rows, values or {}, width))
        exits = [py + t[3] for key, _, px, py in page.placed if left <= px <= right + 10
                 for t in page.sym[key].terminals.values() if t[1] == 'e']
        bottom = max(bottom, max([52, obstacles_bottom, *exits]) + 16 + height)
    if bottom > limit:
        raise ValueError('機器内容と右側設定欄が注記領域までに収まりません')
    frames = [shape for shape in page.shapes if shape.get('type') == 'Rectangle'
              and float(shape.get('x1')) == left and float(shape.get('x2')) == right
              and float(shape.get('y1')) == 52]
    if frames and draw_frame:
        frames[-1].set('y2', str(bottom))
    elif draw_frame:
        page.rect(left, 52, right, bottom, dash=False, width=1)
    settings.draw(page, rows, values or {}, x, x + width, bottom=bottom)
    return bottom


def single_units(pg):
    """左右の指定・設定値を保持して、配線余白のある単体ページへ分ける。"""
    for side in ('left', 'right'):
        if not pg.get(side + '_model'):
            continue
        unit = {key: value for key, value in pg.items() if not key.startswith(('left_', 'right_'))}
        unit.update({key.replace(side + '_', 'left_', 1): value for key, value in pg.items()
                     if key.startswith(side + '_')})
        visibility = pg.get('settings_visibility', {})
        unit['settings_visibility'] = {key.replace(side + '_', 'left_', 1): value
                                       for key, value in visibility.items() if key.startswith(side + '_')}
        yield unit
