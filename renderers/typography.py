"""図面用の文字幅、禁則折返し、セル内の文字サイズ選定。"""
import math
import re

PX_PER_PT = 96 / 72
TEXT_MARGIN = 4


def text_w(text, size):
    """MS ゴシックの文字幅（全角1em、半角・半角カナ0.5em）。"""
    em = size * PX_PER_PT
    return sum(em * (0.5 if (ord(c) < 0x2000 or 0xFF61 <= ord(c) <= 0xFF9F) else 1.0) for c in text)


def text_width(text, pt):
    """文字幅の目安(px)。全角は 1pt = 96/72 px、半角はその 0.55 倍"""
    px = pt * 96 / 72
    return sum(px if ord(c) > 255 else px * 0.55 for c in str(text))


# 行頭に置かない文字(句読点・閉じ括弧・長音など)と、行末に置かない文字(開き括弧)
NO_LINE_START = set('、。，．,.)）]］}｝」』】〕〉》〙！？!?・：:;；ー〜～%％ゃゅょっぁぃぅぇぉャュョッァィゥェォ')
NO_LINE_END = set('(（[［{｛「『【〔〈《〘')


def _tokens(text):
    """英数字・記号の続き(型式・CH1 など)は1語、全角文字は1文字ずつ、空白は区切り。"""
    tokens, word = [], ''
    for c in text:
        if c == ' ':
            if word:
                tokens.append(word); word = ''
            tokens.append(' ')
        elif ord(c) < 0x2000 and c not in '()[]{},.;:!?':
            word += c
        else:
            if word:
                tokens.append(word); word = ''
            tokens.append(c)
    if word:
        tokens.append(word)
    return tokens


def wrap(text, width, pt, measure=text_width):
    """幅 width に収まるように折り返す。英数字の語は分けず、句読点・閉じ括弧は行頭に、
    開き括弧は行末に置かない。最後の行が1〜2文字だけになるときは前の行から送る。"""
    lines = []
    for paragraph in str(text).split('\n'):
        rows, line = [], []
        for token in _tokens(paragraph):
            if token == ' ' and not line:
                continue
            if line and measure(''.join(line) + token, pt) > width:
                carry = []
                if token in NO_LINE_START and len(line) > 1:
                    carry = [line.pop()]                    # 句読点の前の1文字ごと次の行へ
                while len(line) > 1 and line[-1] in NO_LINE_END:
                    carry.insert(0, line.pop())
                while line and line[-1] == ' ':
                    line.pop()
                rows.append(line)
                line = carry
                if token == ' ':
                    continue
            if measure(token, pt) > width and len(token) > 1:
                for c in token:                             # 1語が欄より長いときだけ文字で区切る
                    if line and measure(''.join(line) + c, pt) > width:
                        rows.append(line); line = []
                    line.append(c)
                continue
            line.append(token)
        if line:
            rows.append(line)
        if len(rows) > 1 and len(''.join(rows[-1]).strip()) <= 2:
            # 1〜2文字だけの行を作らない
            while len(rows[-2]) > 1 and len(''.join(rows[-1]).strip()) <= 2:
                moved = rows[-2].pop()
                if moved != ' ':
                    rows[-1].insert(0, moved)
                if measure(''.join(rows[-1]), pt) > width:
                    rows[-1].pop(0); rows[-2].append(moved)
                    break
        lines += [''.join(row).strip() for row in rows]
    return [line for line in lines if line] or ([] if not str(text).strip() else [str(text)])


def _clean_split(value, width, size):
    """語の区切り(空白・「／」の後・「（」の前)で2段に分ける。両段が収まらなければ None。"""
    best = None
    for index in range(1, len(value)):
        c = value[index]
        if c in '／/':
            head, tail, rank = value[:index + 1], value[index + 1:], 0
        elif c in '（(':
            head, tail, rank = value[:index], value[index:], 1
        elif c == ' ':
            head, tail, rank = value[:index], value[index + 1:], 2
        else:
            continue
        head, tail = head.rstrip(), tail.lstrip()
        if head and tail and text_w(head, size) <= width and text_w(tail, size) <= width:
            key = (rank, abs(text_w(head, size) - text_w(tail, size)))
            if best is None or key < best[0]:
                best = (key, head + '\n' + tail)
    return best[1] if best else None


def _cell_lines(value, width, size):
    if text_w(value, size) <= width and '\n' not in value:
        return [value]
    if '\n' not in value:
        split = _clean_split(value, width, size)
        if split:
            return split.split('\n')
    return wrap(value, width, size, text_w)


def wrap2(value, width, size):
    """語の区切りと禁則を優先する2段欄。内容は省略しない。"""
    lines = _cell_lines(value, width, size)
    if len(lines) > 2:
        lines = lines[:1] + [''.join(lines[1:])]
    return '\n'.join(lines)


cell_wrap = wrap2


def fit_cell(value, width):
    """8ptの語区切り・禁則を試し、入らない場合は7ptで同じ順に試す。"""
    if '\n' in value or text_w(value, 8) <= width:
        return value, 8
    split = _clean_split(value, width, 8)
    if split:
        return split, 8
    lines = wrap(value, width, 8)
    if len(lines) <= 2 and all(text_w(line, 8) <= width for line in lines):
        return '\n'.join(lines), 8
    split = _clean_split(value, width, 7)
    if split:
        return split, 7
    # 長い信号名でも末尾を消さない。呼出し側の高さ検査で扱えるよう全文を返す。
    return '\n'.join(wrap(value, width, 7)), 7


def fit_font_size(value, width, row_height, max_size):
    """QETの等幅文字の丸めを含め、既存IO欄に収まるサイズと行数を返す。"""
    for size in dict.fromkeys((max_size, 9, 8, 7, 6)):
        if size > max_size:
            continue
        pixel_ratio = math.ceil(size * PX_PER_PT / 2) / (size * PX_PER_PT / 2)
        lines = sum(max(1, math.ceil(text_w(line, size) * pixel_ratio / (width - 2 * TEXT_MARGIN)))
                    for line in value.split('\n'))
        single = '\n' not in value and not re.search(r'\s|/(?=\D)', value.strip())
        if single and lines > 1 and size > 6:
            continue
        if lines <= 2 and lines * size * PX_PER_PT + 2 * TEXT_MARGIN <= row_height:
            break
    return size, min(lines, 2)
