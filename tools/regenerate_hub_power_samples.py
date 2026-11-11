"""掲載機種・配置・管理番号を保持し、ハブ/電源サンプルの埋込み部品を再生成する。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
import json
import os
import tempfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
from renderers.ethernet_switch import definition as hub_definition
from tools.export_power_supply_elements import definition as power_definition

SAMPLES = {'hub': (10, 5), 'power': (20, 5)}


def records(kind):
    folder = ROOT / ('parts/network' if kind == 'hub' else 'parts/power_supply/omron')
    found = {}
    for path in sorted(folder.rglob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        spec = data.get('definition', {})
        if (kind == 'hub' and spec.get('device_type') == 'ethernet_switch'
                or kind == 'power' and data.get('category') == 'power_supply'):
            found[data['model']] = spec
    return found


def layout(root):
    return [(dict(page.attrib), [(dict(element.attrib),
             [(info.get('name'), info.text) for info in element.findall('./elementInformations/elementInformation')
              if info.get('name') in ('label', 'auxiliary1')])
             for element in page.findall('./elements/element')]) for page in root.findall('diagram')]


def validate(root, kind):
    entries = root.findall('./collection/category/category/element')
    pages = root.findall('diagram')
    if (len(entries), len(pages)) != SAMPLES[kind]:
        raise ValueError(f'{kind}: 掲載機種数/ページ数が想定と違います')
    definitions = {entry.get('name'): entry.find('definition') for entry in entries}
    for page in pages:
        width = int(page.get('cols')) * float(page.get('colsize')) + 20
        height = int(page.get('rows')) * float(page.get('rowsize')) + 20
        for element in page.findall('./elements/element'):
            definition = definitions[element.get('type').rsplit('/', 1)[-1]]
            x, y = float(element.get('x')), float(element.get('y'))
            for rect in definition.findall('./description/rect'):
                rx, ry = x + float(rect.get('x')), y + float(rect.get('y'))
                if not (0 <= rx <= rx + float(rect.get('width')) <= width
                        and 20 <= ry <= ry + float(rect.get('height')) <= height):
                    raise ValueError('部品枠が図枠からはみ出しています')
            terminals = definition.findall('./description/terminal')
            for terminal in terminals:
                if not (0 <= x + float(terminal.get('x')) <= width
                        and 20 <= y + float(terminal.get('y')) <= height):
                    raise ValueError('接続ポイントが図枠からはみ出しています')
            circles = [circle for circle in definition.findall('./description/circle')
                       if float(circle.get('diameter')) == 8]
            for circle in circles:
                cx, cy = float(circle.get('x')), float(circle.get('y')) + 4
                terminal = next((t for t in terminals if float(t.get('y')) == cy and
                                 (t.get('orientation') == 'w' and float(t.get('x')) == cx
                                  or t.get('orientation') == 'e' and float(t.get('x')) == cx + 8)), None)
                if terminal is None:
                    raise ValueError('丸端子の外周と接続ポイントが一致しません')
                tx = float(terminal.get('x'))
                for line in definition.findall('./description/line'):
                    if float(line.get('y1')) == float(line.get('y2')) == cy:
                        ends = [float(line.get('x1')), float(line.get('x2'))]
                        if terminal.get('orientation') == 'w' and min(ends) < tx or terminal.get('orientation') == 'e' and max(ends) > tx:
                            raise ValueError('丸端子から外へ突き出す引出線があります')
            header = definition.find('./description/rect[@y="-18"]')
            if header is None or header.get('height') != '18':
                raise ValueError('共通の18px見出しがありません')


def regenerate(path, kind):
    path = Path(path).resolve()
    result = dict(source=str(path), output=str(path), status='error', before_pages=0,
                  after_pages=None, updated_paths=[], error='')
    temporary = None
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        result['before_pages'] = len(root.findall('diagram'))
        original_layout = layout(root)
        specs = records(kind)
        definitions = {}
        builder = hub_definition if kind == 'hub' else power_definition
        for entry in root.findall('./collection/category/category/element'):
            previous = entry.find('definition')
            model = previous.findtext('./names/name[@lang="en"]')
            current = builder(model, specs[model])
            old_terminals = [(t.get('uuid'), t.get('name')) for t in previous.findall('./description/terminal')]
            new_terminals = [(t.get('uuid'), t.get('name')) for t in current.findall('./description/terminal')]
            if old_terminals != new_terminals:
                raise ValueError(f'{model}: 端子の識別子/名称が変わるため既存図面を保持しました')
            definitions[entry.get('name')] = current
            entry.remove(previous)
            entry.append(current)
        for element in root.findall('./diagram/elements/element'):
            definition = definitions[element.get('type').rsplit('/', 1)[-1]]
            dynamic = element.find('dynamic_texts')
            dynamic.clear()
            for node in definition.findall('./description/dynamic_text'):
                node = copy.deepcopy(node)
                node.tag = 'dynamic_elmt_text'
                dynamic.append(node)
        if layout(root) != original_layout:
            raise ValueError('ページ情報・配置・管理番号が変わりました')
        validate(root, kind)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            ET.indent(tree, space='  ')
            tree.write(stream, encoding='utf-8', xml_declaration=True)
        validate(ET.parse(temporary).getroot(), kind)
        os.replace(temporary, path)
        result.update(status='ok', after_pages=len(root.findall('diagram')), updated_paths=[str(path)])
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=ROOT / 'pdf_ハブ電源_20261028')
    parser.add_argument('--results', type=Path, default=ROOT / '_review/qet_regen_latest/hub_power_results.json')
    args = parser.parse_args(argv)
    results = [regenerate(args.folder / (kind + '_共通端子修正.qet'), kind) for kind in SAMPLES]
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps({'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return int(any(row['status'] != 'ok' for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
