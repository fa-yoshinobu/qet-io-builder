"""Web GUIのparts処理。"""
from .api_common import (json, gen, core, plc, BUS_NAMES, production_end_label, VENDOR_KINDS, RACK_KINDS, GROUP_NAMES, _safe, _text, part_catalog, definitions)

class PartsApi:
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
