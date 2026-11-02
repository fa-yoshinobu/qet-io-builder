"""GUIの画面に依存しない部品・ページ設定の処理。tkinter版とWeb版で共用する。"""
import json
import re
import tomllib
from pathlib import Path

import gen_io_page as gen
from renderers import settings as communication_settings

ROOT = Path(__file__).resolve().parent
PARTS_ROOT = ROOT / 'parts'
MAKER_NAMES = {'mitsubishi': '三菱電機', 'keyence': 'キーエンス', 'omron': 'オムロン', 'fuji': '富士電機', 'toho': '東朋テクノロジー / 吉田電機工業', 'smc': 'SMC', 'nohken': 'ノーケン', 'idec': 'IDEC', 'misumi': 'MISUMI'}
SERIES_NAMES = {'iq_f': 'MELSEC iQ-F (FX5)', 'iq_r': 'MELSEC iQ-R', 'q': 'MELSEC-Q', 'cclink_ie': 'CC-Link IE リモートIO', 'cclink': 'CC-Link リモートIO',
                'iesh': 'IESH 産業用ハブ', 'industrial_switch': '産業用ハブ 金属筐体・Gigabit',
                'hw': 'HW 操作機器', 'rj': 'RJ リレー', 'ru': 'RU リレー', 'sj': 'SJ ソケット', 'ms_t': 'MS-T 電磁接触器', 'th_t': 'TH-T サーマル', 'nf': 'NF ブレーカ', 'cp30_ba': 'CP30-BA サーキットプロテクタ',
                'e2e_next': 'E2E NEXT 近接センサ', 'e3z': 'E3Z 光電センサ', 'wl': 'WL リミットスイッチ', 'is10': 'IS10 圧力スイッチ', 'fq': 'FQ フロートスイッチ', 'm2bj': 'M2BJ ブザー', 'sf_pr': 'SF-PR 三相モータ', '10_sy': '10-SY 電磁弁',
                'got2000': 'GOT2000', 'got3000': 'GOT3000', 'got_options': 'GOT 通信オプション', 'my': 'MY リレー', 'ly': 'LY リレー', 'sc_next': 'SC-NEXT', 'neo_sc': '新SC / NEO SC', 'xw5t': 'XW5T / XW5G 端子台', 'relay_sockets': 'リレーソケット', 'cp30f': 'CP30F 保護器', 'tr_next': 'SC-NEXT サーマル', 'fh': 'FH ヒューズホルダ', 'a22n': 'A22N 操作機器', 'm22n': 'M22N 表示灯', 'h3y': 'H3Y タイマ', 's8v_cp': 'S8V-CP 電子式保護器', 'kv_x': 'KV-X', 'kv_7000_8000': 'KV-7000/8000', 'nj': 'NJ', 'nx': 'NX'}
MAKER_NAMES.update({'wago': 'WAGO', 'phoenix_contact': 'PHOENIX CONTACT', 'littelfuse': 'Littelfuse', 'panasonic': 'パナソニック', 'tdk_lambda': 'TDKラムダ', 'swallow': 'スワロー電機'})
SERIES_NAMES.update({'topjob_s': 'TOPJOB S 端子台', 'pt': 'PT 端子台',
                     'relay_857': '857 リレーモジュール', 'relay_788': '788 リレーモジュール',
                     'plc_interface': 'PLC-INTERFACE リレーモジュール', 'hesi': 'HESI ヒューズ端子台',
                     'fuse_terminal': 'TOPJOB S ヒューズ端子台',
                     'fuse_217': '217 速断ヒューズ', 'fuse_218': '218 タイムラグヒューズ',
                     'hh': 'HH リレー', 'tp': 'TP ソケット', 'su': 'SU ソケット',
                     'gt5y': 'GT5Y タイマ', 'g2r_s': 'G2R-S リレー',
                     'g2rv_st': 'G2RV-ST スリムI/Oリレー', 'p2rf': 'P2RF ソケット',
                     'lf1b_n': 'LF1B-N 盤内LED照明', 'wk': 'WK 盤内コンセント', 'rsen': 'RSEN ノイズフィルタ', 'sc21': 'SC21 小型トランス'})
