import json
import os
import re
import subprocess
import sys
import tempfile
import tkinter as tk
import tomllib
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import gen_io_page as gen

from gui_core import (ROOT, PARTS_ROOT, MAKER_NAMES, SERIES_NAMES, KIND_NAMES, PAGE_CATEGORIES, FIELDS,
                      part_catalog, series_kinds, export_part, cpu_options, property_fields, cpu_summary, setting_controls, page_property_fields)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PLC・GOT 図面生成')
        self.geometry('1000x720')
        self.path = None
        self.data = gen.project_config({'pages': [], 'front_pages': False})
        self.index = None
        self.loading = False
        self.dirty = False
        bar = ttk.Frame(self, padding=6); bar.pack(fill='x')
        for label, command in [('開く', self.open), ('保存', self.save), ('名前を付けて保存', self.save_as),
                               ('図面生成', self.generate), ('CSV雛形作成', self.sample), ('QETに登録', lambda: self.export_standard_parts(True)), ('全部QETに登録', self.register_all_parts), ('部品を書出し', self.export_standard_parts), ('参照表を更新', self.update_xrefs)]:
            ttk.Button(bar, text=label, command=command).pack(side='left', padx=3)
        self.location = ttk.Label(self, text='ファイル未選択'); self.location.pack(anchor='w', padx=8)
        body = ttk.Panedwindow(self, orient='horizontal'); body.pack(fill='both', expand=True, padx=8, pady=6)
        left = ttk.Frame(body); body.add(left, weight=1)
        right = ttk.Frame(body); body.add(right, weight=3)
        ttk.Label(left, text='ページ').pack(anchor='w')
        self.pages = tk.Listbox(left, exportselection=False); self.pages.pack(fill='both', expand=True)
        self.pages.bind('<<ListboxSelect>>', self.select_page)
        buttons = ttk.Frame(left); buttons.pack(fill='x')
        ttk.Button(buttons, text='追加', command=self.add_page).pack(side='left')
        ttk.Button(buttons, text='削除', command=self.delete_page).pack(side='left')
        self.wiring_button = ttk.Button(buttons, text='配線情報', command=self.edit_wiring)
        self.wiring_button.pack(side='left')
        ttk.Label(left, text='ユニット構成（選択ページ）').pack(anchor='w', pady=(12, 0))
        self.modules = tk.Listbox(left, exportselection=False, height=8)
        self.modules.pack(fill='both', expand=True)
        module_buttons = ttk.Frame(left); module_buttons.pack(fill='x')
        ttk.Button(module_buttons, text='ユニット追加', command=self.pick_modules).pack(side='left')
        ttk.Button(module_buttons, text='削除', command=self.delete_module).pack(side='left')
        ttk.Button(module_buttons, text='タグ名', command=self.edit_module_tag).pack(side='left')
        self.extension_button = ttk.Button(left, text='増設ベース追加', command=self.pick_extension)
        self.extension_button.pack(anchor='w')
        project_form = ttk.LabelFrame(right, text='プロジェクト設定', padding=6)
        project_form.pack(fill='x')
        tabs = ttk.Notebook(project_form); tabs.pack(fill='x')
        basic = ttk.Frame(tabs, padding=4); options = ttk.Frame(tabs, padding=4)
        tabs.add(basic, text='図面情報'); tabs.add(options, text='電源・表紙')
        self.project_vars = {}
        project_fields = [('project_title', 'プロジェクト名'), ('company', '会社名'),
                          ('customer', '顧客名'), ('machine', '装置名'),
                          ('drawing_no', '図番'), ('revision', '改訂'),
                          ('date', '日付（YYYYMMDD）'), ('author', '作成者'),
                          ('checker', '検図者'), ('approver', '承認者')]
        for i, (key, label) in enumerate(project_fields):
            row, col = divmod(i, 2); col *= 2
            ttk.Label(basic, text=label).grid(row=row, column=col, sticky='w', padx=3, pady=2)
            var = tk.StringVar(); self.project_vars[key] = var
            ttk.Entry(basic, textvariable=var, width=22).grid(row=row, column=col+1, sticky='ew', padx=3, pady=2)
            var.trace_add('write', self.project_changed)
        basic.columnconfigure(1, weight=1); basic.columnconfigure(3, weight=1)
        self.power_vars = {}
        for row, (key, label) in enumerate((('P', 'P側電源'), ('N', 'N側電源'))):
            ttk.Label(options, text=label).grid(row=row, column=0, sticky='w', padx=3, pady=2)
            var = tk.StringVar(); self.power_vars[key] = var
            ttk.Entry(options, textvariable=var).grid(row=row, column=1, sticky='ew', padx=3, pady=2)
            var.trace_add('write', self.project_changed)
        options.columnconfigure(1, weight=1)
        self.front_pages = tk.BooleanVar()
        ttk.Checkbutton(options, text='表紙・改訂履歴・目次を作成', variable=self.front_pages).grid(row=2, column=0, columnspan=2, sticky='w', pady=4)
        self.front_pages.trace_add('write', self.project_changed)
        self.cpu_spec = ttk.Label(right, text='', wraplength=700, justify='left')
        self.cpu_spec.pack(fill='x')
        form_box = ttk.LabelFrame(right, text='選択したページ', padding=4); form_box.pack(fill='x', pady=8)
        self.form_canvas = tk.Canvas(form_box,height=300,highlightthickness=0)
        form_scroll=ttk.Scrollbar(form_box,orient='vertical',command=self.form_canvas.yview)
        form_scroll.pack(side='right',fill='y'); self.form_canvas.pack(side='left',fill='x',expand=True)
        self.form_canvas.configure(yscrollcommand=form_scroll.set)
        form=ttk.Frame(self.form_canvas,padding=4)
        form_window=self.form_canvas.create_window(0,0,anchor='nw',window=form)
        form.bind('<Configure>',lambda e:self.form_canvas.configure(scrollregion=self.form_canvas.bbox('all')))
        self.form_canvas.bind('<Configure>',lambda e:self.form_canvas.itemconfigure(form_window,width=e.width))
        form.columnconfigure(1, weight=1)
        self.vars = {'maker': tk.StringVar(), 'series': tk.StringVar()}
        self.field_widgets = {}
        self.kind_display = tk.StringVar()
        self.choice_kind = None
        self.page_catalog = part_catalog('series', '')
        self.series_scope = None
        self.allowed_kinds = []
        self.maker_display, self.series_display = tk.StringVar(), tk.StringVar()
        for row, (label, variable) in enumerate((('メーカー', self.maker_display), ('シリーズ', self.series_display))):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', padx=4, pady=2)
            box = ttk.Combobox(form, textvariable=variable, state='readonly')
            box.grid(row=row, column=1, sticky='ew', padx=4, pady=2)
            if row == 0:
                self.maker_box = box
                box.bind('<<ComboboxSelected>>', self.select_page_maker)
            else:
                self.series_box = box
                box.bind('<<ComboboxSelected>>', self.select_page_series)
        self.settings_visibility = {}
        self.setting_checks = {}
        for row, (key, label) in enumerate(FIELDS, 2):
            field_label = ttk.Label(form, text=label); field_label.grid(row=row, column=0, sticky='w', padx=4, pady=2)
            var = tk.StringVar(); self.vars[key] = var
            if key == 'kind':
                widget = ttk.Combobox(form, textvariable=self.kind_display, values=[v for k,v in KIND_NAMES.items() if k != 'power'], state='readonly')
                widget.bind('<<ComboboxSelected>>', self.select_kind)
            elif key == 'board_model':
                widget = ttk.Combobox(form, textvariable=var, values=('なし', 'FX5-3A-BD', 'FX5-232-BD', 'FX5-485-BD', 'FX5-422-BD-GOT', 'FX5-SDCD'), state='readonly')
            elif key in ('sd_card','memory_cassette','memory_card','batteryless'):
                widget = ttk.Combobox(form, textvariable=var, values=('有', '無', '要確認'), state='readonly')
            elif key in ('battery_model','sd_card_model','memory_cassette_model','memory_card_model'):
                widget = ttk.Combobox(form, textvariable=var, state='normal' if key == 'sd_card_model' else 'readonly')
            elif key in ('left_module', 'right_module'):
                widget = ttk.Combobox(form, textvariable=var, values=('',) + tuple(sorted({m for s in gen.GOT_OPTION.values() for m in s.get('module_interfaces', {})})), state='readonly')
            elif key == 'serial_mode':
                widget = ttk.Combobox(form, textvariable=var, values=('', 'RS-232', 'RS-422/485'), state='readonly')
            elif key in ('model', 'left_model', 'right_model', 'battery', 'power_model', 'base_model'):
                values = ('装着', '非装着', '搭載不可', '要確認') if key == 'battery' else ()
                widget = ttk.Combobox(form, textvariable=var, values=values, state='readonly')
            else:
                widget = ttk.Entry(form, textvariable=var)
            widget.grid(row=row, column=1, sticky='ew', padx=4, pady=2)
            self.field_widgets[key] = [field_label, widget]
            from renderers.settings import LABELS
            if key.removeprefix('left_').removeprefix('right_') in LABELS:
                checked = tk.BooleanVar()
                check = ttk.Checkbutton(form, text='表示', variable=checked,
                                        command=lambda k=key, v=checked: self.toggle_setting(k, v.get()))
                check.grid(row=row, column=2)
                self.setting_checks[key] = (checked, check)
            var.trace_add('write', self.form_changed)
            if key in ('csv', 'input_csv', 'output_csv'):
                button = ttk.Button(form, text='参照', command=lambda k=key: self.pick_csv(k)); button.grid(row=row, column=2)
                self.field_widgets[key].append(button)
            elif key in ('model', 'left_model', 'right_model', 'power_model', 'base_model'):
                button = ttk.Button(form, text='部品から選択', command=lambda k=key: self.pick_part(k)); button.grid(row=row, column=2)
                self.field_widgets[key].append(button)
        ttk.Label(right, text='その他のページ設定（JSON形式）').pack(anchor='w')
        self.extra = tk.Text(right, height=7, undo=True); self.extra.pack(fill='both', expand=True)
        self.extra.bind('<<Modified>>', self.changed)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.show_project()

    def changed(self, event):
        if event.widget.edit_modified():
            if not self.loading: self.dirty = True
            event.widget.edit_modified(False)

    def project_changed(self, *_):
        if not self.loading:
            self.dirty = True

    def update_property_fields(self):
        kind = self.vars['kind'].get()
        model=self.vars['model'].get().upper()
        self.cpu_spec.configure(text=cpu_summary(kind,model))
        self.field_widgets['battery'][1].configure(values=('装着','非装着','要確認') if kind=='qbody' else ('装着','非装着','搭載不可','要確認'))
        spec = cpu_options(kind, model)
        if kind in ('iqrbody', 'mxbody') and spec.get('battery_supported'):
            self.field_widgets['battery'][1].configure(values=('装着','非装着','要確認'))
        for key in ('sd_card_model','memory_cassette_model','memory_card_model'):
            self.field_widgets[key][1].configure(values=('',)+tuple(spec.get(key+'s',[])))
        self.field_widgets['battery_model'][1].configure(values=('',)+tuple(spec.get('battery_models',[]) if kind=='qbody' else []))
        self.extension_button.configure(state='normal' if self.index is not None and kind in ('qbody','iqrbody') else 'disabled')
        self.wiring_button.configure(state='normal' if self.index is not None else 'disabled')
        maker, series = self.vars['maker'].get(), self.vars['series'].get()
        self.maker_box.configure(values=[MAKER_NAMES.get(m, m) for m in sorted(self.page_catalog)],
                                 state='readonly' if self.index is not None else 'disabled')
        self.series_box.configure(values=[SERIES_NAMES.get(s, s) for s in sorted(self.page_catalog.get(maker, {}))],
                                  state='readonly' if maker and self.index is not None else 'disabled')
        self.maker_display.set(MAKER_NAMES.get(maker, maker))
        self.series_display.set(SERIES_NAMES.get(series, series))
        if (maker, series) != self.series_scope:
            self.series_scope = (maker, series)
            self.allowed_kinds = series_kinds(maker, series, self.page_catalog)
        self.field_widgets['kind'][1].configure(values=[KIND_NAMES[k] for k in self.allowed_kinds],
                                               state='readonly' if series else 'disabled')
        self.kind_display.set(KIND_NAMES.get(kind, kind))
        if (kind, maker, series) != self.choice_kind:
            self.choice_kind = (kind, maker, series)
            for key in ('model', 'left_model', 'right_model', 'power_model', 'base_model'):
                catalog = part_catalog(key, kind)
                values = sorted(set(catalog.get(maker, {}).get(series, [])))
                self.field_widgets[key][1].configure(values=values)
        try:
            visible = page_property_fields(dict({k:v.get() for k,v in self.vars.items()}, settings_visibility=self.settings_visibility)) if self.index is not None else []
        except (OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
            self.report(exc)
            visible = ['kind']
        boards = ('なし', 'FX5-3A-BD', 'FX5-232-BD', 'FX5-485-BD', 'FX5-422-BD-GOT')
        if self.vars['model'].get().upper().startswith('FX5S-'):
            boards += ('FX5-SDCD',)
            if self.vars['board_model'].get() != 'FX5-SDCD':
                visible = [key for key in visible if key not in ('sd_card', 'sd_card_model')]
        if 'board_model' not in visible:
            visible = [key for key in visible if key != 'board_tag']
        self.field_widgets['board_model'][1].configure(values=boards)
        controls = {c['key']: c for c in setting_controls(dict({k:v.get() for k,v in self.vars.items()}, settings_visibility=self.settings_visibility))} if self.index is not None else {}
        for key, widgets in self.field_widgets.items():
            for widget in widgets:
                widget.grid() if key in visible else widget.grid_remove()
            if key in self.setting_checks:
                checked, check = self.setting_checks[key]
                if key in controls:
                    checked.set(controls[key]['visible'])
                    check.grid()
                    widgets[0].grid()
                else:
                    check.grid_remove()

    def toggle_setting(self, key, visible):
        self.settings_visibility[key] = visible
        self.dirty = True
        self.update_property_fields()

    def form_changed(self, *_):
        if not self.loading and self.index is not None:
            self.dirty = True
            self.update_property_fields()
            name = KIND_NAMES.get(self.vars['kind'].get()) or SERIES_NAMES.get(self.vars['series'].get()) or 'シリーズを選択'
            label = f"{name}  {self.vars['tag'].get()}  {self.vars['model'].get()}  {self.vars['title'].get()}"
            self.pages.delete(self.index); self.pages.insert(self.index, label); self.pages.selection_set(self.index)

    def select_kind(self, event=None):
        kind = next((key for key, label in KIND_NAMES.items() if label == self.kind_display.get()), '')
        self.vars['kind'].set(kind)
        # ページ種類をユーザーが切り替えた場合のみ、不適合な旧機種を解除する。
        visible = property_fields(kind)
        for key in ('model', 'left_model', 'right_model', 'power_model', 'base_model'):
            if key in visible and self.vars[key].get() not in self.field_widgets[key][1]['values']:
                self.vars[key].set('')

    def select_page_maker(self, event=None):
        maker = next((m for m in self.page_catalog if MAKER_NAMES.get(m, m) == self.maker_display.get()), '')
        self.vars['maker'].set(maker)
        self.vars['series'].set('')
        self.clear_page_models()

    def select_page_series(self, event=None):
        series = next((s for s in self.page_catalog.get(self.vars['maker'].get(), {})
                       if SERIES_NAMES.get(s, s) == self.series_display.get()), '')
        self.vars['series'].set(series)
        self.clear_page_models()

    def clear_page_models(self):
        self.loading = True
        for key in ('kind', 'model', 'left_model', 'right_model', 'power_model', 'base_model'):
            self.vars[key].set('')
        self.loading = False
        if self.index is not None:
            self.dirty = True
            self.form_changed()
        self.update_property_fields()

    def show_project(self):
        self.loading = True
        config = gen.project_config(self.data)
        for key, var in self.project_vars.items():
            var.set(config[key])
        for key, var in self.power_vars.items():
            var.set(config['power'][key])
        self.front_pages.set(config['front_pages'])
        self.pages.delete(0, 'end')
        for p in self.data['pages']: self.pages.insert('end', f"{KIND_NAMES.get(p.get('kind'), p.get('kind', '?'))}  {p.get('tag', '')}  {p.get('model', '')}  {p.get('title', '')}")
        self.location.config(text=str(self.path) if self.path else 'ファイル未選択')
        self.show_page(None)
        self.loading = False

    def show_page(self, index):
        self.loading = True; self.index = index
        page = self.data['pages'][index] if index is not None else {}
        maker, series = page.get('maker', ''), page.get('series', '')
        if not maker or not series:
            models = {str(page.get(key, '')).upper() for key in ('model', 'left_model', 'right_model', 'power_model', 'base_model')} - {''}
            matches = [(m, s) for m, ss in self.page_catalog.items() for s, units in ss.items()
                       if models & {model.upper() for model in units}]
            if not matches and page.get('kind'):
                matches = [(m, s) for m, ss in self.page_catalog.items() for s in ss
                           if page['kind'] in series_kinds(m, s, self.page_catalog)]
            if len(matches) == 1:
                maker, series = matches[0]
        if index is not None and not maker and len(self.page_catalog) == 1:
            maker = next(iter(self.page_catalog))
        self.vars['maker'].set(maker); self.vars['series'].set(series)
        self.settings_visibility = dict(page.get('settings_visibility', {}))
        for key, _ in FIELDS: self.vars[key].set(str(page.get(key, '')))
        self.extra.delete('1.0', 'end')
        self.extra.insert('1.0', json.dumps({k:v for k,v in page.items() if k not in self.vars and k != 'settings_visibility'}, ensure_ascii=False, indent=2))
        self.modules.delete(0, 'end')
        if page.get('kind') in ('iqrbody', 'qbody', 'fx5body', 'mxbody'):
            modules = page.get('modules', [])
            for i, model in enumerate(modules):
                previous = modules[i-1].upper() if i and modules[i-1] else ''
                reserved = page.get('kind') == 'iqrbody' and gen.IQR_ANALOG.get(previous, {}).get('slots', 1) == 2
                tags = page.get('module_tags', [])
                tag = tags[i] if i < len(tags) else ''
                self.modules.insert('end', f'{i}: {tag + "  " if tag else ""}{model or ("占有" if reserved else "空き")}')
        self.extra.edit_modified(False); self.loading = False
        self.update_property_fields()

    def collect_page(self):
        if self.index is None: return
        extra = json.loads(self.extra.get('1.0', 'end'))
        if not isinstance(extra, dict) or any(k in extra for k in self.vars): raise ValueError('その他のページ設定は、上の項目と重複しないJSONオブジェクトにしてください')
        hide_sd = self.vars['kind'].get() == 'fx5body' and self.vars['model'].get().upper().startswith('FX5S-') and self.vars['board_model'].get() != 'FX5-SDCD'
        extra.update({k:v.get().strip() for k,v in self.vars.items() if v.get().strip() and not (hide_sd and k in ('sd_card', 'sd_card_model'))})
        if self.settings_visibility:
            extra['settings_visibility'] = dict(self.settings_visibility)
        kind, model = extra.get('kind'), extra.get('model', '').upper()
        if 'batteryless' not in property_fields(kind, model):
            extra.pop('batteryless', None)
        specs = {'qbody': gen.Q_CPU, 'iqrbody': gen.iqr_cpu_positions(), 'gotbody': gen.GOT_BODY, 'mxbody': gen.MX_CPU, 'fx5body': gen.FX5U_SPECS}
        if kind in specs and model in specs[kind]:
            visible = property_fields(kind, model)
            options = {'qbody': ('sd_card','sd_card_model','memory_cassette','memory_cassette_model','memory_card','memory_card_model'),
                       'iqrbody': ('sd_card','sd_card_model','memory_cassette','memory_cassette_model','memory_card','memory_card_model','battery_model','batteryless'),
                       'gotbody': ('battery','sd_card','sd_card_model','serial_mode'),
                       'mxbody': ('battery','sd_card','sd_card_model'),
                       'fx5body': ('board_model','board_tag')}[kind]
            if 'board_model' not in visible:
                visible = [key for key in visible if key != 'board_tag']
            for key in options:
                if key not in visible:
                    extra.pop(key,None)
        if not extra.get('kind'): raise ValueError('ページの種類を選択してください')
        self.data['pages'][self.index] = extra

    def collect(self):
        project = dict(self.data)
        project.update({k:v.get().strip() for k,v in self.project_vars.items()})
        project['power'] = dict(project.get('power', {}), **{k:v.get().strip() for k,v in self.power_vars.items()})
        project['front_pages'] = self.front_pages.get()
        self.collect_page(); project['pages'] = self.data['pages']; return gen.project_config(project)

    def report(self, exc): messagebox.showerror('エラー', str(exc), parent=self)

    def edit_wiring(self):
        if self.index is None:
            return
        from project_wiring.editor import WiringEditor
        try:
            self.collect_page()
            index = self.index
            page = self.data['pages'][index]
            def apply(value):
                previous = page.get('wiring')
                if value['boundaries'] or value['connections'] or value['terminal_plan']:
                    page['wiring'] = value
                else:
                    page.pop('wiring', None)
                if page.get('wiring') != previous:
                    self.show_page(index)
                    self.dirty = True
            WiringEditor(self, page.get('wiring'), apply,
                         page.get('title') or page.get('tag') or page.get('model') or f'ページ {index + 1}')
        except (ValueError, OSError) as error:
            self.report(error)

    def select_page(self, event=None):
        selection = self.pages.curselection()
        if not selection or selection[0] == self.index: return
        try: self.collect_page()
        except (ValueError, json.JSONDecodeError) as exc:
            self.report(exc); self.pages.selection_clear(0, 'end')
            if self.index is not None: self.pages.selection_set(self.index)
            return
        self.show_page(selection[0])

    def catalog_for_page(self, key):
        catalog = part_catalog(key, self.vars['kind'].get())
        maker, series = self.vars['maker'].get(), self.vars['series'].get()
        models = catalog.get(maker, {}).get(series, [])
        if key=='extension_base_model' and self.vars['kind'].get()=='qbody':
            spec=gen.Q_CPU.get(self.vars['model'].get().upper(),{})
            page=self.data['pages'][self.index] if self.index is not None else {}
            extensions=page.get('extensions',[])
            used=gen.Q_BASE.get(self.vars['base_model'].get().upper(),{}).get('slots',0)+sum(gen.Q_BASE.get(e.get('base_model',''),{}).get('slots',0) for e in extensions)
            models=[m for m in models if len(extensions)<spec.get('max_extension_stages',7) and used+gen.Q_BASE[m]['slots']<=spec.get('max_module_slots',10000)]
        return {maker: {series: models}} if models else {}

    def add_page(self):
        try: self.collect_page()
        except ValueError as exc: self.report(exc); return
        self.data['pages'].append({})
        self.pages.insert('end', 'シリーズを選択'); self.pages.selection_clear(0, 'end'); self.pages.selection_set('end')
        self.show_page(len(self.data['pages'])-1); self.dirty = True

    def delete_page(self):
        if self.index is None: return
        del self.data['pages'][self.index]; self.dirty = True
        self.pages.delete(self.index); self.show_page(None)

    def confirm_discard(self):
        return not self.dirty or messagebox.askyesno('確認', '保存していない変更を破棄しますか？', parent=self)

    def open(self):
        if not self.confirm_discard(): return
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')], parent=self)
        if not path: return
        try:
            with open(path, encoding='utf-8-sig') as f: data = json.load(f)
            if not isinstance(data, dict) or not isinstance(data.get('pages'), list) or not all(isinstance(p, dict) for p in data['pages']): raise ValueError('pages が配列のプロジェクトJSONを選択してください')
            data = gen.project_config(data)
            for key in self.project_vars:
                if not isinstance(data[key], str): raise ValueError(f'{key} は文字列で指定してください')
            if any(not isinstance(data['power'][key], str) for key in self.power_vars): raise ValueError('P側・N側電源は文字列で指定してください')
            if not isinstance(data['front_pages'], bool): raise ValueError('front_pages は true または false で指定してください')
            if any(not isinstance(page.get('kind', ''), str) for page in data['pages']): raise ValueError('ページの種類は文字列で指定してください')
            json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.path = Path(path); self.data = data; self.dirty = False; self.show_project()
        except (OSError, ValueError, TypeError) as exc: self.report(exc)

    def save(self):
        if not self.path: return self.save_as()
        temporary = None
        try:
            data = self.collect()
            text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.' + self.path.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.data = data; self.dirty = False
            return True
        except (OSError, ValueError) as exc: self.report(exc); return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save_as(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')], parent=self)
        if not path: return False
        # Relative CSV and unit paths are based on the JSON directory.
        if self.path and Path(path).resolve().parent != self.path.resolve().parent:
            if not messagebox.askyesno('確認', '保存先が変わると相対パスの参照先も変わります。続けますか？', parent=self): return False
        old = self.path; self.path = Path(path)
        if self.save(): self.location.config(text=str(self.path)); return True
        self.path = old; return False

    def pick_csv(self, key):
        path = filedialog.askopenfilename(initialdir=str(self.path.parent if self.path else ROOT), filetypes=[('CSV', '*.csv')], parent=self)
        if path: self.vars[key].set(os.path.relpath(path, self.path.parent) if self.path and os.path.splitdrive(path)[0].lower() == self.path.drive.lower() else path)

    def delete_module(self):
        selected = self.modules.curselection()
        if self.index is None or not selected: return
        try:
            self.collect_page()
            page = self.data['pages'][self.index]
            modules = page['modules']; i = selected[0]
            if page.get('kind') == 'iqrbody' and not modules[i] and i and gen.IQR_ANALOG.get(modules[i-1].upper(), {}).get('slots', 1) == 2:
                i -= 1
            count = gen.IQR_ANALOG.get(modules[i].upper(), {}).get('slots', 1) if page.get('kind') == 'iqrbody' else 1
            tags = list(page.get('module_tags', []))
            tags += [''] * max(0, len(modules)-len(tags))
            del tags[i:i+count]
            page['module_tags'] = tags
            del modules[i:i+count]
            self.show_page(self.index); self.dirty = True
        except (ValueError, json.JSONDecodeError) as exc: self.report(exc)

    def edit_module_tag(self):
        selected = self.modules.curselection()
        if self.index is None or not selected:
            return
        try:
            self.collect_page()
            page = self.data['pages'][self.index]
            modules = page.get('modules', [])
            i = selected[0]
            if not modules[i]:
                return
            tags = list(page.get('module_tags', []))
            tags += [''] * max(0, len(modules)-len(tags))
            value = simpledialog.askstring('タグ名（管理番号）', modules[i], initialvalue=tags[i], parent=self)
            if value is None:
                return
            tags[i] = value.strip()
            page['module_tags'] = tags
            self.show_page(self.index); self.modules.selection_set(i); self.dirty = True
        except (ValueError, json.JSONDecodeError) as exc:
            self.report(exc)

    def pick_modules(self):
        if self.index is None or self.vars['kind'].get() not in ('qbody', 'iqrbody', 'fx5body', 'mxbody'):
            messagebox.showerror('ユニット構成', '先に本体または構成ページを選択してください。', parent=self); return
        try:
            self.collect_page()
            kind = self.data['pages'][self.index]['kind']
            catalog = self.catalog_for_page('modules')
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.report(exc); return
        dialog = tk.Toplevel(self); dialog.title('ユニットを追加'); dialog.transient(self); dialog.geometry('530x420')
        frame = ttk.Frame(dialog, padding=12); frame.pack(fill='both', expand=True)
        maker_var, series_var = tk.StringVar(), tk.StringVar()
        ttk.Label(frame, text='Maker（メーカー）').pack(anchor='w')
        makers = {MAKER_NAMES.get(m, m): m for m in sorted(catalog)}
        maker_box = ttk.Combobox(frame, textvariable=maker_var, values=list(makers), state='readonly'); maker_box.pack(fill='x')
        ttk.Label(frame, text='Series（シリーズ）').pack(anchor='w', pady=(6, 0))
        series_box = ttk.Combobox(frame, textvariable=series_var, state='readonly'); series_box.pack(fill='x')
        ttk.Label(frame, text='Unit（複数選択可）').pack(anchor='w', pady=(6, 0))
        units = tk.Listbox(frame, selectmode='extended', exportselection=False); units.pack(fill='both', expand=True)
        def select_maker(event=None):
            maker = makers.get(maker_var.get())
            series_box['values'] = [SERIES_NAMES.get(s, s) for s in sorted(catalog.get(maker, {}))]
            series_var.set(''); units.delete(0, 'end')
        def select_series(event=None):
            maker = makers.get(maker_var.get())
            series = next((s for s in catalog.get(maker, {}) if SERIES_NAMES.get(s, s) == series_var.get()), None)
            units.delete(0, 'end')
            for model in catalog.get(maker, {}).get(series, []): units.insert('end', model)
        def confirm():
            selected = [units.get(i) for i in units.curselection()]
            if not selected:
                messagebox.showerror('ユニットを追加', 'ユニットを選択してください。', parent=dialog); return
            page = self.data['pages'][self.index]
            modules = page.get('modules', [])
            bases = gen.Q_BASE if kind == 'qbody' else gen.IQR_BASE if kind == 'iqrbody' else {}
            base = page.get('base_model', '').upper()
            if not isinstance(modules, list):
                messagebox.showerror('ユニットを追加', 'modules は配列で指定してください。', parent=dialog); return
            expanded = [slot for model in selected for slot in ([model] + [''] * (gen.IQR_ANALOG.get(model.upper(), {}).get('slots', 1) - 1) if kind == 'iqrbody' else [model])]
            reserved = gen.IQR_CPU.get(page.get('model', '').upper(), {}).get('network_part', {}).get('slots', 0) if kind == 'iqrbody' else 0
            if base in bases and len(modules) + len(expanded) > bases[base]['slots'] - reserved:
                messagebox.showerror('ユニットを追加', f"{base} のスロット数を超えます。", parent=dialog); return
            if kind == 'mxbody':
                from renderers.controllers import expansion_items
                try:
                    expansion_items(dict(page, modules=modules + expanded))
                except ValueError as error:
                    messagebox.showerror('ユニットを追加', str(error), parent=dialog); return
            page['modules'] = modules + expanded
            tags = list(page.get('module_tags', []))
            page['module_tags'] = tags[:len(modules)] + [''] * (len(modules)-len(tags)) + [''] * len(expanded)
            self.show_page(self.index); self.dirty = True; dialog.destroy()
        maker_box.bind('<<ComboboxSelected>>', select_maker)
        series_box.bind('<<ComboboxSelected>>', select_series)
        ttk.Button(frame, text='確定', command=confirm).pack(anchor='e', pady=(8, 0))
        maker_var.set(MAKER_NAMES.get(self.vars['maker'].get(), self.vars['maker'].get())); select_maker()
        series_var.set(SERIES_NAMES.get(self.vars['series'].get(), self.vars['series'].get())); select_series()
        dialog.grab_set()

    def pick_extension(self):
        if self.index is None or self.vars['kind'].get() not in ('qbody','iqrbody'):
            return
        try:
            self.collect_page()
            page=self.data['pages'][self.index]
            spec=gen.Q_CPU.get(page.get('model','').upper(),{}) if page['kind']=='qbody' else {}
            limit=spec.get('max_extension_stages',7)
            if len(page.get('extensions',[])) >= limit:
                raise ValueError(f'このCPUの増設ベースは{limit}段までです。')
        except (ValueError, json.JSONDecodeError) as exc:
            self.report(exc); return
        def selected(base):
            bases = gen.Q_BASE if self.vars['kind'].get() == 'qbody' else gen.IQR_BASE
            if bases[base].get('power_required',True):
                self.pick_part('power_model',on_select=lambda power:self.add_extension(base,power))
            else:
                self.add_extension(base,'')
        self.pick_part('extension_base_model',on_select=selected)

    def add_extension(self, base, power):
        try:
            self.collect_page()
            page=self.data['pages'][self.index]
            bases=gen.Q_BASE if page['kind']=='qbody' else gen.IQR_BASE
            powers=gen.Q_POWER if page['kind']=='qbody' else gen.IQR_POWER
            if base not in bases or not bases[base].get('extension'):
                raise ValueError('増設ベースを選択してください。')
            if bases[base].get('power_required',True) and power not in powers:
                raise ValueError('増設ベースの電源ユニットを選択してください。')
            extensions=list(page.get('extensions',[]))
            spec=gen.Q_CPU.get(page.get('model','').upper(),{}) if page['kind']=='qbody' else {}
            limit=spec.get('max_extension_stages',7)
            if len(extensions)>=limit:
                raise ValueError(f'このCPUの増設ベースは{limit}段までです。')
            slots=sum(bases[e['base_model']]['slots'] for e in extensions)+bases[page['base_model']]['slots']+bases[base]['slots']
            if spec.get('max_module_slots') and slots>spec['max_module_slots']:
                raise ValueError(f"このCPUの合計スロット数は{spec['max_module_slots']}までです。")
            extensions.append({'base_model':base,'power_model':power,'modules':[]})
            page['extensions']=extensions
            self.show_page(self.index); self.dirty=True
        except (ValueError, json.JSONDecodeError) as exc:
            self.report(exc)

    def pick_part(self, key, on_select=None):
        try:
            catalog = part_catalog(key, self.vars['kind'].get()) if key == 'standard_model' else self.catalog_for_page(key)
            if not catalog:
                raise ValueError('この欄で使用できる部品がありません')
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.report(exc)
            return
        dialog = tk.Toplevel(self)
        dialog.title('部品を選択'); dialog.transient(self); dialog.geometry('500x220')
        frame = ttk.Frame(dialog, padding=12); frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        maker_var, series_var, unit_var = (tk.StringVar() for _ in range(3))
        for row, (label, var) in enumerate((('Maker（メーカー）', maker_var), ('Series（シリーズ）', series_var), ('Unit（形名）', unit_var))):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', padx=4, pady=5)
            box = ttk.Combobox(frame, textvariable=var, state='readonly')
            box.grid(row=row, column=1, sticky='ew', padx=4, pady=5)
            if row == 0: maker_box = box
            elif row == 1: series_box = box
            else: unit_box = box
        makers = {MAKER_NAMES.get(m, m): m for m in sorted(catalog)}
        maker_box['values'] = list(makers)
        def select_maker(event=None):
            maker = makers.get(maker_var.get())
            series = catalog.get(maker, {})
            series_box['values'] = [SERIES_NAMES.get(s, s) for s in sorted(series)]
            series_var.set(''); unit_var.set(''); unit_box['values'] = ()
        def select_series(event=None):
            maker = makers.get(maker_var.get())
            series = next((s for s in catalog.get(maker, {}) if SERIES_NAMES.get(s, s) == series_var.get()), None)
            unit_box['values'] = catalog.get(maker, {}).get(series, [])
            unit_var.set('')
        def confirm():
            if not unit_var.get():
                messagebox.showerror('部品を選択', '形名を選択してください。', parent=dialog); return
            model = unit_var.get()
            dialog.destroy()
            if on_select:
                on_select(model)
            else:
                self.vars[key].set(model)
        maker_box.bind('<<ComboboxSelected>>', select_maker)
        series_box.bind('<<ComboboxSelected>>', select_series)
        ttk.Button(frame, text='選択', command=confirm).grid(row=3, column=1, sticky='e', pady=8)
        if key != 'standard_model':
            maker_var.set(MAKER_NAMES.get(self.vars['maker'].get(), self.vars['maker'].get())); select_maker()
            series_var.set(SERIES_NAMES.get(self.vars['series'].get(), self.vars['series'].get())); select_series()
        maker_box.focus_set()
        dialog.grab_set()

    def update_xrefs(self):
        from tools.update_xrefs import update_file
        source = filedialog.askopenfilename(title='QETで保存した図面を選択', parent=self,
                                          filetypes=[('QET図面', '*.qet')])
        if not source:
            return
        source = Path(source)
        output = filedialog.asksaveasfilename(title='参照表更新後の保存先', parent=self,
                                            initialdir=source.parent, initialfile=source.stem + '_xref.qet',
                                            defaultextension='.qet', filetypes=[('QET図面', '*.qet')])
        if not output:
            return
        try:
            path, count = update_file(source, output)
        except (ValueError, OSError, gen.ET.ParseError) as error:
            messagebox.showerror('参照表を更新', str(error), parent=self)
            return
        messagebox.showinfo('参照表を更新', f'{count}個のa・b接点表を更新しました。\n{path}\nQETで更新後のファイルを開いてください。開いた図面へのリアルタイム反映は行いません。', parent=self)

    def register_all_parts(self):
        from tools.qet_collection import register_all_parts
        try:
            result = register_all_parts()
        except (OSError, ValueError) as exc:
            self.report(exc); return
        messagebox.showinfo('全部QETに登録', result['message'], parent=self)

    def export_standard_parts(self, register=False):
        def choose(model, title, options):
            dialog = tk.Toplevel(self)
            dialog.title(title); dialog.transient(self)
            var, accepted = tk.StringVar(), []
            labels = {o.get('label', o.get('name', o['id'])): o['id'] for o in options}
            def accept():
                if var.get():
                    accepted.append(True)
                    dialog.destroy()
            ttk.Label(dialog, text=model + ' の構成を選択').pack(padx=16, pady=8)
            ttk.Combobox(dialog, textvariable=var, values=list(labels), state='readonly').pack(padx=16, pady=8)
            ttk.Button(dialog, text='選択', command=accept).pack(pady=8)
            dialog.grab_set(); self.wait_window(dialog)
            return labels[var.get()] if accepted else None

        def selected(model):
            definitions = gen.read_unit_definitions()
            spec = definitions['standard_device'].get(model.upper(), definitions['power_supply'].get(model.upper(), {}))
            choice = spec.get('default_auxiliary_option')
            if spec.get('auxiliary_selection_required'):
                choice = choose(model, '補助接点構成', spec['auxiliary_options'])
                if choice is None:
                    return
            configuration = None
            if spec.get('configuration_options'):
                configuration = choose(model, '動作構成', spec['configuration_options'])
                if configuration is None:
                    return
            folder = None
            if not register:
                folder = filedialog.askdirectory(title='部品の書出し先（ユーザーコレクション等）', parent=self)
                if not folder:
                    return
            try:
                if register:
                    from tools.qet_collection import register_part
                    paths = register_part(model, choice, configuration)
                else:
                    paths = export_part(model, folder, choice, configuration)
            except (OSError, ValueError) as exc:
                self.report(exc); return
            if register:
                messagebox.showinfo('QETに登録', f'{len(paths)}部品をQETに登録しました。\n{paths[0].parent}\nユーザーコレクションを更新するかQETを再起動してください。', parent=self)
            else:
                messagebox.showinfo('部品を書出し', f'{len(paths)}部品を書き出しました。\n{paths[0].parent}\n定格・設定を確認して使用してください。コイルと接点がある機器はQETで関連付けてください。', parent=self)
        self.pick_part('standard_model', on_select=selected)

    def generate(self):
        if not self.save(): return
        out = filedialog.asksaveasfilename(initialdir=str(self.path.parent), initialfile=self.path.stem + '.qet', defaultextension='.qet', filetypes=[('QET', '*.qet')], parent=self)
        if not out: return
        from project_wiring.data import terminal_rows
        try:
            suffixes = ['_iolist.csv']
            if terminal_rows([(page, None) for page in self.data['pages']]):
                suffixes.append('_terminals.csv')
        except ValueError as error:
            self.report(error); return
        base = Path(out).with_suffix('').as_posix()
        existing = [base + suffix for suffix in suffixes if Path(base + suffix).exists()]
        if existing and not messagebox.askyesno('確認', '次の一覧も上書きします。\n' + '\n'.join(existing), parent=self): return
        result = subprocess.run([sys.executable, str(ROOT / 'gen_io_page.py'), str(self.path), out], capture_output=True, text=True, encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING':'utf-8'})
        if result.returncode: messagebox.showerror('生成エラー', result.stdout + result.stderr, parent=self); return
        if messagebox.askyesno('生成完了', result.stdout + '\nQETで開きますか？', parent=self):
            try: os.startfile(out)
            except OSError as exc: self.report(exc)

    def sample(self):
        model = self.vars['model'].get().strip()
        if model not in gen.fx_cpu_models() and model.upper() not in gen.Q_MIXED and model.upper() not in gen.IQR_MIXED and model.upper() not in gen.REMOTE_MIXED:
            messagebox.showerror('エラー', 'ページでFX5本体または混合入出力の形名を選択してください。', parent=self); return
        path = filedialog.asksaveasfilename(initialdir=str(self.path.parent if self.path else ROOT), defaultextension='.json', filetypes=[('JSON', '*.json')], parent=self)
        if not path: return
        base = str(Path(path).with_suffix(''))
        existing = [base + s for s in ('.json', '_in.csv', '_out.csv') if Path(base + s).exists()]
        if existing and not messagebox.askyesno('確認', '次のファイルを上書きしますか？\n' + '\n'.join(existing), parent=self): return
        result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'make_sample.py'), model, base], capture_output=True, text=True, encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING':'utf-8'})
        if result.returncode: messagebox.showerror('作成エラー', result.stdout + result.stderr, parent=self)
        else: messagebox.showinfo('作成完了', result.stdout, parent=self)

    def close(self):
        if self.confirm_discard(): self.destroy()

if __name__ == '__main__':
    App().mainloop()
