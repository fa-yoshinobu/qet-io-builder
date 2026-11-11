"""プレビューの文字外接矩形と水平・垂直線で、QETのレイアウトを検査する。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import math
from collections import Counter
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from tools import preview_qet


@dataclass(frozen=True)
class Issue:
    kind: str
    text: str
    bounds: tuple
    other: str = ''


class RecordingDraw:
    """ImageDrawと同じ座標・フォントで本文の文字と罫線を記録する。"""
    def __init__(self, draw, bounds):
        self.draw = draw
        self.bounds = bounds
        self.texts = []
        self.lines = []

    def __getattr__(self, name):
        return getattr(self.draw, name)

    def text(self, xy, text, **kwargs):
        if text.strip():
            box = self.draw.textbbox(xy, text, **{key: value for key, value in kwargs.items()
                                                if key != 'fill'})
            self.record_text(text, box)

    def record_text(self, text, bounds):
        """プレビューが計算した輪郭・回転後の文字外接矩形を記録する。"""
        if text.strip():
            self.texts.append((text, bounds))

    def line(self, xy, **kwargs):
        for a, b in zip(xy, xy[1:]):
            if a != b and (a[0] == b[0] or a[1] == b[1]):
                self.lines.append((min(a[0], b[0]), min(a[1], b[1]),
                                   max(a[0], b[0]), max(a[1], b[1])))

    def ellipse(self, xy, **kwargs):
        if kwargs.get('fill') in ('white', '#ffffff', '#FFFFFF'):
            x1, y1, x2, y2 = xy
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            rx, ry = (x2 - x1) / 2, (y2 - y1) / 2
            visible = []
            for a, b, c, d in self.lines:
                horizontal = b == d
                distance = (b - cy) / ry if horizontal else (a - cx) / rx
                if abs(distance) >= 1:
                    visible.append((a, b, c, d))
                    continue
                reach = math.sqrt(1 - distance * distance) * (rx if horizontal else ry)
                low, high = (cx - reach, cx + reach) if horizontal else (cy - reach, cy + reach)
                start, end = (a, c) if horizontal else (b, d)
                for lo, hi in ((start, min(end, low)), (max(start, high), end)):
                    if lo < hi:
                        visible.append((lo, b, hi, d) if horizontal else (a, lo, c, hi))
            self.lines = visible
        self.draw.ellipse(xy, **kwargs)

    def rectangle(self, xy, **kwargs):
        if len(xy) == 4:
            x1, y1, x2, y2 = xy
        else:
            (x1, y1), (x2, y2) = xy
        if kwargs.get('fill') in ('white', '#ffffff', '#FFFFFF'):
            visible = []
            for a, b, c, d in self.lines:
                horizontal = b == d
                covered = y1 < b < y2 if horizontal else x1 < a < x2
                if not covered:
                    visible.append((a, b, c, d))
                    continue
                start, end, low, high = (a, c, x1, x2) if horizontal else (b, d, y1, y2)
                for lo, hi in ((start, min(end, low)), (max(start, high), end)):
                    if lo < hi:
                        visible.append((lo, b, hi, d) if horizontal else (a, lo, c, hi))
            self.lines = visible
        self.line([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)])

    def rounded_rectangle(self, xy, radius=0, **kwargs):
        x1, y1, x2, y2 = xy
        self.line([(x1 + radius, y1), (x2 - radius, y1)])
        self.line([(x1 + radius, y2), (x2 - radius, y2)])
        self.line([(x1, y1 + radius), (x1, y2 - radius)])
        self.line([(x2, y1 + radius), (x2, y2 - radius)])

    def issues(self):
        result = []
        left, top, right, bottom = self.bounds
        lines = set(self.lines)
        for i, (text, box) in enumerate(self.texts):
            x1, y1, x2, y2 = box
            if x1 < left or y1 < top or x2 > right or y2 > bottom:
                result.append(Issue('枠外', text, box))
            for other, (a, b, c, d) in self.texts[i + 1:]:
                if min(x2, c) > max(x1, a) and min(y2, d) > max(y1, b):
                    result.append(Issue('文字重なり', text, box, other))
            for a, b, c, d in lines:
                horizontal = b == d and y1 < b < y2 and min(x2, c) > max(x1, a)
                vertical = a == c and x1 < a < x2 and min(y2, d) > max(y1, b)
                if horizontal or vertical:
                    result.append(Issue('線横切り', text, box, f'({a:g},{b:g})-({c:g},{d:g})'))
        return result


def check(path):
    if not preview_qet.FONT:
        raise ValueError('日本語フォントがありません。MS ゴシックまたは Noto Sans CJKを導入してください')
    pages = []
    def record(draw, diagram, number):
        bounds = (20, 20, 20 + int(diagram.get('cols')) * float(diagram.get('colsize')),
                  20 + int(diagram.get('rows')) * float(diagram.get('rowsize')))
        recorder = RecordingDraw(draw, bounds)
        pages.append((number, diagram.get('title', ''), recorder))
        return recorder
    preview_qet.render(path, None, draw_factory=record)
    if not pages:
        raise ValueError('検査する図面ページがありません')
    return [(number, title, recorder.issues()) for number, title, recorder in pages]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qet', nargs='+', help='検査するQETファイル')
    args = parser.parse_args(argv)
    status = 0
    for path in args.qet:
        try:
            for number, title, issues in check(path):
                if issues:
                    counts = '、'.join(f'{kind} {count}' for kind, count in Counter(i.kind for i in issues).items())
                    first = issues[0]
                    print(f'{path}:p.{number} {title} | {counts} | {first.text!r} {first.bounds} {first.other}')
                    status = max(status, 1)
        except (OSError, ValueError, ET.ParseError) as error:
            print(f'{path}: {error}', file=sys.stderr)
            status = 2
    return status


if __name__ == '__main__':
    sys.exit(main())
