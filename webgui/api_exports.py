"""Web GUIのexports処理。"""
from .api_common import (json, os, shutil, subprocess, sys, tempfile, Path, gen, terminal_rows, ROOT, VENDOR_KINDS, _safe, _text)

class ExportsApi:
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
    def update_xrefs(self, source=None, output=None):
        from tools.update_xrefs import update_file
        source = self._ask('open', 'QETで保存した図面を選択', source, types=('QET図面 (*.qet)',))
        output = self._ask('save', '参照表更新後の保存先', output, source.stem + '_xref.qet', ('QET図面 (*.qet)',))
        path, count = update_file(source, output)
        return {'ok': True, 'message': f'{count}個のa・b接点表を更新しました。\n{path}\nQETで更新後のファイルを開いてください。'}