MAKER_NAMES['otowa'] = '音羽電機工業'
SERIES_NAMES.update({'lt_c': 'LT-C 電源用SPD', 'val_sec': 'VAL-SEC 電源用SPD'})
SERIES_NAMES.update({'y_n': 'Y-N 指示計器', 'cw': 'CW 計測用CT'})
SERIES_NAMES.update({'lb_e': 'LB-E ブレーカ付きトランス', 'elb_e': 'ELB-E 漏電ブレーカ付きトランス', 'cl_a': 'CL-A コンセント付きトランス', 'cl_e': 'CL-E コンセント・シールド付きトランス', 'm_el': 'M-EL マルチトランス'})
SERIES_NAMES['g7sa'] = 'G7SA セーフティリレー'
SERIES_NAMES['h3yn'] = 'H3YN-B タイマ'
SERIES_NAMES['h3cr'] = 'H3CR-A タイマ'
SERIES_NAMES['ar22'] = 'AR22 コマンドスイッチ'
SERIES_NAMES['dr22'] = 'DR22 表示灯'
SERIES_NAMES['ms4s'] = 'MS4S タイマ'
SERIES_NAMES['st7p'] = 'ST7P タイマ'
MAKER_NAMES['cosel'] = 'コーセル'
SERIES_NAMES['nac'] = 'NAC ノイズフィルタ'
MAKER_NAMES['watanabe'] = '渡辺電機工業'
SERIES_NAMES['al'] = 'AL プロセス表示器'
KIND_NAMES = {
    'inverter': 'インバータ',
    'fx5body': 'FX5 本体・拡張ボード',
    'mxbody': 'MX-F 本体', 'mxio': 'MX-F 入出力', 'remotepulse': 'CC-Link パルス・位置決め',
    'power': 'FX5 電源回路', 'input': 'デジタル入力', 'output': 'デジタル出力',
    'fx5u': 'FX5 CPU 入出力', 'fx5ext': 'FX5 増設入出力', 'fx5analog': 'FX5 アナログ入出力',
    'iqranalog': 'iQ-R アナログ入出力', 'qanalog': 'Q アナログ入出力',
    'remoteanalog': 'リモート アナログ入出力', 'remoteiolink': 'リモート IO-Link',
    'qmixed': 'Q 入出力混合', 'iqrmixed': 'iQ-R 入出力混合', 'remotemixed': 'リモート 入出力混合',
    'qcomm': 'Q 通信ユニット', 'iqrcomm': 'iQ-R 通信・情報ユニット', 'fxcomm': 'FX5 通信ユニット',
    'remotebody': 'リモートIO 本体・通信',
    'iqrbody': 'iQ-R / MX-R 本体・ユニット構成', 'qbody': 'Q 本体・ユニット構成',
    'gotbody': 'GOT 本体', 'gotoption': 'GOT 通信オプション',
}
SERIES_NAMES.update({'e800': 'FREQROL-E800', 'd800': 'FREQROL-D800', 'mx_r': 'MELSEC MX-R', 'mx_f': 'MELSEC MX-F', 's8as2': 'S8AS2 DC24V分岐電源', 's8fs_g': 'S8FS-G DC24V電源', 's8vk_g': 'S8VK-G DC24V電源', 's8vk_s': 'S8VK-S DC24V電源', 's8vk_x': 'S8VK-X DC24V電源'})
PAGE_CATEGORIES = {
    'inverter': {'inverter'},
    'power': {'fx5_cpu'}, 'input': {'iqr_q', 'remote_io'}, 'output': {'iqr_q', 'remote_io'},
    'gotbody': {'got_body'}, 'gotoption': {'got_option'}, 'qcomm': {'q_comm'}, 'iqrcomm': {'iqr_comm'}, 'fxcomm': {'fx5_comm'},
    'remotebody': {'remote_io', 'remote_mixed', 'remote_analog', 'remote_iolink', 'remote_pulse'},
    'remotepulse': {'remote_pulse'}, 'mxbody': {'mx_cpu'}, 'mxio': {'mx_cpu', 'mx_io'},
    'remoteanalog': {'remote_analog'}, 'remoteiolink': {'remote_iolink'}, 'remotemixed': {'remote_mixed'},
    'fx5u': {'fx5_cpu'}, 'fx5body': {'fx5_cpu'}, 'fx5ext': {'fx5_ext'}, 'fx5analog': {'fx5_analog'},
    'iqranalog': {'iqr_analog'}, 'qanalog': {'q_analog'}, 'qmixed': {'q_mixed'}, 'iqrmixed': {'iqr_mixed'},
    'iqrbody': {'iqr_cpu'}, 'qbody': {'q_cpu'},
}


