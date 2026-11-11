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
