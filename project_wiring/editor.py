"""選択ページの任意配線情報を編集する固定フォーム。"""
import copy
import tkinter as tk
from tkinter import messagebox, ttk

from project_wiring.data import CONTENT_FIELDS, POSITION_FIELDS, normalize


class WiringEditor(tk.Toplevel):
    def __init__(self, parent, value, on_apply, page_name=''):
        values = normalize(value)
        super().__init__(parent)
        self.title('配線情報')
        self.transient(parent)
        self.geometry('1000x760')
        self.minsize(860, 700)
        self.values = copy.deepcopy(values)
        self.on_apply = on_apply
        self.variables, self.trees, self.current, self.edited = {}, {}, {}, {}
        self.defaults = {key: normalize({key: [{}]})[key][0] for key in CONTENT_FIELDS}
        self.loading = False
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='対象ページ: ' + page_name).pack(anchor='w')
        self.terminal_plan = tk.BooleanVar(self, value=values['terminal_plan'])
        ttk.Checkbutton(frame, text='端子台接続図を追加', variable=self.terminal_plan).pack(anchor='w', pady=(4, 0))
        ttk.Label(frame, text='位置は「配置」タブで調整し、QETでも移動できます。送り・受けは同じ参照IDの2件で対応します。\n'
                             '接続元への配線はQETで行います。未入力の項目は表示しません。').pack(anchor='w', pady=(4, 8))
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill='both', expand=True)
        for group, title in (('connections', '接続注記・端子台'), ('boundaries', '盤内外境界')):
            section = ttk.Frame(self.tabs, padding=6)
            self.tabs.add(section, text=title)
            headings = ('分割頁', '対象機器 / 端子', '端子台', '線番', 'ケーブル', '相手機器', '送り先 / 参照') if group == 'connections' else ('分割頁', '左側', '右側', '横位置', '上端 - 下端')
            listing = ttk.Frame(section)
            listing.pack(fill='x')
            tree = ttk.Treeview(listing, columns=tuple(range(len(headings))), show='headings', height=6)
            for index, heading in enumerate(headings):
                tree.heading(index, text=heading)
                tree.column(index, width=55 if index == 0 else 130, minwidth=40)
            scroll = ttk.Scrollbar(listing, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            tree.pack(fill='x')
            self.trees[group] = tree
            tree.bind('<<TreeviewSelect>>', lambda event, key=group: self.select_row(key))
            controls = ttk.Frame(section)
            controls.pack(fill='x', pady=5)
            for label, command in (('追加', self.add_row), ('更新', self.update_row), ('削除', self.delete_row), ('入力をクリア / 次行', self.clear_row)):
                ttk.Button(controls, text=label, command=lambda key=group, callback=command: callback(key)).pack(side='left', padx=(0, 5))
            form_tabs = ttk.Notebook(section)
            form_tabs.pack(fill='both', expand=True)
            self.variables[group] = {}
            self.current[group], self.edited[group] = None, False
            for label, fields in (('内容', CONTENT_FIELDS[group]), ('配置', POSITION_FIELDS[group])):
                form = ttk.Frame(form_tabs, padding=8)
                form_tabs.add(form, text=label)
                form.columnconfigure(1, weight=1)
                form.columnconfigure(3, weight=1)
                for index, (key, caption) in enumerate(fields):
                    row, column = divmod(index, 2)
                    column *= 2
                    ttk.Label(form, text=caption).grid(row=row, column=column, sticky='w', padx=4, pady=4)
                    variable = tk.StringVar(self, str(self.defaults[group].get(key, '')))
                    self.variables[group][key] = variable
                    widget = (ttk.Combobox(form, textvariable=variable, values=('', '送り', '受け'), state='readonly')
                              if key == 'reference' else ttk.Entry(form, textvariable=variable))
                    widget.grid(row=row, column=column + 1, sticky='ew', padx=4, pady=4)
                    variable.trace_add('write', lambda *args, key=group: self.form_changed(key))
            self.refresh(group)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=(8, 0))
        ttk.Button(buttons, text='取消', command=self.destroy).pack(side='right', padx=4)
        ttk.Button(buttons, text='適用', command=self.apply).pack(side='right', padx=4)
        self.bind('<Escape>', lambda event: self.destroy())
        self.grab_set()

    def form_changed(self, group):
        if not self.loading:
            self.edited[group] = True

    def summary(self, group, row):
        if group == 'boundaries':
            return (row['part'], row['left'], row['right'], row['x'], f"{row['top']} - {row['bottom']}")
        return (row['part'], ':'.join(filter(None, (row['unit_tag'], row['unit_terminal']))),
                ':'.join(filter(None, (row['terminal_block'], row['level'], row['terminal']))), row['wire'],
                ' / '.join(filter(None, (row['cable'], row['core']))),
                ':'.join(filter(None, (row['peer_tag'], row['peer_terminal']))),
                ' / '.join(filter(None, (row['destination'], row['reference'], row['link_id']))))

    def refresh(self, group):
        tree = self.trees[group]
        tree.delete(*tree.get_children())
        for index, row in enumerate(self.values[group]):
            tree.insert('', 'end', iid=str(index), values=self.summary(group, row))
        if self.current[group] is not None:
            tree.selection_set(str(self.current[group]))

    def read_row(self, group):
        row = {key: variable.get().strip() for key, variable in self.variables[group].items()}
        for key, _ in POSITION_FIELDS[group]:
            try:
                row[key] = int(row[key]) if key == 'part' else float(row[key])
            except ValueError:
                raise ValueError('分割頁は整数、配置位置は数値で入力してください') from None
        if group == 'connections' and not any(row[key] for key, _ in CONTENT_FIELDS[group]):
            raise ValueError('接続注記の内容を1項目以上入力してください')
        return normalize({group: [row]})[group][0]

    def store_row(self, group, index):
        row = self.read_row(group)
        if index is None:
            index = len(self.values[group])
            self.values[group].append(row)
            self.trees[group].insert('', 'end', iid=str(index), values=self.summary(group, row))
        else:
            self.values[group][index] = row
            self.trees[group].item(str(index), values=self.summary(group, row))
        self.edited[group] = False
        return index

    def load_row(self, group, row):
        self.loading = True
        try:
            for key, variable in self.variables[group].items():
                variable.set(str(row.get(key, '')))
        finally:
            self.loading = False
        self.edited[group] = False

    def select_row(self, group):
        selection = self.trees[group].selection()
        if not selection:
            return
        index = int(selection[0])
        if index == self.current[group]:
            return
        try:
            if self.edited[group]:
                self.store_row(group, self.current[group])
        except ValueError as error:
            messagebox.showerror('配線情報', str(error), parent=self)
            self.trees[group].selection_remove(*selection)
            if self.current[group] is not None:
                self.trees[group].selection_set(str(self.current[group]))
            return
        self.current[group] = index
        self.load_row(group, self.values[group][index])

    def add_row(self, group):
        try:
            self.current[group] = self.store_row(group, None)
            self.trees[group].selection_set(str(self.current[group]))
        except ValueError as error:
            messagebox.showerror('配線情報', str(error), parent=self)

    def update_row(self, group):
        if self.current[group] is None:
            messagebox.showerror('配線情報', '更新する行を選択してください', parent=self)
            return
        try:
            self.store_row(group, self.current[group])
        except ValueError as error:
            messagebox.showerror('配線情報', str(error), parent=self)

    def delete_row(self, group):
        if self.current[group] is None:
            return
        del self.values[group][self.current[group]]
        self.clear_row(group, advance=False)
        self.refresh(group)

    def clear_row(self, group, advance=True):
        defaults = dict(self.defaults[group])
        if advance and group == 'connections':
            try:
                defaults['part'] = int(self.variables[group]['part'].get())
                defaults['x'] = float(self.variables[group]['x'].get())
            except ValueError:
                messagebox.showerror('配線情報', '分割頁は整数、横位置は数値で入力してください', parent=self)
                return
            ys = [row['y'] for row in self.values[group] if row['part'] == defaults['part'] and row['x'] == defaults['x']]
            if ys:
                defaults['y'] = max(ys) + 100
            try:
                normalize({group: [defaults]})
            except ValueError as error:
                messagebox.showerror('配線情報', str(error), parent=self)
                return
        self.current[group] = None
        self.trees[group].selection_remove(*self.trees[group].selection())
        self.load_row(group, defaults)

    def apply(self):
        try:
            for group in CONTENT_FIELDS:
                if self.edited[group]:
                    self.current[group] = self.store_row(group, self.current[group])
            self.on_apply(normalize(dict(self.values, terminal_plan=self.terminal_plan.get())))
        except ValueError as error:
            messagebox.showerror('配線情報', str(error), parent=self)
            return
        self.destroy()