def part_catalog(key, kind, root=PARTS_ROOT):
    comm_categories = {key: PAGE_CATEGORIES[key] for key in ('gotoption', 'iqrcomm', 'qcomm', 'fxcomm')}
    allowed = {'standard_model': {'standard_device', 'power_supply'}, 'left_model': comm_categories.get(kind, set()), 'right_model': comm_categories.get(kind, set()),
               'power_model': {'qbody': {'q_power'}, 'iqrbody': {'iqr_power'}}.get(kind, set()),
               'base_model': {'qbody': {'q_base'}, 'iqrbody': {'iqr_base'}}.get(kind, set()),
               'extension_base_model': {'qbody': {'q_base'}, 'iqrbody': {'iqr_base'}}.get(kind, set())}
    kinds = PAGE_CATEGORIES
    categories = allowed.get(key, kinds.get(kind, set()) if key == 'model' else set())
    if key == 'series':
        categories = set().union(*kinds.values())
    if key == 'modules':
        categories = {'iqr_q', 'iqr_analog', 'iqr_comm', 'iqr_mixed'} if kind == 'iqrbody' else {'iqr_q', 'q_analog', 'q_comm', 'q_mixed'} if kind == 'qbody' else {'fx5_comm'} if kind == 'fx5body' else {'mx_io', 'fx5_analog', 'fx5_comm'} if kind == 'mxbody' else set()
    definitions = gen.read_unit_definitions()
    catalog = {}
    for path in root.rglob('*.json'):
        with path.open(encoding='utf-8-sig') as f:
            item = json.load(f)
        category, model = item.get('category'), item.get('model', '')
        if not isinstance(model, str) or category not in definitions or model.upper() not in definitions[category]:
            continue
        cpu_head = kind == 'iqrbody' and item['definition'].get('mount_position') == 'cpu_slot'
        if key == 'modules' and cpu_head:
            continue
        if key == 'base_model' and item['definition'].get('extension'):
            continue
        if key == 'extension_base_model' and not item['definition'].get('extension'):
            continue
        if category not in categories and not (key == 'model' and cpu_head):
            continue
        if key == 'model' and kind in ('input', 'output') and item['definition'].get('io') != ('in' if kind == 'input' else 'out'):
            continue
        relative = path.relative_to(root).parts
        maker, series = relative[1:3] if len(relative) >= 5 else relative[:2]
        if key == 'modules' and kind != 'mxbody' and series != {'iqrbody':'iq_r', 'qbody':'q', 'fx5body':'iq_f'}.get(kind):
            continue
        catalog.setdefault(maker, {}).setdefault(series, []).append(model)
    if kind == 'mxbody' and key == 'modules':
        allowed = {m for spec in gen.MX_CPU.values() for m in spec.get('compatible_modules', [])}
        models = {m for series in catalog.get('mitsubishi', {}).values() for m in series}
        catalog = {'mitsubishi': {'mx_f': sorted(models & allowed)}}
    if kind == 'iqrbody' and key in ('power_model', 'base_model', 'extension_base_model', 'modules'):
        mitsubishi = catalog.get('mitsubishi', {})
        if mitsubishi.get('iq_r'):
            allowed = next((s.get('compatible_modules') for m, s in gen.IQR_CPU.items() if m.startswith('MXR')), None)
            mitsubishi['mx_r'] = [m for m in mitsubishi['iq_r'] if key != 'modules' or allowed is None or m in allowed]
    for series_map in catalog.values():
        for models in series_map.values(): models.sort()
    return catalog


