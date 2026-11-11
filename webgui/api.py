"""Web版GUIの処理。画面(JavaScript)から呼ばれ、結果をJSONにできる辞書で返す。

pywebview では js_api として、ブラウザ確認用サーバーでは /api/<名前> として同じメソッドを使う。
状態は先頭が _ の属性に置く(pywebview が画面へ公開しないように)。"""
import copy
import csv
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import gen_io_page as gen
import gui_core as core
import plc_configuration as plc
from project_wiring.data import (BOUNDARY_DEFAULTS, CONNECTION_DEFAULTS, CONTENT_FIELDS, POSITION_FIELDS,
                                 normalize as normalize_wiring, terminal_rows)

ROOT = core.ROOT
BUS_NAMES = {'power': '電源ユニット', 'left': '左側アダプタ', 'front': '前面カセット',
             'direct': '右側 直接接続', 'legacy': '右側 変換バス', 'nx': '右側 NXバス', 'x': '左側 Xバス'}


def production_end_label(spec, today=None):
    value = spec.get('production_end_date')
    if not value:
        return ''
    end = date.fromisoformat(value)
    return f'{end.year}年' + ('予定' if end > (today or date.today()) else '')

VENDOR_KINDS = ('kvbody', 'nxbody')
BODY_KINDS = ('iqrbody', 'qbody', 'fx5body', 'mxbody', *VENDOR_KINDS)
LINEAR_KINDS = ('fx5body', 'mxbody', *VENDOR_KINDS)
RACK_KINDS = ('iqrbody', 'qbody')
MODEL_KEYS = ('model', 'left_model', 'right_model', 'power_model', 'base_model')
TAG_KEYS = {'model': 'tag', 'left_model': 'left_tag', 'right_model': 'right_tag',
            'power_model': 'power_tag', 'base_model': 'base_tag', 'board_model': 'board_tag'}
# 画面のユニット構成・配線情報で編集し、「その他の設定」には出さない項目
MANAGED_KEYS = ('modules', 'module_tags', 'module_buses', 'module_modes', 'extensions', 'wiring', 'module_starts', 'settings_visibility')
PROJECT_FIELDS = [('project_title', 'プロジェクト名'), ('company', '会社名'), ('customer', '顧客名'),
                  ('machine', '装置名'), ('drawing_no', '図番'), ('revision', '改訂'),
                  ('date', '日付（YYYYMMDD）'), ('author', '作成者'), ('checker', '検図者'), ('approver', '承認者')]
GROUP_NAMES = {
    'coupler': 'カプラ',
    'digital_io': '入出力', 'analog_io': 'アナログ', 'network': 'ネットワーク', 'serial': 'シリアル',
    'information': '情報', 'counter_pulse': 'カウンタ・パルス', 'motion_positioning': '位置決め',
    'cpu': 'CPU', 'base': 'ベース', 'power_supply': '電源', 'mixed_io': '入出力混合',
    'body': '本体', 'communication': '通信', 'expansion_board': '拡張ボード', 'io_link': 'IO-Link',
    'breaker': 'ブレーカ', 'buzzer': 'ブザー', 'contact_block': '接点ブロック', 'contactor': '電磁接触器',
    'float_switch': 'フロートスイッチ', 'fuse': 'ヒューズ', 'lamp': '表示灯', 'limit_switch': 'リミットスイッチ',
    'motor': 'モータ', 'pressure_switch': '圧力スイッチ', 'protector': '保護器', 'relay': 'リレー',
    'sensor': 'センサ', 'socket': 'ソケット', 'solenoid': '電磁弁', 'switch': 'スイッチ',
    'terminal': '端子台', 'thermal': 'サーマル', 'timer': 'タイマ',
    'lighting': '盤内LED照明', 'outlet': '盤内コンセント', 'noise_filter': 'ノイズフィルタ', 'transformer': 'トランス',
    'surge_protection': 'サージ保護器（SPD）',
    'ammeter': '電流計', 'current_transformer': 'CT（計測用変流器）',
}
BOARDS = ('なし', 'FX5-3A-BD', 'FX5-232-BD', 'FX5-485-BD', 'FX5-422-BD-GOT')


class Cancelled(Exception):
    """ファイル選択などを利用者が取り消した。"""


EDIT_METHODS = {'set_project', 'add_page', 'duplicate_page', 'delete_page', 'move_page', 'move_page_to',
                'update_page', 'set_module', 'remove_module', 'set_module_tag', 'set_module_start', 'set_module_bus', 'set_module_mode',
                'set_stage_part', 'add_extension', 'remove_extension', 'create_unit_page',
                'create_all_unit_pages', 'create_cpu_io_page', 'make_page_csv', 'set_wiring', 'make_sample', 'sync_details', 'set_setting_visibility', 'generate_configuration'}


def _safe(method):
    def wrapper(self, *args):
        editing = method.__name__ in EDIT_METHODS and not self._editing
        if editing:
            before = (copy.deepcopy(self._data), self._index)
            dirty_before = self._dirty
            self._editing = True
        try:
            result = method(self, *args)
            if editing and isinstance(result, dict) and result.get('error'):
                self._data, self._index = before
                self._dirty = dirty_before
            elif editing and self._data != before[0]:
                self._undo.append(before)
                self._undo = self._undo[-100:]
                self._redo.clear()
                self._touch()
            if editing and isinstance(result, dict):
                result.update(can_undo=bool(self._undo), can_redo=bool(self._redo), dirty=self._dirty)
            return {'ok': True} if result is None else result
        except Cancelled:
            if editing:
                self._data, self._index = before
                self._dirty = dirty_before
            return {'cancelled': True}
        except (ValueError, OSError, TypeError, KeyError, IndexError, gen.ET.ParseError) as error:
            if editing:
                self._data, self._index = before
                self._dirty = dirty_before
            return {'error': str(error) or error.__class__.__name__}
        finally:
            if editing:
                self._editing = False
    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    return wrapper


def _text(value):
    return '' if value is None else str(value)


_CACHE = {}


def _cached(name, function, *args):
    """部品データは起動中に変わらないので、一覧の読み込み結果を使い回す。"""
    key = (name,) + args
    if key not in _CACHE:
        _CACHE[key] = function(*args)
    return copy.deepcopy(_CACHE[key])


def part_catalog(key, kind):
    return _cached('catalog', core.part_catalog, key, kind)


def definitions():
    if 'definitions' not in _CACHE:
        _CACHE['definitions'] = gen.read_unit_definitions()
    return _CACHE['definitions']


def property_fields(kind, model=''):
    return _cached('fields', core.property_fields, kind, model)


def series_kinds(maker, series):
    return _cached('kinds', lambda m, s: core.series_kinds(m, s, part_catalog('series', '')), maker, series)


