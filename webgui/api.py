"""Web GUIの公開APIとプロジェクト状態。"""
from .api_common import (copy, csv, json, re, os, shutil, subprocess, sys, tempfile, date, Path, gen, core, plc, BOUNDARY_DEFAULTS, CONNECTION_DEFAULTS, CONTENT_FIELDS, POSITION_FIELDS, normalize_wiring, terminal_rows, ROOT, BUS_NAMES, production_end_label, VENDOR_KINDS, BODY_KINDS, LINEAR_KINDS, RACK_KINDS, MODEL_KEYS, TAG_KEYS, MANAGED_KEYS, PROJECT_FIELDS, GROUP_NAMES, BOARDS, Cancelled, EDIT_METHODS, _safe, _text, _CACHE, _cached, part_catalog, definitions, property_fields, series_kinds)
from .api_pages import PagesApi
from .api_configuration import ConfigurationApi
from .api_parts import PartsApi
from .api_wiring import WiringApi
from .api_exports import ExportsApi

class Api(PagesApi, ConfigurationApi, PartsApi, WiringApi, ExportsApi):
    CSV_KINDS = {'mxio': ('csv',), 'remotepulse': ('csv',), 'input': ('csv',), 'output': ('csv',), 'qmixed': ('input_csv', 'output_csv'), 'iqrmixed': ('input_csv', 'output_csv'),
                 'remotemixed': ('input_csv', 'output_csv'), 'iqranalog': ('csv',), 'qanalog': ('csv',), 'remoteanalog': ('csv',), 'fx5analog': ('csv',)}

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
        json.dumps(data, ensure_ascii=False).encode('utf-8')
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


    @_safe
    def pick_csv(self, path=None):
        """CSVを選ぶ。プロジェクトと同じドライブなら、JSONのフォルダからの相対パスにする。"""
        path = self._ask('open', 'CSVを選択', path, types=('CSV (*.csv)',))
        if self._path and os.path.splitdrive(str(path))[0].lower() == os.path.splitdrive(str(self._path))[0].lower():
            return {'path': os.path.relpath(path, self._path.parent)}
        return {'path': str(path)}