def series_kinds(maker, series, catalog):
    models = {model.upper() for model in catalog.get(maker, {}).get(series, [])}
    definitions = gen.read_unit_definitions()
    result = []
    for kind in KIND_NAMES:
        if kind == 'power':
            continue  # 既存ファイルは読み込めるが、新規ページの選択肢には出さない。
        for category in PAGE_CATEGORIES[kind]:
            candidates = definitions[category]
            if any(model in candidates and (kind not in ('input', 'output') or
                   candidates[model].get('io') == ('in' if kind == 'input' else 'out')) for model in models):
                result.append(kind)
                break
    return result


def export_part(model, folder, auxiliary=None, configuration=None, *, definitions=None):
    definitions = definitions if definitions is not None else gen.read_unit_definitions()
    if model.upper() in definitions['standard_device']:
        from renderers.standard import export_model
        return export_model(model, definitions['standard_device'][model.upper()], folder, auxiliary, configuration=configuration)
    if model.upper() not in definitions['power_supply']:
        raise ValueError('書出しに対応していない部品です: ' + model)
    from tools.export_power_supply_elements import definition
    xml = definition(model, definitions['power_supply'][model.upper()])
    name = re.sub(r'[<>:"/\\|?*]', '-', model)
    target = Path(folder) / name / 'unit.elmt'
    target.parent.mkdir(parents=True, exist_ok=True)
    gen.ET.indent(xml, space='  ')
    gen.ET.ElementTree(xml).write(target, encoding='utf-8', xml_declaration=True)
    return [target]

FIELDS = [('kind', '種類'), ('model', '形名'), ('tag', 'タグ名（管理番号）'), ('slot', 'スロット番号'), ('unit_no','ユニット番号'),
          ('left_model', '左側通信ユニット'), ('left_tag', '左側 タグ名'), ('left_slot','左側 スロット番号'), ('left_unit_no','左側 ユニット番号'),
          ('right_model', '右側通信ユニット'), ('right_tag', '右側 タグ名'), ('right_slot','右側 スロット番号'), ('right_unit_no','右側 ユニット番号'),
          ('power_model', '電源ユニット'), ('power_tag', '電源 タグ名'), ('base_model', 'ベース'), ('base_tag', 'ベース タグ名'), ('title', 'ページ名'), ('csv', 'CSV'),
          ('input_csv', '入力CSV'), ('output_csv', '出力CSV'), ('x_start', '入力開始アドレス'),
          ('y_start', '出力開始アドレス'), ('start', '先頭アドレス（16進）'), ('input_voltage', '入力電圧（V）'), ('battery', '電池状態'), ('sd_card', 'SDカード状態'), ('sd_card_model', 'SDカード型式'), ('board_model', '拡張ボード'),
          ('left_station', '左側 局番・ネットワーク番号'), ('left_ip', '左側 IP設定'), ('left_communication', '左側 通信設定'), ('left_dip', '左側 機器設定'),
          ('serial_mode', 'シリアル方式'), ('station', '局番・ネットワーク番号'), ('ip', 'IP設定'), ('communication', '通信設定'), ('dip', '機器設定'),
          ('right_station', '右側 局番・ネットワーク番号'), ('right_ip', '右側 IP設定'), ('right_communication', '右側 通信設定'), ('right_dip', '右側 機器設定'),
          ('left_module', '左側 通信モジュール'), ('right_module', '右側 通信モジュール'), ('board_tag', '拡張ボード タグ名'),
          ('battery_model','バッテリ型式'), ('batteryless','バッテリレス（NZ1BLC）'), ('memory_cassette','拡張SRAM装着'), ('memory_cassette_model','拡張SRAM型式'),
          ('memory_card','メモリカード装着'), ('memory_card_model','メモリカード型式')]



def setting_controls(page):
    return communication_settings.controls(page)


def page_property_fields(page):
    kind = page.get('kind', '')
    model = page.get('model') or page.get('left_model') or page.get('right_model') or ''
    visible = property_fields(kind, model)
    setting_keys = {prefix + key for prefix in ('', 'left_', 'right_') for key in communication_settings.LABELS}
    return [key for key in visible if key not in setting_keys] + [c['key'] for c in setting_controls(page) if c['visible']]


