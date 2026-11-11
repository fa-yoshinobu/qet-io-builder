"""Web GUIのconfiguration処理。"""
from .api_common import (copy, re, gen, core, plc, BUS_NAMES, VENDOR_KINDS, BODY_KINDS, LINEAR_KINDS, RACK_KINDS, TAG_KEYS, _safe, _text, part_catalog, definitions, property_fields)

class ConfigurationApi:
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