class Api:
    def __init__(self, dialogs=None):
        # dialogs: open_file(title, types) / save_file(title, name, types, folder) / folder(title) を持つもの。
        # None のときは画面からパスを受け取る(ブラウザ確認用)。
        self._dialogs = dialogs
        self._path = None
        self._data = gen.project_config({'pages': [], 'front_pages': False})
        self._dirty = False
        self._index = None
        self._undo, self._redo = [], []
        self._editing = False
        self._saved_data = copy.deepcopy(self._data)

    # ------------------------------------------------------------ 共通
    def _ask(self, kind, title, path, name='', types=('JSON (*.json)',)):
        if path:
            return Path(path)
        if self._dialogs is None:
            raise ValueError('ファイルの場所を入力してください')
        folder = str(self._path.parent) if self._path else str(ROOT)
        if kind == 'open':
            chosen = self._dialogs.open_file(title, types, folder)
        elif kind == 'save':
            chosen = self._dialogs.save_file(title, name, types, folder)
        else:
            chosen = self._dialogs.folder(title, folder)
        if not chosen:
            raise Cancelled()
        return Path(chosen)

    def _page(self, index):
        index = int(index)
        if not 0 <= index < len(self._data['pages']):
            raise ValueError('ページがありません')
        return self._data['pages'][index]

    def _touch(self):
        self._dirty = self._data != self._saved_data

    def _reset_history(self):
        self._undo.clear()
        self._redo.clear()
        self._saved_data = copy.deepcopy(self._data)
        self._index = None

    @_safe
    def undo(self):
        return self._restore(self._undo, self._redo)

    @_safe
    def redo(self):
        return self._restore(self._redo, self._undo)

    def _restore(self, source, target):
        if source:
            target.append((copy.deepcopy(self._data), self._index))
            self._data, self._index = source.pop()
            self._touch()
        index = self._index
        if index is not None:
            index = min(index, len(self._data['pages']) - 1)
            if index < 0:
                index = None
        return {**self.snapshot(), 'index': index}

    def _page_parent(self, index):
        page = self._data['pages'][index]
        if page.get('kind') in BODY_KINDS:
            return None
        matches = []
        for parent, body in enumerate(self._data['pages']):
            if body.get('kind') not in BODY_KINDS:
                continue
            identities = [(body.get('model', ''), body.get('tag', ''), None)]
            for stage, config in enumerate([body] + list(body.get('extensions', []))):
                tags = config.get('module_tags', [])
                for slot, model in enumerate(config.get('modules', [])):
                    if model:
                        identities.append((model, tags[slot] if slot < len(tags) else '', str(self._slot_number(body, stage, slot))))
            for prefix in ('', 'left_', 'right_'):
                model, tag = page.get(prefix + 'model', ''), page.get(prefix + 'tag', '')
                number = page.get(prefix + 'slot', page.get(prefix + 'unit_no', ''))
                if model and any(model.upper() == m.upper() and
                                 (tag == t if tag else (str(number) == n if n is not None and number != '' else True))
                                 for m, t, n in identities):
                    matches.append(parent)
                    break
        preceding = [p for p in matches if p < index]
        return max(preceding) if preceding else matches[0] if len(matches) == 1 else None

    # ------------------------------------------------------------ 一覧・プロジェクト
    def _terminal_block_choices(self):
        choices = {}
        for block in gen.TERMINAL_BLOCKS.values():
            for connection in block['compatible']:
                for plc_model in connection['models']:
                    if plc_model in gen.KV_IO:
                        plc_maker = 'keyence'
                    elif plc_model in gen.UNIT_DIAGRAMS:
                        plc_maker = gen.UNIT_DIAGRAMS[plc_model]['manufacturer']
                    elif plc_model in gen.IO_UNITS:
                        plc_maker = 'mitsubishi'
                    else:
                        continue
                    by_model = choices.setdefault(plc_maker, {})
                    by_model.setdefault(plc_model, []).append(dict(model=block['model'], maker=block['manufacturer'],
                                                                   cable=connection['cable'], cable_maker=connection['cable_manufacturer'],
                                                                   kit=connection.get('kit', ''), ports=connection.get('ports'),
                                                                   branches=[b['connector'] for b in connection.get('branches', [])] or None))
        return choices

    @_safe
    def meta(self):
        def kv_function(spec):
            if spec.get('body'):
                return 'CPU・内蔵I/O'
            for section in ('module', 'analog'):
                if section in spec:
                    return spec[section]['function']
            directions = {d for page in spec['pages'] for d in page.get('directions', [])}
            if len(directions) > 1:
                return 'デジタル入出力'
            return 'デジタル出力' if spec.get('output') or 'output' in directions else 'デジタル入力'

        keyence = {m: s for m, s in gen.UNIT_DIAGRAMS.items() if s['manufacturer'] == 'keyence'}
        return {
            'kinds': {k: v for k, v in core.KIND_NAMES.items()},
            'fields': core.FIELDS,
            'makers': core.MAKER_NAMES,
            'series': core.SERIES_NAMES,
            'project_fields': PROJECT_FIELDS,
            'browser_paths': self._dialogs is None,
            'terminal_blocks': self._terminal_block_choices(),
            'kv_models': {model: spec['series'] for model, spec in sorted({**gen.KV_IO, **keyence}.items())},
            'kv_functions': {**{m: kv_function(s) for m, s in gen.KV_IO.items()},
                             **{m: s['function'] for m, s in keyence.items()}},
            'nx_models': {model: spec['function'] for model, spec in sorted(gen.UNIT_DIAGRAMS.items())
                          if spec['manufacturer'] == 'omron'},
            'omron_series': {model: spec['series'] for model, spec in gen.UNIT_DIAGRAMS.items()
                             if spec['manufacturer'] == 'omron'},
            'kv_modes': {model: list(spec['module']['modes']) for model, spec in gen.KV_IO.items()
                         if spec.get('module', {}).get('modes')},
            'kv_settings': {model: [key for label, key in spec['module'].get('settings', [])]
                            for model, spec in gen.KV_IO.items() if spec.get('module')},
        }

    @_safe
    def snapshot(self):
        config = gen.project_config(self._data)
        pages = []
        for i, page in enumerate(self._data['pages']):
            kind = page.get('kind', '')
            model = page.get('model') or ' / '.join(filter(None, (page.get('left_model'), page.get('right_model'))))
            tag = page.get('tag') or ' / '.join(filter(None, (page.get('left_tag'), page.get('right_tag'))))
            pages.append({'index': i, 'kind': kind, 'kind_name': core.KIND_NAMES.get(kind, kind or '種類を選択'),
                          'tag': _text(tag), 'model': _text(model), 'title': _text(page.get('title', '')),
                          'body': kind in BODY_KINDS, 'parent': self._page_parent(i), 'wiring': bool(page.get('wiring'))})
        return {
            'maker': self._project_maker(),
            'path': str(self._path) if self._path else '',
            'name': self._path.name if self._path else '新しいプロジェクト',
            'dirty': self._dirty,
            'can_undo': bool(self._undo), 'can_redo': bool(self._redo),
            'project': {**{k: _text(config.get(k, '')) for k, _ in PROJECT_FIELDS},
                        'power': {k: _text(config['power'].get(k, '')) for k in ('P', 'N')},
                        'front_pages': bool(config.get('front_pages'))},
            'pages': pages,
        }

    @_safe
    def new_project(self):
        self._path, self._dirty = None, False
        self._data = gen.project_config({'pages': [], 'front_pages': False})
        self._reset_history()
        return self.snapshot()

    def _project_maker(self, data=None):
        data = self._data if data is None else data
        if data.get('maker') in ('mitsubishi', 'keyence', 'omron'):
            return data['maker']
        makers = set()
        for page in data.get('pages', []):
            maker = page.get('maker')
            if not maker:
                if page.get('kind') in ('kvbody', 'kv_io'):
                    maker = 'keyence'
                elif page.get('kind') == 'nxbody':
                    maker = 'omron'
                elif page.get('kind') == 'unit_diagram':
                    maker = gen.UNIT_DIAGRAMS.get(str(page.get('model', '')).upper(), {}).get('manufacturer')
                else:
                    maker = 'mitsubishi'
            if maker:
                makers.add(maker)
        return next(iter(makers)) if len(makers) == 1 else 'mitsubishi'

    def _configuration_roots(self, maker, series):
        if maker not in ('keyence', 'omron'):
            raise ValueError('キーエンスまたはオムロンを選択してください')
        candidates = [r for r in plc.roots(maker, definitions()) if not series or series in r['series']]
        if not candidates:
            raise ValueError('構成を作成するPLCシリーズを選択してください')
        return candidates

    @_safe
    def configuration_roots(self, maker, series):
        rows = []
        for root in self._configuration_roots(maker, series):
            buses = root['spec']['configuration']['buses']
            rows.append(dict(model=root['model'], group='CPU' if root['role'] == 'cpu' else 'カプラ',
                             summary=' / '.join(BUS_NAMES[bus] for bus in buses if buses[bus]),
                             series=series, production_end=''))
        return {'rows': rows}

    @_safe
    def new_configuration(self, maker, series='', model=None):
        candidates = self._configuration_roots(maker, series)
        if model is None:
            # 形名を渡さない従来の呼出しはCPUを優先する。
            model = next((r['model'] for r in candidates if r['role'] == 'cpu'), candidates[0]['model'])
        elif model not in {r['model'] for r in candidates}:
            raise ValueError('選択したシリーズのCPU・カプラを指定してください')
        page = dict(kind='kvbody' if maker == 'keyence' else 'nxbody', maker=maker, model=model)
        self._path, self._dirty = None, True
        self._data = gen.project_config(dict(maker=maker, front_pages=False, pages=[page]))
        self._reset_history()
        return dict(index=0, **self.snapshot())

    @_safe
    def open_configuration(self, maker, path=None):
        if maker not in ('keyence', 'omron'):
            raise ValueError('キーエンスまたはオムロンを選択してください')
        path = self._ask('open', '構成プロジェクトを開く', path)
        with path.open(encoding='utf-8-sig') as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or not isinstance(data.get('pages'), list) or any(not isinstance(p, dict) for p in data['pages']):
            raise ValueError('プロジェクトJSONを選択してください')
        if self._project_maker(data) != maker:
            raise ValueError('選択したメーカーのプロジェクトを開いてください')
        result = self.open_project(str(path))
        if result.get('error'):
            return result
        return dict(index=0, **result)

    @_safe
    def open_project(self, path=None):
        path = self._ask('open', 'プロジェクトを開く', path)
        with open(path, encoding='utf-8-sig') as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get('pages'), list) or not all(isinstance(p, dict) for p in data['pages']):
            raise ValueError('pages が配列のプロジェクトJSONを選択してください')
        data = gen.project_config(data)
        for key, _ in PROJECT_FIELDS:
            if not isinstance(data[key], str):
                raise ValueError(f'{key} は文字列で指定してください')
        if any(not isinstance(data['power'][key], str) for key in ('P', 'N')):
            raise ValueError('P側・N側電源は文字列で指定してください')
        if not isinstance(data['front_pages'], bool):
            raise ValueError('front_pages は true または false で指定してください')
        if any(not isinstance(page.get('kind', ''), str) for page in data['pages']):
            raise ValueError('ページの種類は文字列で指定してください')
        self._path, self._data, self._dirty = Path(path), data, False
        self._reset_history()
        return self.snapshot()

    @_safe
    def set_project(self, values):
        for key, _ in PROJECT_FIELDS:
            if key in values:
                self._data[key] = _text(values[key]).strip()
        if 'power' in values:
            self._data['power'] = dict(self._data.get('power', {}), **{k: _text(v).strip() for k, v in values['power'].items() if k in ('P', 'N')})
        if 'front_pages' in values:
            self._data['front_pages'] = bool(values['front_pages'])
        self._touch()
        return self.snapshot()

    def _write(self, path):
        for i, page in enumerate(self._data['pages'], 1):
            if not page.get('kind'):
                raise ValueError(f'{i}ページ目の種類を選択してください')
        data = gen.project_config(self._data)
        text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='.' + path.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._data = data
        self._saved_data = copy.deepcopy(data)

    @_safe
    def save(self):
        if not self._path:
            return {'need_save_as': True}
        self._write(self._path)
        self._dirty = False
        return self.snapshot()

    @_safe
    def save_as(self, path=None, confirmed=False):
        path = self._ask('save', '名前を付けて保存', path, (self._path.name if self._path else 'project.json'))
        if path.suffix.lower() != '.json':
            path = path.with_suffix('.json')
        # CSV等の相対パスはJSONのフォルダが基準になる
        if self._path and path.resolve().parent != self._path.resolve().parent and not confirmed:
            return {'confirm': '保存先のフォルダが変わると、CSVなどの相対パスの参照先も変わります。続けますか？', 'path': str(path)}
        self._write(path)
        self._path, self._dirty = path, False
        return self.snapshot()

    @_safe
    def is_dirty(self):
        return {'dirty': self._dirty}

    # ------------------------------------------------------------ ページ
    @_safe
    def add_page(self, after=None):
        pages = self._data['pages']
        index = len(pages) if after is None else int(after) + 1
        maker = self._project_maker()
        page = {} if maker == 'mitsubishi' else dict(kind='kvbody' if maker == 'keyence' else 'nxbody', maker=maker)
        pages.insert(index, page)
        self._touch()
        return {'index': index, **self.snapshot()}

    @_safe
    def duplicate_page(self, index):
        page = copy.deepcopy(self._page(index))
        self._data['pages'].insert(int(index) + 1, page)
        self._touch()
        return {'index': int(index) + 1, **self.snapshot()}

    @_safe
    def delete_page(self, index):
        self._page(index)
        del self._data['pages'][int(index)]
        self._touch()
        return self.snapshot()

    @_safe
    def move_page(self, index, delta):
        pages = self._data['pages']
        index, target = int(index), int(index) + int(delta)
        self._page(index)
        if not 0 <= target < len(pages):
            return {'index': index, **self.snapshot()}
        pages.insert(target, pages.pop(index))
        self._touch()
        return {'index': target, **self.snapshot()}

    @_safe
    def move_page_to(self, index, target):
        """ページを target の位置へ移す(一覧のドラッグ用)。"""
        pages = self._data['pages']
        index, target = int(index), int(target)
        self._page(index)
        target = max(0, min(target, len(pages) - 1))
        if target != index:
            pages.insert(target, pages.pop(index))
            self._touch()
        return {'index': target, **self.snapshot()}

    def _scope(self, page):
        """ページのメーカー・シリーズ。未指定なら形名から推定する(旧GUIと同じ)。"""
        catalog = part_catalog('series', '')
        project_maker = self._project_maker()
        catalog = {project_maker: catalog.get(project_maker, {})}
        maker, series = page.get('maker', ''), page.get('series', '')
        if not maker or not series:
            models = {str(page.get(k, '')).upper() for k in MODEL_KEYS} - {''}
            matches = [(m, s) for m, ss in catalog.items() for s, units in ss.items()
                       if models & {u.upper() for u in units}]
            if not matches and page.get('kind'):
                matches = [(m, s) for m, ss in catalog.items() for s in ss
                           if page['kind'] in series_kinds(m, s)]
            if len(matches) == 1:
                maker, series = matches[0]
        if not maker and len(catalog) == 1:
            maker = next(iter(catalog))
        return maker, series, catalog

    def _visible(self, values):
        kind = values.get('kind', '')
        model = values.get('model') or values.get('left_model') or values.get('right_model') or ''
        visible = core.page_property_fields(values) if kind else ['kind']
        if values.get('model', '').upper().startswith('FX5S-') and values.get('board_model') != 'FX5-SDCD':
            visible = [k for k in visible if k not in ('sd_card', 'sd_card_model')]
        if 'board_model' not in visible:
            visible = [k for k in visible if k != 'board_tag']
        if kind == 'gotoption':
            for prefix in ('left', 'right'):
                if not gen.GOT_OPTION.get(values.get(prefix + '_model', '').upper(), {}).get('module_interfaces'):
                    visible = [k for k in visible if k != prefix + '_module']
        return visible

    def _options(self, values, maker, series, catalog):
        kind = values.get('kind', '')
        model = values.get('model', '').upper()
        options = {
            'maker': [[m, core.MAKER_NAMES.get(m, m)] for m in sorted(catalog)],
            'series': [[s, core.SERIES_NAMES.get(s, s)] for s in sorted(catalog.get(maker, {}))],
            'kind': [[k, core.KIND_NAMES[k]] for k in series_kinds(maker, series)] if series else [],
            'battery': ['装着', '非装着', '要確認'] if kind == 'qbody' else ['装着', '非装着', '搭載不可', '要確認'],
            'sd_card': ['有', '無', '要確認'], 'memory_cassette': ['有', '無', '要確認'], 'memory_card': ['有', '無', '要確認'],
            'batteryless': ['有', '無', '要確認'],
            'serial_mode': ['', 'RS-232', 'RS-422/485'],
            'board_model': list(BOARDS) + (['FX5-SDCD'] if model.startswith('FX5S-') else []),
        }
        for prefix in ('left', 'right'):
            option = gen.GOT_OPTION.get(values.get(prefix + '_model', '').upper(), {})
            options[prefix + '_module'] = [''] + sorted(option.get('module_interfaces', {}))
        spec = core.cpu_options(kind, model)
        if kind in ('iqrbody', 'mxbody') and spec.get('battery_supported'):
            options['battery'] = ['装着', '非装着', '要確認']
        for key in ('sd_card_model', 'memory_cassette_model', 'memory_card_model'):
            options[key] = [''] + list(spec.get(key + 's', []))
        options['battery_model'] = [''] + (list(spec.get('battery_models', [])) if kind == 'qbody' else [])
        for key in MODEL_KEYS:
            options[key] = sorted(set(part_catalog(key, kind).get(maker, {}).get(series, [])))
        options['communication_mode'] = list(gen.KV_IO.get(model, {}).get('module', {}).get('modes', {}))
        return options

    @_safe
    def page(self, index):
        self._index = int(index)
        page = self._page(index)
        maker, series, catalog = self._scope(page)
        values = {key: _text(page.get(key, '')) for key, _ in core.FIELDS}
        values.update(maker=maker, series=series)
        extra = {k: v for k, v in page.items() if k not in values and k not in MANAGED_KEYS}
        kind = values['kind']
        result = {
            'index': int(index), 'values': values,
            'visible': self._visible(page),
            'settings': core.setting_controls(page),
            'options': self._options(values, maker, series, catalog),
            'extra': json.dumps(extra, ensure_ascii=False, indent=2) if extra else '',
            'summary': core.cpu_summary(kind, values['model']),
            'rack': self._rack(page) if kind in BODY_KINDS else None,
            'wiring_count': len(page.get('wiring', {}).get('connections', [])) + len(page.get('wiring', {}).get('boundaries', [])) if isinstance(page.get('wiring'), dict) else 0,
            'terminal_plan': bool(isinstance(page.get('wiring'), dict) and page['wiring'].get('terminal_plan')),
            'can_csv': kind in self.CSV_KINDS,
            'can_sample': values['model'] in gen.fx_cpu_models() or values['model'].upper() in gen.Q_MIXED or values['model'].upper() in gen.IQR_MIXED or values['model'].upper() in gen.REMOTE_MIXED,
        }
        return result

    @_safe
    def update_page(self, index, values, extra='', changed=''):
        """フォームの値を反映する。changed は直前に変えた欄(メーカー等を変えたら下位の選択を解除)。"""
        page = self._page(index)
        values = {k: _text(v).strip() for k, v in values.items()}
        if values.get('maker') and values['maker'] != self._project_maker():
            raise ValueError('このプロジェクトのメーカーを選択してください')
        if changed == 'maker':
            values['series'] = ''
        if changed in ('maker', 'series'):
            for key in ('kind',) + MODEL_KEYS:
                values[key] = ''
        if changed == 'kind':
            maker, series = values.get('maker', ''), values.get('series', '')
            visible = property_fields(values['kind'])
            for key in MODEL_KEYS:
                if key in visible and values.get(key) and values[key] not in part_catalog(key, values['kind']).get(maker, {}).get(series, []):
                    values[key] = ''
        extra = (extra or '').strip()
        extra_data = json.loads(extra) if extra else {}
        if not isinstance(extra_data, dict):
            raise ValueError('その他の設定は { } で囲んだJSONにしてください')
        known = {k for k, _ in core.FIELDS} | {'maker', 'series'} | set(MANAGED_KEYS)
        overlap = sorted(set(extra_data) & known)
        if overlap:
            raise ValueError('その他の設定に、上の欄と同じ項目があります: ' + ', '.join(overlap))
        hide_sd = values.get('kind') == 'fx5body' and values.get('model', '').upper().startswith('FX5S-') and values.get('board_model') != 'FX5-SDCD'
        result = dict(extra_data)
        result.update({k: v for k, v in values.items() if v and k in known and not (hide_sd and k in ('sd_card', 'sd_card_model'))})
        for key in MANAGED_KEYS:
            if key in page:
                result[key] = page[key]
        kind, model = result.get('kind', ''), result.get('model', '').upper()
        if kind != 'iqrbody':
            result.pop('batteryless', None)
        if kind == 'gotoption':
            for prefix in ('left', 'right'):
                key = prefix + '_module'
                modules = gen.GOT_OPTION.get(result.get(prefix + '_model', '').upper(), {}).get('module_interfaces', {})
                if result.get(key) and result[key] not in modules:
                    if changed == key:
                        raise ValueError('このユニットでは指定した通信モジュールを使用できません')
                    result.pop(key, None)
        specs = {'qbody': gen.Q_CPU, 'iqrbody': gen.iqr_cpu_positions(), 'gotbody': gen.GOT_BODY, 'mxbody': gen.MX_CPU, 'fx5body': gen.FX5U_SPECS}
        if kind in specs and model in specs[kind]:
            visible = self._visible(result)
            options = {'qbody': ('sd_card', 'sd_card_model', 'memory_cassette', 'memory_cassette_model', 'memory_card', 'memory_card_model'),
                       'iqrbody': ('sd_card', 'sd_card_model', 'memory_cassette', 'memory_cassette_model', 'memory_card', 'memory_card_model', 'battery_model', 'batteryless'),
                       'gotbody': ('battery', 'sd_card', 'sd_card_model', 'serial_mode'),
                       'mxbody': ('battery', 'sd_card', 'sd_card_model'),
                       'fx5body': ('board_model', 'board_tag')}[kind]
            for key in options:
                if key not in visible:
                    result.pop(key, None)
            if changed == 'model' and kind in RACK_KINDS:
                spec = specs[kind][model]
                known_sd = {m for cpu in (*gen.Q_CPU.values(), *gen.IQR_CPU.values()) for m in cpu.get('sd_card_models', [])}
                for key in ('sd_card_model', 'memory_cassette_model', 'memory_card_model', 'battery_model'):
                    selected = result.get(key, '')
                    candidates = spec.get(key + 's', [])
                    if selected and (key != 'sd_card_model' or selected.upper() in known_sd) and selected.upper() not in candidates:
                        result.pop(key, None)
        if kind in RACK_KINDS and changed in ('model', 'base_model'):
            self._check_rack_fit(result)
        if kind == 'iqrbody':
            if changed == 'batteryless' and result.get('batteryless') == '有':
                result['memory_cassette'] = '無'
                result.pop('memory_cassette_model', None)
            elif changed == 'memory_cassette' and result.get('memory_cassette') == '有':
                result['batteryless'] = '無'
        if kind == 'fx5body':
            allowed_boards = ['なし'] if model.startswith('FX5UC-') else list(BOARDS) + (['FX5-SDCD'] if model.startswith('FX5S-') else [])
            if result.get('board_model') and result['board_model'] not in allowed_boards:
                if changed == 'board_model':
                    raise ValueError('このCPUでは指定した拡張ボードを使用できません')
                result.pop('board_model', None)
                result.pop('board_tag', None)
            boards = [m for m in result.get('modules', []) if gen.FX5_COMM.get(m.upper(), {}).get('form') == 'board']
            board = result.get('board_model', '')
            if (model.startswith('FX5UC-') and boards) or len(boards) > 1 or (boards and board not in ('', 'なし', boards[0])):
                raise ValueError('このCPUの拡張ボード構成は装着できません。先に追加済みのボードを取り外してください')
        if kind == 'mxbody' and model:
            from renderers.controllers import expansion_items
            expansion_items(result)
        if kind in VENDOR_KINDS and model:
            plc.resolve(result, definitions(), complete=False)
        if kind not in BODY_KINDS:
            for key in ('modules', 'module_tags', 'module_buses', 'module_modes', 'extensions', 'module_starts'):
                result.pop(key, None)
        if result != page:
            self._data['pages'][int(index)] = result
            self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': self._dirty}

    @_safe
    def set_setting_visibility(self, index, key, visible):
        page = self._page(index)
        if type(visible) is not bool or key not in {c['key'] for c in core.setting_controls(page)}:
            raise ValueError('表示を切り替えられない設定欄です')
        page.setdefault('settings_visibility', {})[key] = visible
        self._touch()
        return self.page(index)

    # ------------------------------------------------------------ ユニット構成
    def _stage(self, page, stage):
        stage = int(stage)
        if stage == 0:
            return page
        extensions = page.get('extensions', [])
        if not 1 <= stage <= len(extensions):
            raise ValueError('増設ベースがありません')
        return extensions[stage - 1]

    def _tables(self, kind):
        if kind == 'qbody':
            return gen.Q_CPU, gen.Q_POWER, gen.Q_BASE
        return gen.iqr_cpu_positions(), gen.IQR_POWER, gen.IQR_BASE

    def _capacity(self, page, stage):
        """そのベースに並べられるユニット数(ENCPU のネットワーク部の分を除く)。"""
        if page.get('kind') in LINEAR_KINDS:
            return None
        cpus, _, bases = self._tables(page['kind'])
        config = self._stage(page, stage)
        base = str(config.get('base_model', '')).upper()
        if base not in bases:
            raise ValueError('先にベースを選択してください')
        reserved = cpus.get(str(page.get('model', '')).upper(), {}).get('network_part', {}).get('slots', 0) if int(stage) == 0 else 0
        return bases[base]['slots'] - reserved

    def _check_rack_fit(self, page):
        """ベース・CPU変更でユニットが画面外に隠れる構成は反映しない。"""
        cpus, _, bases = self._tables(page['kind'])
        spec = cpus.get(page.get('model', '').upper(), {})
        extensions = page.get('extensions', [])
        if len(extensions) > spec.get('max_extension_stages', 7):
            raise ValueError('選択したCPUの増設段数を超えています。先に増設ベースを取り外してください')
        slots = sum(bases.get(config.get('base_model', '').upper(), {}).get('slots', 0)
                    for config in [page, *extensions])
        if spec.get('max_module_slots') and slots > spec['max_module_slots']:
            raise ValueError('選択したCPUの合計スロット数を超えています。先にベース構成を変更してください')
        for stage, config in enumerate([page] + list(page.get('extensions', []))):
            base = config.get('base_model', '').upper()
            if base not in bases:
                continue
            offset = cpus.get(page.get('model', '').upper(), {}).get('network_part', {}).get('slots', 0) if stage == 0 else 0
            capacity = bases[base]['slots'] - offset
            for slot, model in enumerate(config.get('modules', [])):
                if model and slot + gen.slot_definition(model.upper(), page['kind'] == 'qbody').get('slots', 1) > capacity:
                    raise ValueError(f'{base} に現在のユニットは収まりません。先に末尾のユニットを移動・取り外してください')

    def _module_info(self, model, is_q):
        model = model.upper()
        points, head = gen.slot_points(model, is_q, 0)
        group = 'empty'
        if model in gen.IO_UNITS and gen.IO_UNITS[model].get('io'):
            group = 'in' if gen.IO_UNITS[model]['io'] == 'in' else 'out'
        elif model in (gen.Q_MIXED if is_q else gen.IQR_MIXED):
            group = 'mixed'
        elif model in (gen.Q_ANALOG if is_q else gen.IQR_ANALOG):
            group = 'analog'
        elif model:
            group = 'comm'
        return {'summary': gen.slot_summary(model, is_q).replace('\n', '・'), 'points': points, 'head': head,
                'group': group, 'slots': gen.slot_definition(model, is_q).get('slots', 1)}

    def _rack(self, page):
        kind = page['kind']
        if kind in VENDOR_KINDS:
            return self._vendor_rack(page)
        if kind == 'mxbody':
            from renderers.controllers import expansion_items
            items = [{'id': 'cpu', 'type': 'cpu', 'head': '本体', 'model': page.get('model', ''),
                      'tag': page.get('tag', ''), 'summary': 'MX-F 本体'}]
            for item in expansion_items(page):
                items.append(dict(id=f"0:{item['slot']}", type='module', stage=0, slot=item['slot'],
                                  head=('左' if item['side'] == 'left' else '右') + str(item['slot'] + 1),
                                  model=item['model'], tag=item['tag'], summary=item['summary'], addr=item['addr'],
                                  points=item['points'], x_start=item.get('x_start'), y_start=item.get('y_start'),
                                  group='analog' if item['spec']['category'] == 'fx5_analog' else 'comm' if item['side'] == 'left' else 'mixed'))
            items = [i for i in items if i['head'].startswith('左')] + items[:1] + [i for i in items if i['head'].startswith('右')]
            items.append(dict(id='0:new', type='add', stage=0, slot=len(page.get('modules', [])), head='追加', model=''))
            return dict(kind=kind, stages=[dict(stage=0, name='本体・拡張・増設', base='', power='', items=items)],
                        io_total=None, slots_used=len(page.get('modules', [])), slots_total=None, message='')
        if kind == 'fx5body':
            items = [{'id': 'cpu', 'type': 'cpu', 'head': '本体', 'model': _text(page.get('model', '')) or '未選択',
                      'tag': _text(page.get('tag', '')), 'summary': 'FX5 CPU'}]
            tags = page.get('module_tags', [])
            for j, model in enumerate(page.get('modules', [])):
                spec = gen.FX5_COMM.get(str(model).upper(), {})
                items.append({'id': f'0:{j}', 'type': 'module', 'stage': 0, 'slot': j, 'head': f'#{j + 1}',
                              'model': model, 'tag': _text(tags[j] if j < len(tags) else ''), 'group': 'comm',
                              'summary': _text(spec.get('network', '')), 'addr': ''})
            items.append({'id': '0:new', 'type': 'add', 'stage': 0, 'slot': len(page.get('modules', [])), 'head': '追加', 'model': ''})
            return {'kind': kind, 'stages': [{'name': '本体・増設', 'base': '', 'power': '', 'items': items}],
                    'io_total': None, 'slots_used': len(page.get('modules', [])), 'slots_total': None, 'message': ''}
        is_q = kind == 'qbody'
        cpus, powers, bases = self._tables(kind)
        cpu = str(page.get('model', '')).upper()
        try:
            empty_points = int(page.get('empty_slot_points', gen.EMPTY_SLOT_POINTS))
        except ValueError:
            empty_points = gen.EMPTY_SLOT_POINTS
        configs = [page] + list(page.get('extensions', []))
        # 先頭XYは図面と同じ計算(gen.slot_assignments)。指定値は直さず、おかしな割付は警告にする
        safe = dict(page, base_model=_text(page.get('base_model', '')), power_model=_text(page.get('power_model', '')),
                    extensions=[dict(e, base_model=_text(e.get('base_model', '')), power_model=_text(e.get('power_model', '')))
                                for e in page.get('extensions', [])])
        assignments, errors, warnings = gen.slot_assignments(safe)
        alarms = errors + warnings + [w for w in gen.page_start_warnings(self._data['pages'])
                                      if any(w.startswith((t + ' ', m + ' ')) for c in configs
                                             for t, m in zip(c.get('module_tags', []) + [''] * 99, c.get('modules', [])) if m)]
        used, total, io_total, slot_no, stages, message = 0, 0, 0, 0, [], ''
        for s, config in enumerate(configs):
            base = str(config.get('base_model', '')).upper()
            power = str(config.get('power_model', '')).upper()
            items = []
            if power or s == 0:
                items.append({'id': f'power:{s}', 'type': 'power', 'stage': s, 'head': '電源', 'model': power or '未選択',
                              'tag': _text(config.get('power_tag', '')), 'summary': _text(powers.get(power, {}).get('supply', ''))})
            if s == 0:
                items.append({'id': 'cpu', 'type': 'cpu', 'stage': 0, 'head': 'CPU', 'model': cpu or '未選択',
                              'tag': _text(page.get('tag', '')), 'summary': 'リモートヘッド' if cpus.get(cpu, {}).get('module_role') == 'remote_head' else ''})
            if base not in bases:
                message = message or ('ベースを選択してください' if not base else f'{base} は対応していないベースです')
                stages.append({'stage': s, 'name': '基本ベース' if s == 0 else f'増設{s}段', 'base': base, 'power': power, 'items': items})
                continue
            slots = bases[base]['slots']
            total += slots
            netpart = cpus.get(cpu, {}).get('network_part') if s == 0 else None
            offset = netpart.get('slots', 1) if netpart else 0
            modules = config.get('modules', [])
            tags = config.get('module_tags', [])
            for i in range(slots):
                assigned = assignments[s][i]
                address = assigned['start']
                if i < offset:
                    points = netpart.get('points', 32)
                    items.append({'id': f'net:{i}', 'type': 'net', 'stage': s, 'head': str(slot_no), 'model': netpart.get('names_by_slot', ['ネットワーク部'] * offset)[i],
                                  'summary': f"{netpart['equivalent']}相当" if netpart.get('equivalent') else '', 'group': 'comm',
                                  'addr': f'X/Y{address:03X}〜{address + points - 1:03X}'})
                    io_total += points
                    used += 1
                    slot_no += 1
                    continue
                j = i - offset
                model = str(modules[j]).upper() if j < len(modules) and modules[j] else ''
                previous = str(modules[j - 1]).upper() if j and j - 1 < len(modules) and modules[j - 1] else ''
                reserved = gen.slot_definition(previous, is_q).get('slots', 1) == 2
                starts = config.get('module_starts', [])
                item = {'id': f'{s}:{j}', 'type': 'module', 'stage': s, 'slot': j, 'head': str(slot_no), 'start': address,
                        'model': model, 'tag': _text(tags[j] if model and j < len(tags) else ''),
                        'manual': assigned['manual'], 'given': _text(starts[j] if j < len(starts) else '').strip(),
                        'auto': f'{address:X}',
                        'alarm': any(f'スロット{slot_no}(' in a or f'スロット{slot_no}の' in a or f'スロット{slot_no}は' in a for a in alarms)}
                if model:
                    info = self._module_info(model, is_q)
                    item.update(group=info['group'], summary=info['summary'], points=info['points'])
                    used += 1
                elif reserved:
                    item.update(type='reserved', group='reserved', summary='2スロット占有', model='占有')
                    used += 1
                else:
                    item.update(group='empty', summary='', model='')
                points, head = (0, '') if reserved else gen.slot_points(model, is_q, empty_points)
                if points:
                    item['addr'] = f'{head}{address:03X}〜{head}{address + points - 1:03X}' if head else f'{address:03X}〜{address + points - 1:03X}'
                    item['points'] = points
                    if model:
                        io_total += points
                slot_no += 1
                items.append(item)
            stages.append({'stage': s, 'name': '基本ベース' if s == 0 else f'増設{s}段', 'base': base, 'power': power,
                           'base_tag': _text(config.get('base_tag', '')), 'power_required': bases[base].get('power_required', True),
                           'items': items})
        spec = cpus.get(cpu, {})
        alarm_targets = []
        for alarm in alarms:
            numbers = set(re.findall(r'スロット(\d+)', alarm))
            targets = [{'id': item['id'], 'label': 'スロット' + item['head'],
                        'field': 'start' if item['type'] == 'module' else ''}
                       for stage in stages for item in stage['items'] if str(item.get('head')) in numbers]
            if not targets:
                stage = next((i for i in range(1, len(stages)) if f'増設{i}段' in alarm), 0)
                targets = [{'id': f'base:{stage}', 'label': stages[stage]['name'], 'field': 'extra'}] if stages else []
            alarm_targets.append({'text': alarm, 'targets': targets})
        return {'kind': kind, 'stages': stages, 'io_total': io_total, 'io_limit': spec.get('io_points'),
                'slots_used': used, 'slots_total': total, 'message': message, 'alarms': alarms, 'alarm_targets': alarm_targets,
                'max_extensions': spec.get('max_extension_stages', 7)}

    def _unit_list(self, config, length):
        modules = list(config.get('modules', []))
        tags = list(config.get('module_tags', []))
        modules += [''] * max(0, length - len(modules))
        tags += [''] * max(0, len(modules) - len(tags))
        return modules, tags[:len(modules)]

    def _store_units(self, config, modules, tags, is_q):
        # 末尾の空きは詰める(2スロットユニットの占有分は残す)
        last = -1
        for j, model in enumerate(modules):
            if model:
                width = 1 if config.get('kind') in VENDOR_KINDS else gen.slot_definition(model.upper(), is_q).get('slots', 1)
                last = max(last, j + width - 1)
        modules, tags = modules[:last + 1], tags[:last + 1]
        if modules:
            config['modules'] = modules
            config['module_tags'] = tags
            for key in ('module_buses', 'module_versions', 'module_modes'):
                if key in config:
                    config[key] = config[key][:len(modules)]
        else:
            config.pop('modules', None)
            config.pop('module_tags', None)
            config.pop('module_buses', None)
            config.pop('module_versions', None)
            config.pop('module_modes', None)

    def _vendor_rack(self, page):
        model = str(page.get('model', '')).upper()
        available = plc.options(model, definitions()) if model else []
        buses = list(dict.fromkeys(option['bus'] for option in available if option['allowed']))
        warnings, conditions = [], []
        try:
            resolved = plc.resolve(page, definitions(), complete=False) if model else None
        except ValueError as error:
            warnings = [str(error)]
            resolved = None
        items = []
        if resolved:
            records = resolved['modules']
            conditions = resolved.get('conditions', [])
            warnings += resolved.get('warnings', [])
        else:
            tags, groups = page.get('module_tags', []), page.get('module_buses', [])
            records = [dict(model=m, tag=tags[i] if i < len(tags) else '', bus=groups[i] if i < len(groups) else '', index=i)
                       for i, m in enumerate(page.get('modules', [])) if m]
            for record in records:
                if not record['bus']:
                    record['bus'] = next((o['bus'] for o in available if o['model'] == record['model']), '')
        next_slot = len(page.get('modules', []))
        order = ('power', 'left', 'x', 'direct', 'legacy', 'nx', 'front')
        extra_buses = list(dict.fromkeys(record['bus'] for record in records if record['bus'] not in order))
        front = []
        for bus in (*order, *extra_buses):
            group = []
            adapters = [a for a in resolved.get('adapters', []) if a['bus'] == bus] if resolved else []
            entries = [(a['before_index'], True, a) for a in adapters]
            entries += [(r['index'], False, r) for r in records if r['bus'] == bus]
            for _, automatic, record in sorted(entries, key=lambda entry: (entry[0], not entry[1])):
                if automatic:
                    group.append(dict(id=f"adapter:{record['model']}:{record['before_index']}", type='adapter',
                                      head='自動', model=record['model'], summary='接続に必要な変換器'))
                    continue
                slot = record['index']
                choices = next((option.get('buses', [option['bus']]) for option in available if option['model'] == record['model']), [bus])
                mode_options = list(gen.KV_IO.get(record['model'], {}).get('module', {}).get('modes', {}))
                modes = page.get('module_modes', [])
                mode = modes[slot] if slot < len(modes) else ''
                group.append(dict(id=f'0:{slot}', type='module', stage=0, slot=slot, head=BUS_NAMES.get(bus, bus) + f' #{slot + 1}',
                                  model=record['model'], tag=record['tag'], bus=bus,
                                  bus_options=[[value, BUS_NAMES.get(value, value)] for value in choices],
                                  mode_options=mode_options, communication_mode=mode,
                                  summary=BUS_NAMES.get(bus, bus), addr='', group='comm'))
            if bus in buses:
                group.append(dict(id='0:new:' + bus, type='add', stage=0, slot=next_slot,
                                  head=BUS_NAMES.get(bus, bus) + ' 追加', model='', bus=bus))
            if bus in ('power', 'left', 'x'):
                items += group
            elif bus == 'front':
                front = group
            else:
                if not any(item['id'] == 'cpu' for item in items):
                    items.append(dict(id='cpu', type='cpu', head='本体', model=model or '未選択', tag=page.get('tag', ''), summary='CPU・カプラ'))
                items += group
        if not any(item['id'] == 'cpu' for item in items):
            items.append(dict(id='cpu', type='cpu', head='本体', model=model or '未選択', tag=page.get('tag', ''), summary='CPU・カプラ'))
        if resolved and resolved.get('end_cover'):
            items.append(dict(id='adapter:end', type='adapter', head='右端', model=resolved['end_cover'], summary='エンドカバー'))
        stages = [dict(stage=0, name='本体・接続ユニット', base='', power='', items=items)]
        if front:
            stages.append(dict(stage=0, name='前面カセット', base='', power='', items=front))
        return dict(kind=page['kind'], stages=stages, io_total=None, slots_used=len(records), slots_total=None,
                    bus_options=[[bus, BUS_NAMES.get(bus, bus)] for bus in buses],
                    message='\n'.join(dict.fromkeys(conditions)), alarms=warnings)

    def _module_models(self, page, slot=None, bus=''):
        if page.get('kind') in VENDOR_KINDS:
            return {option['model'].upper(): option['model'] for option in plc.options(page.get('model', ''), definitions())
                    if option['allowed'] and (not bus or bus in option.get('buses', [option['bus']]))}
        catalog = part_catalog('modules', page.get('kind', ''))
        maker, series, _ = self._scope(page)
        models = {m.upper(): m for m in catalog.get(maker, {}).get(series, [])}
        if page.get('kind') == 'fx5body':
            cpu = page.get('model', '').upper()
            other_board = page.get('board_model') not in (None, '', 'なし') or any(
                gen.FX5_COMM.get(m.upper(), {}).get('form') == 'board'
                for i, m in enumerate(page.get('modules', [])) if m and i != slot)
            if cpu.startswith('FX5UC-') or other_board:
                models = {k: m for k, m in models.items() if gen.FX5_COMM[m.upper()].get('form') != 'board'}
        return models

    @_safe
    def set_module(self, index, stage, slot, model, bus='', communication_mode=None):
        page = self._page(index)
        if communication_mode is not None and not isinstance(communication_mode, str):
            raise ValueError('通信方式は機種の選択肢から指定してください')
        if page.get('kind') not in BODY_KINDS:
            raise ValueError('本体・構成ページで使えます')
        allowed = self._module_models(page, int(slot), bus)
        if str(model).upper() not in allowed:
            raise ValueError(f'{model} はこの構成に追加できません')
        model = allowed[str(model).upper()]
        is_q = page['kind'] == 'qbody'
        config = self._stage(page, stage)
        slot = int(slot)
        capacity = self._capacity(page, stage)
        modules, tags = self._unit_list(config, slot + 1)
        if page['kind'] not in LINEAR_KINDS:
            width = gen.slot_definition(model.upper(), is_q).get('slots', 1)
            if slot + width > capacity:
                raise ValueError(f'{model} は{width}スロットを使うため、この位置には入りません')
            if slot and modules[slot - 1] and gen.slot_definition(modules[slot - 1].upper(), is_q).get('slots', 1) == 2 and not modules[slot]:
                raise ValueError('このスロットは左の2スロットユニットが使っています')
            modules += [''] * max(0, slot + width - len(modules))
            tags += [''] * max(0, len(modules) - len(tags))
            if width == 2 and modules[slot + 1]:
                raise ValueError(f'{model} は2スロットを使います。右隣のスロットを空けてください')
        if not modules[slot]:
            tags[slot] = ''
        previous_model = modules[slot]
        modules[slot] = model
        if page['kind'] in VENDOR_KINDS:
            option = next(o for o in plc.options(page['model'], definitions()) if o['model'] == model)
            buses = list(config.get('module_buses', []))
            buses += [''] * max(0, len(modules) - len(buses))
            buses[slot] = bus or option['bus']
            config['module_buses'] = buses
            versions = config.get('module_versions')
            if isinstance(versions, list):
                config['module_versions'] = (versions + [''] * len(modules))[:len(modules)]
                if previous_model != model:
                    config['module_versions'][slot] = ''
            modes = (config.get('module_modes', []) + [''] * len(modules))[:len(modules)]
            if previous_model != model or communication_mode is not None:
                default_mode = next(iter(gen.KV_IO.get(model, {}).get('module', {}).get('modes', {})), '')
                modes[slot] = default_mode if communication_mode in (None, '') else communication_mode
            if any(modes):
                config['module_modes'] = modes
            else:
                config.pop('module_modes', None)
        elif communication_mode:
            raise ValueError('この構成では通信方式を指定できません')
        self._store_units(config, modules, tags, is_q)
        if page['kind'] in VENDOR_KINDS:
            plc.resolve(page, definitions(), complete=False)
            if communication_mode is not None and modes[slot]:
                for detail in self._existing_pages(model, tags[slot], index, stage, slot):
                    other = self._page(detail['index'])
                    if other['kind'] == 'kv_io':
                        other['communication_mode'] = modes[slot]
        if page['kind'] == 'mxbody':
            from renderers.controllers import expansion_items
            expansion_items(page)
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    @_safe
    def set_module_mode(self, index, stage, slot, communication_mode):
        page = self._page(index)
        slot = int(slot)
        modules = page.get('modules', [])
        if page.get('kind') != 'kvbody' or int(stage) != 0 or not 0 <= slot < len(modules):
            raise ValueError('通信方式を設定するユニットを選択してください')
        model = modules[slot]
        if not gen.KV_IO.get(model, {}).get('module', {}).get('modes'):
            raise ValueError(f'{model}には選択できる通信方式がありません')
        buses = page.get('module_buses', [])
        return self.set_module(index, stage, slot, model, buses[slot] if buses else '', communication_mode)

    @_safe
    def set_module_bus(self, index, stage, slot, bus):
        page = self._page(index)
        if page.get('kind') not in VENDOR_KINDS:
            raise ValueError('キーエンス・オムロンの構成で使えます')
        slot = int(slot)
        modules, _ = self._unit_list(page, 0)
        if not 0 <= slot < len(modules) or not modules[slot]:
            raise ValueError('ユニットがありません')
        buses = list(page.get('module_buses', [''] * len(modules)))
        buses[slot] = str(bus)
        page['module_buses'] = buses
        plc.resolve(page, definitions(), complete=False)
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    @_safe
    def remove_module(self, index, stage, slot):
        page = self._page(index)
        config = self._stage(page, stage)
        modules, tags = self._unit_list(config, 0)
        slot = int(slot)
        if slot >= len(modules) or not modules[slot]:
            raise ValueError('このスロットにユニットはありません')
        if page.get('kind') in LINEAR_KINDS:
            del modules[slot]
            del tags[slot]
            for key in ('module_buses', 'module_versions', 'module_modes'):
                if key in config:
                    del config[key][slot]
        else:
            modules[slot], tags[slot] = '', ''
        self._store_units(config, modules, tags, page.get('kind') == 'qbody')
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    @_safe
    def set_module_tag(self, index, stage, slot, tag):
        page = self._page(index)
        config = self._stage(page, stage)
        modules, tags = self._unit_list(config, 0)
        slot = int(slot)
        if slot >= len(modules) or not modules[slot]:
            raise ValueError('このスロットにユニットはありません')
        tags[slot] = _text(tag).strip()
        config['module_tags'] = tags
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    @_safe
    def set_module_start(self, index, stage, slot, value):
        """スロットの先頭XY(16進)を指定する。空欄は自動。おかしな割付は構成図の警告で知らせ、値は直さない。"""
        page = self._page(index)
        if page.get('kind') not in RACK_KINDS:
            raise ValueError('iQ-R・Q の構成ページで使えます')
        config = self._stage(page, stage)
        value, slot = _text(value).strip(), int(slot)
        if value:
            try:
                if int(value, 16) < 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f'先頭XYは16進数で入力してください: {value}') from None
        starts = list(config.get('module_starts', []))
        starts += [''] * max(0, slot + 1 - len(starts))
        starts[slot] = value
        while starts and not starts[-1]:
            starts.pop()
        if starts:
            config['module_starts'] = starts
        else:
            config.pop('module_starts', None)
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    @_safe
    def set_stage_part(self, index, stage, key, model, tag=None):
        """増設ベースの電源・ベース形名、またはタグを変える(基本ベースはページの欄で変える)。"""
        page = self._page(index)
        if key not in ('base_model', 'power_model'):
            raise ValueError('ベースまたは電源を指定してください')
        candidate = copy.deepcopy(page)
        config = self._stage(candidate, stage)
        if model is not None:
            config[key] = _text(model).strip().upper()
        if tag is not None:
            config[TAG_KEYS[key]] = _text(tag).strip()
            if not config[TAG_KEYS[key]]:
                config.pop(TAG_KEYS[key])
        if candidate.get('kind') in RACK_KINDS:
            self._check_rack_fit(candidate)
        page.clear()
        page.update(candidate)
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    @_safe
    def add_extension(self, index, base, power=''):
        page = self._page(index)
        if page.get('kind') not in RACK_KINDS:
            raise ValueError('iQ-R・Q の構成ページで使えます')
        cpus, powers, bases = self._tables(page['kind'])
        base, power = _text(base).upper(), _text(power).upper()
        if base not in bases or not bases[base].get('extension'):
            raise ValueError('増設ベースを選択してください')
        if bases[base].get('power_required', True) and power not in powers:
            raise ValueError('増設ベースの電源ユニットを選択してください')
        extensions = list(page.get('extensions', []))
        spec = gen.Q_CPU.get(str(page.get('model', '')).upper(), {}) if page['kind'] == 'qbody' else {}
        limit = spec.get('max_extension_stages', 7)
        if len(extensions) >= limit:
            raise ValueError(f'このCPUの増設ベースは{limit}段までです')
        main_base = str(page.get('base_model', '')).upper()
        if main_base not in bases:
            raise ValueError('先に基本ベースを選択してください')
        slots = sum(bases[str(e.get('base_model', '')).upper()]['slots'] for e in extensions) + bases[main_base]['slots'] + bases[base]['slots']
        if spec.get('max_module_slots') and slots > spec['max_module_slots']:
            raise ValueError(f"このCPUの合計スロット数は{spec['max_module_slots']}までです")
        extensions.append({'base_model': base, 'power_model': power if bases[base].get('power_required', True) else '', 'modules': []})
        page['extensions'] = extensions
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    @_safe
    def remove_extension(self, index, stage):
        page = self._page(index)
        self._stage(page, stage)
        del page['extensions'][int(stage) - 1]
        if not page['extensions']:
            page.pop('extensions')
        self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True}

    def _unit_page_kinds(self, model):
        defs = definitions()
        model = model.upper()
        kinds = []
        for kind, categories in core.PAGE_CATEGORIES.items():
            if kind in BODY_KINDS or kind == 'power':
                continue
            for category in categories:
                spec = defs.get(category, {}).get(model)
                if spec is None:
                    continue
                if kind in ('input', 'output') and spec.get('io') != ('in' if kind == 'input' else 'out'):
                    continue
                kinds.append(kind)
                break
        return kinds

    def _slot_number(self, page, stage, slot):
        if page['kind'] in ('mxbody', *VENDOR_KINDS):
            return int(slot) + 1
        cpus, _, bases = self._tables(page['kind'])
        number = cpus.get(str(page.get('model', '')).upper(), {}).get('network_part', {}).get('slots', 0) if page['kind'] not in LINEAR_KINDS else 0
        for config in ([page] + list(page.get('extensions', [])))[:int(stage)]:
            number += bases.get(str(config.get('base_model', '')).upper(), {}).get('slots', 0)
        if page['kind'] in ('qbody', 'iqrbody'):
            modules = self._stage(page, stage).get('modules', [])
            model = str(modules[int(slot)]).upper() if int(slot) < len(modules) else ''
            spec = gen.slot_definition(model, page['kind'] == 'qbody')
            if spec.get('power_ports') and spec.get('slot_io_points') == [16, 32]:
                number += 1  # 前半は外部供給電源。詳細図のスロット番号は後半のネットワーク部。
        return number + int(slot)

    def _side(self, kind):
        return 'right_' if kind in ('qcomm', 'iqrcomm', 'fxcomm', 'gotoption') else ''

    def _existing_pages(self, model, tag, index, stage, slot):
        found = []
        body = self._page(index)
        number = str(self._slot_number(body, stage, slot))
        end = next((i for i in range(int(index) + 1, len(self._data['pages']))
                    if self._data['pages'][i].get('kind') in BODY_KINDS), len(self._data['pages']))
        vendor = body['kind'] in VENDOR_KINDS
        shared_tag = vendor and tag and body.get('module_tags', []).count(tag) > 1
        for i, other in enumerate(self._data['pages']):
            if vendor and not int(index) < i < end:
                continue
            for prefix in ('', 'left_', 'right_'):
                local_number = int(index) < i < end and str(other.get(prefix + 'slot', other.get(prefix + 'unit_no', ''))) == number
                matches = local_number
                if tag:
                    matches = other.get(prefix + 'tag', '') == tag and (not shared_tag or local_number)
                if str(other.get(prefix + 'model', '')).upper() == model.upper() and matches:
                    found.append({'index': i, 'label': f"{i + 1}. {core.KIND_NAMES.get(other.get('kind'), other.get('kind', ''))} {other.get(prefix + 'tag', '')}".strip()})
                    break
        return found

    @_safe
    def unit_pages(self, index, stage, slot):
        """スロットのユニットで作れる図面ページの種類と、既にあるページ。"""
        page = self._page(index)
        modules, tags = self._unit_list(self._stage(page, stage), 0)
        slot = int(slot)
        if slot >= len(modules) or not modules[slot]:
            return {'kinds': [], 'existing': []}
        return {'kinds': [[k, core.KIND_NAMES[k]] for k in self._unit_page_kinds(modules[slot])],
                'existing': self._existing_pages(modules[slot], tags[slot], index, stage, slot)}

    def _unit_page(self, index, stage, slot, kind):
        """スロットのユニットの図面ページ(形名・タグ・スロット番号・先頭アドレス入り)を作り、本体ページの後ろに入れる。"""
        page = self._page(index)
        modules, tags = self._unit_list(self._stage(page, stage), 0)
        slot = int(slot)
        if slot >= len(modules) or not modules[slot]:
            raise ValueError('このスロットにユニットはありません')
        model, tag = modules[slot], tags[slot]
        if kind not in self._unit_page_kinds(model):
            raise ValueError(f'{model} では作れない図面ページです')
        maker, series, _ = self._scope(page)
        side = self._side(kind)
        new = {'kind': kind, side + 'model': model}
        if maker and series:
            new.update(maker=maker, series=series)
        if page['kind'] in VENDOR_KINDS:
            for child_series, models in part_catalog('model', kind).get(maker, {}).items():
                if model in models:
                    new['series'] = child_series
                    break
            modes = page.get('module_modes', [])
            if slot < len(modes) and modes[slot]:
                new['communication_mode'] = modes[slot]
        if tag:
            new[side + 'tag'] = tag
        visible = property_fields(kind, model)
        if page['kind'] not in LINEAR_KINDS and side + 'slot' in visible:
            new[side + 'slot'] = str(self._slot_number(page, stage, slot))
        elif side + 'unit_no' in visible:
            new[side + 'unit_no'] = str(self._slot_number(page, stage, slot))
        if page['kind'] == 'mxbody':
            from renderers.controllers import expansion_items
            assigned = next(item for item in expansion_items(page) if item['slot'] == slot)
            new.update({k: assigned[k] for k in ('x_start', 'y_start') if k in assigned})
            new.update(maker='mitsubishi', series='mx_f' if kind == 'mxio' else 'iq_f')
        if page['kind'] in RACK_KINDS and kind in ('input', 'output', 'qmixed', 'iqrmixed'):
            # 構成図と同じ割付(スロット順に詰める)の先頭アドレス。CSVのアドレスもこれに合わせる
            item = next(i for st in self._rack(page)['stages'] for i in st['items'] if i['id'] == f'{int(stage)}:{slot}')
            new['start'] = f"{item['start']:X}"
        pages = self._data['pages']
        target = int(index) + 1
        while target < len(pages) and pages[target].get('kind') not in BODY_KINDS:
            target += 1
        pages.insert(target, new)
        self._touch()
        return target

    @_safe
    def create_unit_page(self, index, stage, slot, kind):
        target = self._unit_page(index, stage, slot, kind)
        return {'index': target, **self.snapshot()}

    @_safe
    def create_cpu_io_page(self, index):
        page = self._page(index)
        if page.get('kind') in VENDOR_KINDS:
            target, _ = self._vendor_cpu_page(index)
            return dict(index=target, **self.snapshot())
        page = self._page(index)
        if page.get('kind') != 'mxbody':
            raise ValueError('MX-F本体で使えます')
        end = next((i for i in range(int(index) + 1, len(self._data['pages']))
                    if self._data['pages'][i].get('kind') in BODY_KINDS), len(self._data['pages']))
        existing = next((i for i, other in enumerate(self._data['pages'])
                         if other.get('kind') == 'mxio' and other.get('model') == page.get('model')
                         and other.get('tag', '') == page.get('tag', '')
                         and int(index) < i < end), None)
        if existing is not None:
            return dict(index=existing, **self.snapshot())
        target = int(index) + 1
        self._data['pages'].insert(target, dict(kind='mxio', model=page['model'],
                                  tag=page.get('tag', ''), unit_no=page.get('unit_no', '')))
        self._touch()
        return dict(index=target, **self.snapshot())

    def _vendor_cpu_page(self, index):
        page = self._page(index)
        if not page.get('model'):
            raise ValueError('先にCPU・カプラを選択してください')
        end = next((i for i in range(int(index) + 1, len(self._data['pages']))
                    if self._data['pages'][i].get('kind') in BODY_KINDS), len(self._data['pages']))
        model = page['model'].upper()
        kind = 'kv_io' if model in gen.KV_IO else 'unit_diagram'
        for i in range(int(index) + 1, end):
            other = self._data['pages'][i]
            if other.get('kind') == kind and other.get('model') == model and other.get('tag', '') == page.get('tag', ''):
                return i, False
        new = dict(kind=kind, model=model, maker=self._project_maker(), tag=page.get('tag', ''), unit_no=page.get('unit_no', ''))
        self._data['pages'].insert(int(index) + 1, new)
        self._touch()
        return int(index) + 1, True

    @_safe
    def create_all_unit_pages(self, index, with_csv=False):
        """構成のユニットのうち、図面ページがまだ無いものを全部作る(1ユニット1ページ、構成図だけのユニットは除く)。"""
        page = self._page(index)
        if page.get('kind') not in BODY_KINDS:
            raise ValueError('本体・構成ページで使えます')
        if with_csv and not self._path:
            return {'need_save_as': True}
        created, skipped = [], []
        if page['kind'] in VENDOR_KINDS:
            plc.validate(page, definitions())
            target, added = self._vendor_cpu_page(index)
            if added:
                created.append(target)
        for stage, config in enumerate([page] + list(page.get('extensions', []))):
            modules, tags = self._unit_list(config, 0)
            for slot, model in enumerate(modules):
                if not model:
                    continue
                kinds = self._unit_page_kinds(model)
                if not kinds:
                    continue
                if self._existing_pages(model, tags[slot], index, stage, slot):
                    skipped.append(tags[slot] or model)
                    continue
                created.append(self._unit_page(index, stage, slot, kinds[0]))
        messages = []
        if with_csv:
            for target in created:
                if self._data['pages'][target].get('kind') not in self.CSV_KINDS:
                    continue
                result = self.make_page_csv(target)
                if result.get('error'):
                    messages.append(f'{target + 1}ページ目: ' + result['error'])
                elif result.get('message'):
                    messages.append(result['message'])
        text = f'{len(created)}ページを作成しました。' + (f'\n既にページがあるため作らなかったユニット: {", ".join(skipped)}' if skipped else '')
        if messages:
            text += '\n\n' + '\n'.join(messages)
        return {'index': created[0] if created else int(index), 'message': text, **self.snapshot()}

    CSV_KINDS = {'mxio': ('csv',), 'remotepulse': ('csv',), 'input': ('csv',), 'output': ('csv',), 'qmixed': ('input_csv', 'output_csv'), 'iqrmixed': ('input_csv', 'output_csv'),
                 'remotemixed': ('input_csv', 'output_csv'), 'iqranalog': ('csv',), 'qanalog': ('csv',), 'remoteanalog': ('csv',), 'fx5analog': ('csv',)}

    @_safe
    def detail_differences(self):
        """構成との対応が一意な詳細ページだけ修正候補にする。CSVは読み書きしない。"""
        slots = []
        pages = self._data['pages']
        for index, page in enumerate(pages):
            if page.get('kind') not in BODY_KINDS:
                continue
            if page['kind'] in VENDOR_KINDS:
                slots.append(dict(body=index, model=page.get('model', ''), tag=page.get('tag', ''),
                                  number=page.get('unit_no', ''), start=None,
                                  kinds=self._unit_page_kinds(page.get('model', ''))))
            if page['kind'] == 'mxbody':
                slots.append(dict(body=index, model=page['model'], tag=page.get('tag', ''),
                                  number=page.get('unit_no', ''), start=None, kinds=['mxio'], x_start='0', y_start='0'))
            for stage in self._rack(page)['stages']:
                for item in stage['items']:
                    if item['type'] == 'module' and item.get('model'):
                        modes = page.get('module_modes', [])
                        slots.append(dict(body=index, model=item['model'], tag=item.get('tag', ''),
                                          number=str(self._slot_number(page, item['stage'], item['slot'])),
                                          mode=modes[item['slot']] if item['slot'] < len(modes) else '',
                                          start=item.get('start'), kinds=self._unit_page_kinds(item['model']),
                                          x_start=item.get('x_start'), y_start=item.get('y_start')))
        rows = []
        body = None
        detail_kinds = {kind for slot in slots for kind in slot['kinds']}
        detail_kinds.update(('input', 'output', 'qanalog', 'iqranalog', 'qmixed', 'iqrmixed', 'qcomm', 'iqrcomm', 'fxcomm'))
        for index, page in enumerate(pages):
            kind = page.get('kind', '')
            if kind in BODY_KINDS:
                body = index
                continue
            if kind not in detail_kinds:
                continue
            for prefix in ('', 'left_', 'right_'):
                model, tag = page.get(prefix + 'model', ''), page.get(prefix + 'tag', '')
                if not model:
                    continue
                local = [slot for slot in slots if slot['body'] == body]
                tagged = [slot for slot in slots if tag and slot['tag'] == tag]
                number = _text(page.get(prefix + 'slot', page.get(prefix + 'unit_no', '')))
                candidates = tagged if len(tagged) == 1 else [s for s in local if tag and s['tag'] == tag]
                if not candidates:
                    candidates = [s for s in local if s['model'].upper() == model.upper() and number and s['number'] == number]
                if not candidates:
                    candidates = [s for s in local if number and s['number'] == number]
                if not candidates:
                    candidates = [s for s in local if s['model'].upper() == model.upper()]
                row = dict(id=f'{index}:{prefix}', page=index, prefix=prefix,
                           label=f'{index + 1}頁 {tag or model}', actual={}, expected={}, can_sync=False, changes=[])
                if len(candidates) != 1:
                    row['reason'] = '対応する構成ユニットを一意に特定できません'
                    rows.append(row)
                    continue
                slot = candidates[0]
                expected = {prefix + 'model': slot['model'], prefix + 'tag': slot['tag']}
                if kind == 'kv_io' and (slot.get('mode') or model != slot['model'] and page.get('communication_mode')):
                    expected['communication_mode'] = slot.get('mode', '')
                if kind == 'mxio':
                    expected.update({key: slot[key] for key in ('x_start', 'y_start') if slot.get(key) is not None})
                number_key = prefix + ('slot' if gen.is_slot_unit(kind, slot['model']) else 'unit_no')
                expected[number_key] = slot['number']
                if kind in ('input', 'output', 'qmixed', 'iqrmixed') and slot['start'] is not None:
                    expected['start'] = f"{slot['start']:X}"
                actual = {key: _text(page.get(key, '')) for key in expected}
                same_starts = set()
                for key in ('start', 'x_start', 'y_start'):
                    if key not in actual:
                        continue
                    try:
                        if int(actual[key] or ('0' if key != 'start' else ''), 16) == int(expected[key], 16):
                            same_starts.add(key)
                    except ValueError:
                        pass
                labels = {prefix + 'model': '形名', prefix + 'tag': 'タグ', number_key: '番号', 'start': '先頭XY',
                          'x_start': '入力開始', 'y_start': '出力開始', 'communication_mode': '通信方式'}
                changes = [dict(key=key, label=labels[key], before=actual[key], after=value)
                           for key, value in expected.items() if actual[key] != value and key not in same_starts]
                if not changes and kind in slot['kinds']:
                    continue
                row.update(body=slot['body'], actual=actual, expected=expected, changes=changes,
                           can_sync=kind in slot['kinds'], reason='' if kind in slot['kinds'] else '構成ユニットに合うページ種類を作成してください')
                rows.append(row)
        return {'rows': rows}

    @_safe
    def sync_details(self, requests):
        if not isinstance(requests, list) or not requests or any(not isinstance(row, dict) for row in requests):
            raise ValueError('修正する差分を選んでください')
        current = {row['id']: row for row in self.detail_differences()['rows']}
        for request in requests:
            row = current.get(request.get('id'))
            if row != request or not row.get('can_sync'):
                raise ValueError('構成またはページが変わりました。差分一覧を開き直してください')
        for request in requests:
            page = self._page(request['page'])
            page.update(request['expected'])
            prefix = request['prefix']
            other_number = prefix + ('unit_no' if prefix + 'slot' in request['expected'] else 'slot')
            page.pop(other_number, None)
        self._touch()
        return self.snapshot()

    @_safe
    def open_csv(self, index, key):
        if key not in ('csv', 'input_csv', 'output_csv'):
            raise ValueError('CSVの項目を指定してください')
        name = self._page(index).get(key, '')
        if not name:
            raise ValueError('CSVを指定してください')
        path = Path(name)
        if not path.is_absolute():
            if not self._path:
                raise ValueError('相対パスのCSVを開く前にプロジェクトを保存してください')
            path = self._path.parent / path
        path = path.resolve()
        if path.suffix.lower() != '.csv' or not path.is_file():
            raise ValueError(f'CSVファイルが見つかりません: {path}')
        result = self.open_file(str(path))
        if result.get('error'):
            return result
        return {'ok': True, 'path': str(path)}

    @_safe
    def make_page_csv(self, index):
        """ページの入出力CSV(アドレス入り・信号名は空欄)を作り、ページに指定する。既にあるファイルは上書きしない。"""
        page = self._page(index)
        kind = page.get('kind', '')
        if kind not in self.CSV_KINDS:
            raise ValueError('入出力・混合・アナログのページで使えます')
        if not self._path:
            return {'need_save_as': True}
        model = str(page.get('model', '')).upper()
        if not model:
            raise ValueError('形名を選択してください')
        name = re.sub(r'[<>:"/\\|?*\s]+', '_', page.get('tag') or model)
        files, notes = [], []
        used = {(self._path.parent / other[key]).resolve()
                for other in self._data['pages'] if other is not page
                for key in self.CSV_KINDS.get(other.get('kind'), ()) if other.get(key)}
        for key in self.CSV_KINDS[kind]:
            suffix = {'input_csv': '_in', 'output_csv': '_out'}.get(key, '')
            target = self._path.parent / f'{name}{suffix}.csv'
            if page.get(key):
                notes.append(f'{page[key]} は指定済みです')
                continue
            number = 2
            while target.resolve() in used:
                target = self._path.parent / f'{name}_{number}{suffix}.csv'
                number += 1
            if target.exists():
                notes.append(f'{target.name} は既にあるため、上書きせずに指定しました')
            else:
                if kind in ('mxio', 'remotepulse'):
                    from renderers.terminal_pages import terminal_rows
                    spec = (gen.MX_IO if kind == 'mxio' else gen.REMOTE_PULSE)[page['model'].upper()]
                    header = ['No.', '端子', '信号', '用途']
                    rows = [[i, row['terminal'] if kind == 'mxio' else row.get('pin', ''), row['signal'], row.get('description', '')] for i, row in enumerate(terminal_rows(page, spec), 1)]
                elif kind.endswith('analog'):
                    specs = {'iqranalog': gen.IQR_ANALOG, 'qanalog': gen.Q_ANALOG, 'remoteanalog': gen.REMOTE_ANALOG, 'fx5analog': gen.FX5_ANALOG_SPECS}[kind]
                    if model not in specs:
                        raise ValueError(f'未対応のアナログ機種です: {model}')
                    header = ('CH', '用途', '方式', '機器番号')
                    rows = [[str(ch), '', '', ''] for ch in range(1, len(specs[model]['channels']) + 1)]
                else:
                    unit = dict(page, model=model)
                    if key != 'csv':
                        direction = 'in' if key == 'input_csv' else 'out'
                        unit = next(uc for uc, _ in gen.iqr_units(unit, {'in': [], 'out': []}) if uc['_mixed_io'] == direction)
                    elif model not in gen.IO_UNITS:
                        raise ValueError(f'対応済みの入出力ユニットを指定してください: {model}')
                    header = gen.IO_COLUMNS[gen.configured_unit(unit)['io']]
                    rows = [[address] + [''] * (len(header) - 1) for address in gen.unit_addrs(unit)]
                with open(target, 'w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(header)
                    writer.writerows(rows)
                files.append(target.name)
            page[key] = target.name
        self._touch()
        message = ('作成: ' + '、'.join(files)) if files else ''
        if notes:
            message = '\n'.join(filter(None, [message] + notes))
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': True, 'message': message}

    # ------------------------------------------------------------ 部品の一覧
    def _describe(self, category, spec, model):
        is_q = category.startswith('q_')
        if category in ('iqr_q', 'iqr_analog', 'iqr_comm', 'iqr_mixed', 'q_analog', 'q_comm', 'q_mixed') or model in gen.IO_UNITS:
            text = gen.slot_summary(model, is_q).replace('\n', '・')
            if text:
                return text
        if 'io' in spec and 'points' in spec:
            return ('入力' if spec['io'] == 'in' else '出力') + f"{spec['points']}点"
        if category.endswith('_base'):
            return f"{spec.get('slots', '')}スロット" + ('（増設）' if spec.get('extension') else '')
        if category.endswith('_power'):
            return f"{spec.get('supply', '')}電源" + ('・DC24V出力あり' if spec.get('service_24v') else '')
        if category == 'q_cpu':
            return f"{spec.get('program_capacity_ksteps', '')}Kステップ・I/O {spec.get('io_points', '')}点"
        if category == 'got_body':
            display = spec.get('display', '')
            screen = display.get('screen', '') if isinstance(display, dict) else display
            if not screen and spec.get('screen_size_inch'):
                screen = f"{spec['screen_size_inch']}型"
            resolution = spec.get('resolution') or (display.get('resolution', '') if isinstance(display, dict) else '')
            power = spec.get('power', {})
            supply = (power.get('voltage') or power.get('supply', '')) if isinstance(power, dict) else power
            return ' / '.join(_text(value) for value in (screen, resolution, supply) if value)
        if category == 'got_option':
            return _text(spec.get('option_type', ''))
        if category in ('standard_device', 'power_supply'):
            return ' '.join(filter(None, (_text(spec.get('display_ratings', '')), _text(spec.get('part_type', '')))))[:60]
        if category in ('iqr_cpu', 'mx_cpu') and model.startswith(('MXR', 'MXF')):
            return f"{spec['max_axes']}軸 / {spec['program_memory_mb']}MB / USB Type-C"
        if category == 'inverter':
            return f"{spec['supply']} / ND {spec['capacity_kw']:g}kW / {spec['function']}"
        if category == 'remote_pulse':
            return spec.get('function', 'パルス')
        if category == 'remote_analog':
            return f"{spec['network']} / アナログ {len(spec['channels'])}CH"
        if 'network' in spec:
            return _text(spec['network'])
        if 'channels' in spec:
            channels = spec['channels']
            return f"アナログ {len(channels) if isinstance(channels, (list, dict)) else channels}ch"
        if 'inputs' in spec or 'outputs' in spec:
            def count(value):
                return value.get('points', '') if isinstance(value, dict) else len(value) if isinstance(value, list) else value
            return f"入力{count(spec.get('inputs', ''))}・出力{count(spec.get('outputs', ''))}"
        return ''

    def _part_index(self):
        if getattr(self, '_parts', None) is None:
            defs = definitions()
            index = {}
            for path in core.PARTS_ROOT.rglob('*.json'):
                try:
                    with path.open(encoding='utf-8-sig') as f:
                        item = json.load(f)
                except (OSError, ValueError):
                    continue
                model, category = item.get('model'), item.get('category')
                if not isinstance(model, str) or category not in defs or model.upper() not in defs[category]:
                    continue
                relative = path.relative_to(core.PARTS_ROOT).parts
                group = relative[3] if len(relative) >= 5 else ''
                index.setdefault(model.upper(), {'category': category, 'group': GROUP_NAMES.get(group, group),
                                                 'production_end': production_end_label(defs[category][model.upper()]),
                                                 'summary': self._describe(category, defs[category][model.upper()], model.upper())})
            self._parts = index
        return self._parts

    @_safe
    def catalog(self, key, index=None, stage=0, bus=''):
        """選定ダイアログの一覧。key: modules / model / power_model / base_model / extension_base_model /
        left_model / right_model / standard_model。ページの種類・メーカー・シリーズで絞る。"""
        page = self._page(index) if index is not None and key != 'standard_model' else {}
        kind = page.get('kind', '')
        if key == 'modules' and kind in VENDOR_KINDS:
            maker = 'keyence' if kind == 'kvbody' else 'omron'
            rows = []
            for option in plc.options(page.get('model', ''), definitions()):
                if not option['allowed'] or (bus and bus not in option.get('buses', [option['bus']])):
                    continue
                rows.append(dict(model=option['model'], maker=core.MAKER_NAMES[maker],
                                 series=BUS_NAMES.get(option['bus'], option['bus']),
                                 group=BUS_NAMES.get(option['bus'], option['bus']), bus=option['bus'],
                                 summary=' / '.join(option.get('conditions', [])), production_end='',
                                 slots=1, points='', pages='・'.join(core.KIND_NAMES[k] for k in self._unit_page_kinds(option['model']))))
            return {'key': key, 'rows': rows}
        catalog = part_catalog(key, kind)
        if key != 'standard_model' and page:
            maker, series, _ = self._scope(page)
            catalog = {maker: {series: catalog.get(maker, {}).get(series, [])}} if catalog.get(maker, {}).get(series) else {}
        parts = self._part_index()
        is_q = kind == 'qbody'
        rows = []
        for maker, series_map in sorted(catalog.items()):
            for series, models in sorted(series_map.items()):
                for model in models:
                    if key == 'modules' and kind == 'fx5body' and model.upper() not in self._module_models(page):
                        continue
                    info = parts.get(model.upper(), {})
                    row = {'model': model, 'maker': core.MAKER_NAMES.get(maker, maker), 'series': core.SERIES_NAMES.get(series, series),
                           'group': info.get('group') or core.SERIES_NAMES.get(series, series), 'summary': info.get('summary', ''),
                           'production_end': info.get('production_end', ''),
                           'slots': 1, 'points': '', 'pages': ''}
                    if key == 'modules' and kind in RACK_KINDS:
                        module = self._module_info(model, is_q)
                        row.update(slots=module['slots'], points=f"{module['points']}点", group=row['group'] or module['group'])
                    if key == 'modules':
                        row['pages'] = '・'.join(core.KIND_NAMES[k] for k in self._unit_page_kinds(model))
                    rows.append(row)
        if key == 'extension_base_model' and kind == 'qbody':
            spec = gen.Q_CPU.get(str(page.get('model', '')).upper(), {})
            extensions = page.get('extensions', [])
            used = gen.Q_BASE.get(str(page.get('base_model', '')).upper(), {}).get('slots', 0) + sum(gen.Q_BASE.get(str(e.get('base_model', '')).upper(), {}).get('slots', 0) for e in extensions)
            rows = [r for r in rows if len(extensions) < spec.get('max_extension_stages', 7) and used + gen.Q_BASE[r['model'].upper()]['slots'] <= spec.get('max_module_slots', 10000)]
        if key in ('extension_base_model',):
            bases = gen.Q_BASE if kind == 'qbody' else gen.IQR_BASE
            for r in rows:
                r['power_required'] = bases.get(r['model'].upper(), {}).get('power_required', True)
        return {'key': key, 'rows': rows}

    # ------------------------------------------------------------ 配線情報
    @_safe
    def wiring(self, index):
        page = self._page(index)
        name = page.get('title') or page.get('tag') or page.get('model') or f'ページ {int(index) + 1}'
        return {'name': name, 'value': normalize_wiring(page.get('wiring')),
                'content_fields': CONTENT_FIELDS, 'position_fields': POSITION_FIELDS,
                'defaults': {'boundaries': BOUNDARY_DEFAULTS, 'connections': CONNECTION_DEFAULTS}}

    @_safe
    def set_wiring(self, index, value):
        page = self._page(index)
        value = normalize_wiring(value)
        previous = page.get('wiring')
        if value['boundaries'] or value['connections'] or value['terminal_plan']:
            page['wiring'] = value
        else:
            page.pop('wiring', None)
        if page.get('wiring') != previous:
            self._touch()
        return {**self.page(index), 'pages': self.snapshot()['pages'], 'dirty': self._dirty}

    @_safe
    def pick_csv(self, path=None):
        """CSVを選ぶ。プロジェクトと同じドライブなら、JSONのフォルダからの相対パスにする。"""
        path = self._ask('open', 'CSVを選択', path, types=('CSV (*.csv)',))
        if self._path and os.path.splitdrive(str(path))[0].lower() == os.path.splitdrive(str(self._path))[0].lower():
            return {'path': os.path.relpath(path, self._path.parent)}
        return {'path': str(path)}

    # ------------------------------------------------------------ 出力
    @_safe
    def generate_kv(self, series, model, unit_no='', tag='', out=None, communication_mode='', settings=None):
        model = str(model).upper()
        spec = gen.KV_IO.get(model)
        if spec is None and gen.UNIT_DIAGRAMS.get(model, {}).get('manufacturer') == 'keyence':
            spec = gen.UNIT_DIAGRAMS[model]
        if not spec or series not in spec['series']:
            raise ValueError('選択したシリーズのユニットを指定してください')
        title = 'VTタッチパネル図面の保存先' if spec.get('function') == 'タッチパネル' else 'KVユニット図面の保存先'
        path = self._ask('save', title, out, model + '.qet', ('QET図面 (*.qet)',))
        if path.suffix.lower() != '.qet':
            path = path.with_suffix('.qet')
        allowed = {key for label, key in spec.get('module', {}).get('settings', [])}
        if settings is not None and (not isinstance(settings, dict) or
                                    any(key not in allowed or not isinstance(value, str) for key, value in settings.items())):
            raise ValueError('このユニットの設定項目を文字列で指定してください')
        page = dict(kind='kv_io' if model in gen.KV_IO else 'unit_diagram', model=model,
                    unit_no=unit_no, tag=tag, communication_mode=communication_mode)
        page.update(settings or {})
        config = dict(project_title=series + ' ユニット図', front_pages=False)
        return self._export_diagrams(path, config, [(page, None)])

    @_safe
    def generate_nx(self, model, unit_no='', tag='', out=None):
        model = str(model).upper()
        if gen.UNIT_DIAGRAMS.get(model, {}).get('manufacturer') != 'omron':
            raise ValueError('対応するオムロンの機種を選択してください')
        panel = gen.UNIT_DIAGRAMS[model].get('function') == 'タッチパネル'
        title = 'NAタッチパネル図面の保存先' if panel else 'NXユニット図面の保存先'
        path = self._ask('save', title, out, model + '.qet', ('QET図面 (*.qet)',))
        if path.suffix.lower() != '.qet':
            path = path.with_suffix('.qet')
        page = dict(kind='unit_diagram', model=model, unit_no=unit_no, tag=tag)
        config = dict(project_title='オムロンNA タッチパネル図' if panel else 'オムロンNX ユニット図', front_pages=False)
        return self._export_diagrams(path, config, [(page, None)])

    @_safe
    def generate_terminal_block(self, model, plc_model, cable, plc_tag, block_tag, cable_tag, out=None, extra=None):
        pages = gen.terminal_block_project_pages(model, plc_model, cable, plc_tag, block_tag, cable_tag, **(extra or {}))
        path = self._ask('save', 'I/O図・中継端子台図の保存先', out, model + '.qet', ('QET図面 (*.qet)',))
        if path.suffix.lower() != '.qet':
            path = path.with_suffix('.qet')
        return self._export_diagrams(path, dict(project_title=plc_model + ' I/O・中継端子台図', front_pages=False), pages)

    def _export_diagrams(self, path, config, pages):
        project, _ = gen.build_project(config, pages)
        with tempfile.TemporaryDirectory(dir=path.parent) as folder:
            temporary = Path(folder) / 'unit.qet'
            gen.ET.ElementTree(project).write(temporary, encoding='utf-8')
            os.replace(temporary, path)
        return {'ok': True, 'out': str(path)}

    def _run(self, *args):
        return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})

    @_safe
    def generate_configuration(self, include_details=True, out=None, confirmed=False):
        pages = self._data['pages']
        bodies = [i for i, p in enumerate(pages) if p.get('kind') in VENDOR_KINDS]
        if not bodies:
            raise ValueError('キーエンスまたはオムロンのPLC構成を選んでください')
        stem = self._path.stem if self._path else pages[bodies[0]]['model']
        name = stem + ('' if include_details else '_構成') + '.qet'
        target = self._ask('save', '図面の保存先', out, name, ('QET図面 (*.qet)',)).with_suffix('.qet')
        selected = pages[self._index] if self._index is not None and self._index < len(pages) else None
        config = gen.project_config(self._data)
        if not include_details:
            config.update(pages=[pages[i] for i in bodies], front_pages=False)
        outputs = [target, target.with_name(target.stem + '_iolist.csv')]
        if terminal_rows([(p, None) for p in config['pages']]):
            outputs.append(target.with_name(target.stem + '_terminals.csv'))
        existing = [str(path) for path in outputs if path.exists()]
        if existing and not confirmed:
            return {'confirm': '次のファイルを上書きします。\n' + '\n'.join(existing), 'out': str(target)}

        before_count = len(pages)
        if include_details:
            # 後ろの本体から展開し、詳細ページ挿入で他の本体の参照位置をずらさない。
            for i in reversed(bodies):
                result = self.create_all_unit_pages(i)
                if result.get('error'):
                    raise ValueError(result['error'])
        # 生成元JSONと同じ場所で相対CSVを解決し、QET・付属帳票は全て完成後に公開する。
        folder = self._path.parent if self._path else ROOT
        with tempfile.TemporaryDirectory(dir=target.parent) as work:
            stage = Path(work)
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=folder, suffix='.json', delete=False) as stream:
                source = Path(stream.name)
            try:
                source.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
                result = self._run(ROOT / 'gen_io_page.py', source, stage / target.name)
                if result.returncode:
                    raise ValueError((result.stdout + result.stderr).strip())
            finally:
                source.unlink(missing_ok=True)
            backups = {}
            for path in outputs:
                if not (stage / path.name).is_file():
                    raise ValueError(f'生成されなかったファイル: {path.name}')
                if path.exists():
                    backups[path] = stage / (path.name + '.bak')
                    shutil.copy2(path, backups[path])
            published = []
            try:
                for path in outputs:
                    os.replace(stage / path.name, path)
                    published.append(path)
            except OSError:
                for path in reversed(published):
                    if path in backups:
                        os.replace(backups[path], path)
                    else:
                        path.unlink()
                raise
        self._index = next((i for i, p in enumerate(pages) if p is selected), None)
        added = len(pages) - before_count
        message = result.stdout.strip()
        for path in outputs:
            message = message.replace(str(stage / path.name), str(path))
        if added:
            message = f'プロジェクトに不足していた詳細ページを{added}件追加しました。\n' + message
        return {'ok': True, 'index': self._index, 'out': str(target), 'message': message, **self.snapshot()}

    @_safe
    def generate(self, out=None, confirmed=False):
        if not self._path:
            return {'need_save_as': True}
        self._write(self._path)
        self._dirty = False
        out = self._ask('save', '図面の保存先', out, self._path.stem + '.qet', ('QET図面 (*.qet)',))
        if out.suffix.lower() != '.qet':
            out = out.with_suffix('.qet')
        suffixes = ['_iolist.csv']
        if terminal_rows([(page, None) for page in self._data['pages']]):
            suffixes.append('_terminals.csv')
        base = out.with_suffix('').as_posix()
        existing = [base + suffix for suffix in suffixes if Path(base + suffix).exists()]
        if existing and not confirmed:
            return {'confirm': '次の一覧も上書きします。\n' + '\n'.join(existing), 'out': str(out)}
        result = self._run(ROOT / 'gen_io_page.py', self._path, out)
        if result.returncode:
            return {'error': (result.stdout + result.stderr).strip(), 'snapshot': self.snapshot()}
        return {'ok': True, 'message': result.stdout.strip(), 'out': str(out), 'snapshot': self.snapshot()}

    @_safe
    def check(self):
        """保存せずに、生成と同じ検査を一時ファイルで行う。"""
        for i, page in enumerate(self._data['pages'], 1):
            if not page.get('kind'):
                raise ValueError(f'{i}ページ目の種類を選択してください')
        if not self._data['pages']:
            raise ValueError('ページがありません')
        folder = self._path.parent if self._path else ROOT
        with tempfile.TemporaryDirectory() as work:
            config = None
            try:
                with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=folder, prefix='.check_', suffix='.json', delete=False) as stream:
                    config = Path(stream.name)
                    json.dump(gen.project_config(self._data), stream, ensure_ascii=False)
                result = self._run(ROOT / 'gen_io_page.py', config, Path(work) / 'check.qet')
            finally:
                if config is not None:
                    config.unlink(missing_ok=True)
        if result.returncode:
            return {'error': (result.stdout + result.stderr).strip()}
        lines = [line for line in result.stdout.splitlines() if not line.startswith(('出力:', '帳票:', '端子台接続表:'))]
        return {'ok': True, 'message': 'エラーはありません\n' + '\n'.join(lines).strip()}

    @_safe
    def open_file(self, path):
        if sys.platform == 'win32':
            os.startfile(path)
        else:
            raise ValueError('このOSでは開けません: ' + path)

    @_safe
    def make_sample(self, index, path=None, confirmed=False):
        model = _text(self._page(index).get('model', '')).strip()
        if model not in gen.fx_cpu_models() and model.upper() not in gen.Q_MIXED and model.upper() not in gen.IQR_MIXED and model.upper() not in gen.REMOTE_MIXED:
            raise ValueError('FX5本体または混合入出力の形名を選んだページで使えます')
        path = self._ask('save', 'CSV雛形の保存先', path, model.replace('/', '-') + '.json')
        base = str(path.with_suffix(''))
        existing = [base + s for s in ('.json', '_in.csv', '_out.csv') if Path(base + s).exists()]
        if existing and not confirmed:
            return {'confirm': '次のファイルを上書きしますか？\n' + '\n'.join(existing), 'path': str(path)}
        result = self._run(ROOT / 'tools' / 'make_sample.py', model, base)
        if result.returncode:
            return {'error': (result.stdout + result.stderr).strip()}
        return {'ok': True, 'message': result.stdout.strip()}

    @_safe
    def part_options(self, model):
        defs = definitions()
        spec = defs['standard_device'].get(model.upper(), defs['power_supply'].get(model.upper()))
        if spec is None:
            raise ValueError('書出しに対応していない部品です: ' + model)
        auxiliary = [[o['id'], o.get('label', o.get('name', o['id']))] for o in spec.get('auxiliary_options', [])] if spec.get('auxiliary_selection_required') else []
        configuration = [[o['id'], o.get('label', o.get('name', o['id']))] for o in spec.get('configuration_options', [])]
        return {'model': model, 'auxiliary': auxiliary, 'default_auxiliary': spec.get('default_auxiliary_option'),
                'configuration': configuration}

    @_safe
    def register_all_parts(self):
        from tools.qet_collection import register_all_parts
        return register_all_parts()

    @_safe
    def register_part(self, model, auxiliary=None, configuration=None):
        from tools.qet_collection import register_part
        options = self.part_options(model)
        if 'error' in options:
            return options
        if options['auxiliary'] and not auxiliary:
            raise ValueError('補助接点構成を選択してください')
        if options['configuration'] and not configuration:
            raise ValueError('動作構成を選択してください')
        paths = register_part(model, auxiliary or options['default_auxiliary'], configuration or None)
        return {'ok': True, 'paths': [str(p) for p in paths],
                'message': f'{len(paths)}部品をQETに登録しました。\n{paths[0].parent}\nQETのユーザーコレクションを更新するか、QETを再起動してください。'}

    @_safe
    def export_part(self, model, auxiliary=None, configuration=None, folder=None):
        options = self.part_options(model)
        if 'error' in options:
            return options
        if options['auxiliary'] and not auxiliary:
            raise ValueError('補助接点構成を選択してください')
        if options['configuration'] and not configuration:
            raise ValueError('動作構成を選択してください')
        folder = self._ask('folder', '部品の書出し先（QETのユーザーコレクション等）', folder)
        paths = core.export_part(model, folder, auxiliary or options['default_auxiliary'], configuration or None)
        return {'ok': True, 'message': f'{len(paths)}部品を書き出しました。\n{paths[0].parent}\n定格・設定を確認して使用してください。コイルと接点がある機器はQETで関連付けてください。'}

    @_safe
    def update_xrefs(self, source=None, output=None):
        from tools.update_xrefs import update_file
        source = self._ask('open', 'QETで保存した図面を選択', source, types=('QET図面 (*.qet)',))
        output = self._ask('save', '参照表更新後の保存先', output, source.stem + '_xref.qet', ('QET図面 (*.qet)',))
        path, count = update_file(source, output)
        return {'ok': True, 'message': f'{count}個のa・b接点表を更新しました。\n{path}\nQETで更新後のファイルを開いてください。'}