def cpu_options(kind, model):
    definitions = gen.Q_CPU if kind == 'qbody' else gen.iqr_cpu_positions() if kind == 'iqrbody' else gen.MX_CPU if kind == 'mxbody' else {}
    return definitions.get(model.upper(), {})


def property_fields(kind, model='', root=PARTS_ROOT):
    """部品フォルダの設定からページごとの表示項目を読む。"""
    candidates = []
    for path in sorted(root.rglob('gui_properties.toml')):
        with path.open('rb') as f:
            definitions = tomllib.load(f)
        if kind not in definitions:
            continue
        value = definitions[kind].get('fields')
        if not isinstance(value, list) or any(not isinstance(k, str) or k not in dict(FIELDS) or k == 'kind' for k in value):
            raise ValueError(f'GUIプロパティ定義が不正です: {path}')
        candidates.append((path, value))
    fields = candidates[0][1] if candidates else []
    if model:
        for path, value in candidates:
            for unit_path in path.parent.glob('*.json'):
                with unit_path.open(encoding='utf-8-sig') as f:
                    unit = json.load(f)
                if str(unit.get('model', '')).upper() == model.upper():
                    fields = value
                    break
            else:
                continue
            break
    visible = ['kind'] + (fields or [])
    for model_key,prefix in (('model',''),('left_model','left_'),('right_model','right_')):
        if model_key in visible:
            visible.insert(visible.index(model_key)+1,prefix+('slot' if gen.is_slot_unit(kind,model) else 'unit_no'))
    for model_key, tag_key in (('model', 'tag'), ('left_model', 'left_tag'), ('right_model', 'right_tag'),
                               ('power_model', 'power_tag'), ('base_model', 'base_tag'), ('board_model', 'board_tag')):
        if model_key in visible and tag_key not in visible:
            visible.insert(visible.index(model_key)+1, tag_key)
    if 'input_voltage' in visible and model.upper() not in gen.IO_UNITS:
        visible.remove('input_voltage')
    elif 'input_voltage' in visible and not gen.IO_UNITS[model.upper()].get('input_voltages'):
        visible.remove('input_voltage')
    if kind == 'remotebody' and model:
        spec = gen.remote_spec(model.upper())
        if spec and spec.get('module_role') == 'extension':
            visible = [k for k in visible if k not in ('station', 'ip', 'dip')]
    if kind == 'gotbody' and model.upper() in gen.GOT_BODY:
        spec = gen.GOT_BODY[model.upper()]
        if not spec.get('battery_supported'):
            visible = [k for k in visible if k != 'battery']
        if not spec.get('sd_card_supported'):
            visible = [k for k in visible if k not in ('sd_card', 'sd_card_model')]
        if not spec.get('serial_modes') and not any(i.get('modes') for i in spec['interfaces']):
            visible = [k for k in visible if k != 'serial_mode']
    if 'board_model' in visible and model.upper().startswith('FX5UC-'):
        visible.remove('board_model')
    if kind in ('qbody', 'iqrbody', 'mxbody'):
        spec = cpu_options(kind, model)
        for option,flag in (('sd_card','sd_card_supported'),('memory_cassette','memory_cassette_supported'),('memory_card','memory_card_supported'),('batteryless','batteryless_supported')):
            if not spec.get(flag, False):
                visible=[k for k in visible if k not in (option,option+'_model')]
    return visible


def cpu_summary(kind, model):
    spec=gen.Q_CPU.get(model.upper()) if kind=='qbody' else None
    if not spec:
        return ''
    features=['USB '+spec['usb_type']]
    features+=['Ethernet' if spec['ethernet'] else 'Ethernetなし']
    features+=['RS-232'] if spec.get('rs232_port') else []
    features+=['SDあり' if spec['sd_card_supported'] else 'SDなし']
    features+=['メモリカードあり'] if spec.get('memory_card_supported') else []
    features+=['拡張SRAM対応'] if spec.get('memory_cassette_supported') else []
    return (f"CPU仕様: {spec['program_capacity_ksteps']}Kステップ / 実I/O {spec['io_points']}点 / I/Oデバイス {spec['io_device_points']}点\n"
            + ' / '.join(features)+f" / 増設{spec['max_extension_stages']}段・合計{spec['max_module_slots']}スロットまで")
