"""A3横1ページの製作仕様書サンプルをQETで作る。記入例であり実案件の仕様ではない。"""
import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gen_io_page as g


def choices(*labels, selected=()):
    return [(label, label in selected) for label in labels]


COLUMNS = [
    [
        ('適用条件', [
            ('顧客仕様', choices('有', '無', '別途')),
            ('設置場所', choices('屋内', '屋外', 'その他', selected=('屋内',))),
            ('盤形式', choices('自立', '壁掛け', 'その他', selected=('壁掛け',))),
            ('外形寸法', 'W(       ) H(       ) D(       ) mm'),
            ('使用温度', '(                ) ℃'),
            ('使用湿度', '(                ) %'),
        ]),
        ('筐体・構造', [
            ('材質', choices('鋼板', 'ステンレス', 'その他')),
            ('板厚', '外箱(     ) 扉(     ) 取付板(     ) mm'),
            ('保護構造', choices('図面指定', '別途指定', 'その他')),
            ('引込口', choices('上', '下', '側面', '別図')),
            ('扉', choices('片開き', '両開き', 'なし')),
            ('扉付属品', choices('ストッパ', 'パッキン', 'なし')),
        ]),
        ('塗装・仕上げ', [
            ('仕上げ', choices('塗装', '無塗装', 'その他')),
            ('塗装方法', choices('焼付', '粉体', '別途指定')),
            ('外面色', '色番号 (                         )'),
            ('内面色', '色番号 (                         )'),
            ('艶', choices('全艶', '半艶', 'つや消し')),
        ]),
        ('その他の指定', [('代替品', choices('不可', '事前確認', selected=('事前確認',)))]),
    ],
    [
        ('電源条件', [
            ('主回路', choices('単相', '三相', 'その他')),
            ('主電圧', choices('100V', '200V', '400V', 'その他')),
            ('周波数', choices('50Hz', '60Hz', '別途')),
            ('制御回路', choices('AC', 'DC', 'その他')),
            ('制御電圧', choices('24V', '100V', '200V', 'その他')),
            ('供給元', choices('盤内', '外部', '別途')),
        ]),
        ('配線仕様', [
            ('配線方式', choices('ダクト', '束線', 'その他')),
            ('主回路線', choices('IV', 'KIV', 'その他')),
            ('制御線', choices('IV', 'KIV', 'その他')),
            ('線径', '主(         ) 制御(         ) mm²'),
            ('線色', choices('顧客指定', '社内標準', '別表')),
            ('端末', choices('丸形', 'Y形', '棒形', '裸線')),
            ('線番', choices('チューブ', 'ラベル', '無', selected=('チューブ',))),
        ]),
        ('端子台・接地', [
            ('接続方式', choices('ねじ式', 'ばね式', 'その他')),
            ('端子表示', choices('追番', '線番', '指定', selected=('追番',))),
            ('予備端子', choices('有', '無', '別途')),
            ('接地端子', choices('有', '無', '別途')),
        ]),
        ('表示の指定', [('線番方向', choices('縦', '横', '図面指定'))]),
    ],
    [
        ('表示・銘板', [
            ('銘板材質', choices('樹脂', '金属', 'その他')),
            ('取付方法', choices('ねじ', '接着', 'その他')),
            ('文字', choices('印刷', '彫刻', '別途')),
            ('機器表示', choices('有', '無', '別途', selected=('有',))),
            ('表示・操作色', choices('顧客指定', '社内標準', '別表')),
        ]),
        ('盤内付属品', [
            ('照明', choices('有', '無')),
            ('コンセント', choices('有', '無')),
            ('換気', choices('自然', 'ファン', '別途')),
            ('図面入れ', choices('有', '無')),
        ]),
    ],
]
BLOCK_WIDTH, LABEL_WIDTH = 370, 88
HEADER_HEIGHT, ROW_HEIGHT, BLOCK_GAP = 24, 28, 8


def draw_block(page, x, y, title, rows):
    bottom = y + HEADER_HEIGHT + len(rows) * ROW_HEIGHT
    page.rect(x, y, x + BLOCK_WIDTH, bottom, dash=False, width=1)
    page.text(x + 8, y + 3, title, 9, True)
    page.line(x, y + HEADER_HEIGHT, x + BLOCK_WIDTH, y + HEADER_HEIGHT, width=0.8)
    page.line(x + LABEL_WIDTH, y + HEADER_HEIGHT, x + LABEL_WIDTH, bottom, width=0.5)
    for index, (label, value) in enumerate(rows):
        top = y + HEADER_HEIGHT + index * ROW_HEIGHT
        if index:
            page.line(x, top, x + BLOCK_WIDTH, top, width=0.5)
        page.text(x + 8, top + 5, label, 8)
        value_x = x + LABEL_WIDTH + 8
        if isinstance(value, str):
            page.text(value_x, top + 5, value, 8)
        else:
            for option, checked in value:
                text = ('■ ' if checked else '□ ') + option
                page.text(value_x, top + 5, text, 8)
                value_x += g.text_w(text, 8) + 14
    return bottom + BLOCK_GAP


def make(output):
    cfg = g.project_config({'project_title': '製作仕様書サンプル', 'machine': 'サンプル制御盤',
                            'company': '作図サンプル', 'drawing_no': 'SAMPLE-SP-001',
                            'revision': 'A', 'front_pages': False})
    page = g.Page({})
    page.text(50, 42, '制御盤 製作仕様書', 18, True)
    page.text(1050, 52, 'SAMPLE / 記入例', 10, True)
    page.rect(50, 88, 1210, 122, dash=False, width=1)
    page.line(670, 88, 670, 122, width=0.8)
    page.text(62, 95, '対象：サンプル制御盤', 10)
    page.text(682, 95, '選択方式：□ → ■ ／ 数値・その他は記入', 10)
    for column, blocks in enumerate(COLUMNS):
        y = 144
        for title, rows in blocks:
            y = draw_block(page, 50 + column * 395, y, title, rows)
    page.text(50, 800, '■ 選択／□ 未選択。選択は記入例、未選択・空欄は未確認。', 8)
    project, _ = g.build_project(cfg, [])
    project.remove(project.find('collection'))  # 図形と文字だけなので部品定義は不要。
    g.add_diagram(project, cfg, '制御盤 製作仕様書（サンプル）', 1, page)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(project, space='  ')
    ET.ElementTree(project).write(output, encoding='utf-8', xml_declaration=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', default='_review/manufacturing_spec/manufacturing_spec.qet')
    print(make(parser.parse_args().output))
