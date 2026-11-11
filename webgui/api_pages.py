"""Web GUIのpages処理。"""
from .api_common import (copy, json, gen, core, plc, VENDOR_KINDS, BODY_KINDS, RACK_KINDS, MODEL_KEYS, MANAGED_KEYS, BOARDS, _safe, _text, part_catalog, definitions, property_fields, series_kinds)

class PagesApi:
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
        """ページのメーカー・シリーズ。未指定なら形名から推定する。"""
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
