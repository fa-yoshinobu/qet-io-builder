"""機種定義の読込み、共有カタログ、構成とアドレスの照合。"""
import json
import os

TB16 = [f"TB{i}" for i in range(1, 17)]

PINS32 = [f"B{20 - i}" for i in range(16)] + [f"A{20 - i}" for i in range(16)]

PIN_PRESETS = {"TB16": TB16, "PINS32": PINS32}

def _pins_32(prefix):
    m = {}
    for i in range(16):
        m[f"{prefix}{i:X}"] = f"B{20 - i}"
        m[f"{prefix}{16 + i:X}"] = f"A{20 - i}"
    return m



def io_unit(model):
    m = model.upper().replace(" ", "")
    if m not in IO_UNITS:
        raise SystemExit(f"未対応のユニットです: {model}(対応: {', '.join(IO_UNITS)})")
    return IO_UNITS[m]

def configured_unit(uc):
    if uc.get("_mixed_io"):
        return {"qmixed": Q_MIXED, "iqrmixed": IQR_MIXED, "remotemixed": REMOTE_MIXED}[uc["kind"]][uc["model"].upper()][uc["_mixed_io"] + "put"]
    return io_unit(uc["model"])

def unit_addrs(uc):
    """ユニットのアドレス一覧(16進)。uc: ページ設定(model, start)"""
    unit = configured_unit(uc)
    prefix = "X" if unit["io"] == "in" else "Y"
    start = int(str(uc.get("start", "0")), 16)
    return [f"{prefix}{start + i:X}" for i in range(unit["points"])]

IO_COLUMNS = {"in": ("アドレス", "信号名", "機器番号", "接点", "線番", "備考"),
              "out": ("アドレス", "信号名", "機器番号", "負荷", "形式", "線番", "備考")}

def blank_io_rows(uc):
    """CSV未指定のときの行。アドレスだけを入れ、信号名などは空欄にする(構成から先に図面を作るため)"""
    columns = IO_COLUMNS[configured_unit(uc)["io"]]
    return [dict(dict.fromkeys(columns, ""), アドレス=address) for address in unit_addrs(uc)]

def iqr_units(pg, rows):
    """iQ-R/Q のページに載るユニット [(設定, 行)]。right があれば右半分に別ユニット"""
    if pg["kind"] in ("qmixed", "iqrmixed", "remotemixed"):
        base = int(str(pg.get("start", "0")), 16)
        spec = {"qmixed": Q_MIXED, "iqrmixed": IQR_MIXED, "remotemixed": REMOTE_MIXED}[pg["kind"]][pg["model"].upper()]
        return [(dict(pg, _mixed_io=direction, csv=pg.get(direction + "put_csv", ""),
                      start=f"{base + spec[direction + 'put']['start_offset']:X}"), rows[direction])
                for direction in ("in", "out")]
    out = [(pg, rows)]
    if pg.get("right"):
        out.append((pg["right"], pg["_right_rows"]))
    return out

DEFAULT_RELAY_TYPES = {}  # parts/control以下の標準記号向け機種定義からuse_unitsで設定する。

def octal(prefix, n):
    return [f"{prefix}{oct(i)[2:]}" for i in range(n)]

def _groups(spec):
    """spec: [(コモン番号, 先頭8進, 点数)] → [(番号, [Yアドレス…])]"""
    out = []
    for no, start, n in spec:
        base = int(start, 8)
        out.append((no, [f"Y{oct(base + k)[2:]}" for k in range(n)]))
    return out

UNITS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts")

def read_unit_definitions(path=UNITS_DIR):
    """機種別ファイルを集め、重複や不正な定義を拒否する。"""
    categories = ("kv_io", "inverter", "remote_pulse", "mx_cpu", "mx_io", "remote_mixed", "remote_io", "remote_analog", "remote_iolink", "iqr_mixed", "q_mixed", "iqr_q", "fx5_cpu", "fx5_ext", "fx5_analog", "fx5_comm", "fx5_board", "iqr_cpu", "iqr_power", "iqr_base", "iqr_analog", "iqr_comm", "q_cpu", "q_power", "q_base", "q_analog", "q_comm", "got_body", "got_option", "power_supply", "standard_device")
    categories = ("unit_diagram", "terminal_block") + categories
    d = {category: {} for category in categories}
    if not os.path.isdir(path):
        raise ValueError(f"機種定義フォルダがありません: {path}")
    for root, _, files in os.walk(path):
        for name in sorted(files):
            if not name.lower().endswith(".json"):
                continue
            file = os.path.join(root, name)
            with open(file, encoding="utf-8-sig") as f:
                item = json.load(f)
            if not isinstance(item, dict) or item.get("category") not in d or not isinstance(item.get("model"), str) or not item["model"].strip() or not isinstance(item.get("definition"), dict):
                raise ValueError(f"機種定義が不正です: {file}")
            category, model = item["category"], item["model"].upper()
            if model in d[category]:
                raise ValueError(f"機種定義が重複しています: {model} ({file})")
            definition = item["definition"]
            if category == "terminal_block":
                definition = dict(definition, model=item["model"])
            if category == "fx5_cpu" and (len(definition.get("variants", [])) != 1 or
                    (definition.get("base", "") + definition["variants"][0]).upper() != model):
                raise ValueError(f"CPUのbaseとvariantsが形名と一致しません: {file}")
            if category == "fx5_ext" and definition.get("variants") != [""]:
                raise ValueError(f"増設機種のvariantsは空文字1件にしてください: {file}")
            d[category][model] = definition
    if not any(d.values()):
        raise ValueError(f"機種定義がありません: {path}")
    return d

def _checked_signal_pins(model, spec):
    pins = spec['pins']
    pins = list(PIN_PRESETS[pins]) if isinstance(pins, str) else list(pins)
    if len(pins) != spec['points']:
        raise SystemExit(f"機種定義: {model} の pins の数({len(pins)})が points({spec['points']})と合いません")
    seen_pins = set()
    for pin in pins:
        if not isinstance(pin, str) or not pin.strip():
            raise ValueError(f"機種定義: {model} の信号端子は空でない文字列にしてください")
        normalized = pin.strip().upper()
        if normalized in seen_pins:
            raise ValueError(f"機種定義: {model} の信号端子が重複しています: {pin}")
        seen_pins.add(normalized)
    return pins

def load_units(path=UNITS_DIR):
    """機種別JSONを読み、内部形式に変換する。"""
    d = read_unit_definitions(path)
    io_units = {}
    for model, u in {**d.get("iqr_q", {}), **d.get("remote_io", {})}.items():
        u = dict(u)
        u['pins'] = _checked_signal_pins(model, u)
        io_units[model.upper()] = u
    for category in ('q_mixed', 'iqr_mixed', 'remote_mixed'):
        for model, spec in d[category].items():
            for direction in ('input', 'output'):
                spec[direction]['pins'] = _checked_signal_pins(f'{model} {direction}', spec[direction])
    cpus = {m.upper(): dict(inputs=s["inputs"], groups=_groups([tuple(x) for x in s["outputs"]]),
                            confirmed=s.get("confirmed", False), base=s.get("base", m).upper(),
                            variants=[v.upper() for v in s.get("variants", [])],
                            in_common=s.get("in_common", "S/S"), series=s.get("series", ""),
                            battery_supported=s.get("battery_supported"), usb_port=s.get("usb_port"),
                            analog=s.get("analog"), rs485=s.get("rs485"), service=s.get("service"),
                            physical_io=s.get("physical_io", {}))
            for m, s in d.get("fx5_cpu", {}).items()}
    exts = {m.upper(): dict(inputs=s["inputs"], groups=[tuple(x) for x in s["outputs"]],
                            confirmed=s.get("confirmed", False),
                            in_common=s.get("in_common", "S/S"), sink_only=s.get("sink_only", False),
                            variants=[v.upper() for v in s.get("variants", [])], physical_io=s.get("physical_io", {}))
            for m, s in d.get("fx5_ext", {}).items()}
    # 長い形名を先に照合する(FX5-16EY が FX5-16EX などに誤って当たらないように)
    cpus = dict(sorted(cpus.items(), key=lambda kv: -len(kv[0])))
    exts = dict(sorted(exts.items(), key=lambda kv: -len(kv[0])))
    boards = {**d['fx5_board'], **{m: s for m, s in d['fx5_comm'].items() if s.get('form') == 'board'}}
    from renderers.unit_diagrams import validate
    for model, spec in d["unit_diagram"].items():
        validate(model, spec)
    return io_units, cpus, exts, d["fx5_analog"], d["iqr_cpu"], d["iqr_power"], d["iqr_base"], d["iqr_analog"], d["q_cpu"], d["q_power"], d["q_base"], d["q_analog"], d["q_comm"], d["iqr_comm"], d["fx5_comm"], d["q_mixed"], d["iqr_mixed"], d["remote_mixed"], boards, d["remote_analog"], d["remote_iolink"], d["got_body"], d["got_option"], d["standard_device"], d["remote_pulse"], d["mx_cpu"], d["mx_io"], d["inverter"], d["kv_io"], d["unit_diagram"], d["terminal_block"]

def terminal_block_choice(pg):
    spec = TERMINAL_BLOCKS.get(str(pg.get('model', '')).upper())
    if spec is None:
        raise ValueError('登録済みの中継端子台を選んでください')
    from renderers.cable_routes import check_page
    return spec, check_page(pg, spec)

def terminal_block_project_pages(model, plc_model, cable, plc_tag, block_tag, cable_tag, *, tag2=None, cable_tag2=None, cable2=None, start=None):
    pg = dict(kind='terminal_block', model=model, plc_model=plc_model, cable=cable,
              plc_tag=plc_tag, tag=block_tag, cable_tag=cable_tag)
    pg.update({k: v for k, v in dict(tag2=tag2, cable_tag2=cable_tag2, cable2=cable2, start=start).items() if v is not None})
    terminal_block_choice(pg)
    return [(pg, None)]

def fx_spec(pg):
    """FX5 のページ設定から、入力アドレス・出力グループ・出力方式を決める"""
    m = pg["model"].upper().replace(" ", "")
    kind = "source" if "/ESS" in m or "/DSS" in m else ("relay" if ("R/" in m or m.endswith("R")) else "sink")
    if pg["kind"] == "fx5ext":
        key = next((k for k, e in FX5_EXT_SPECS.items() if m.startswith(k) and m[len(k):] in e["variants"]), None)
        if key is None:
            raise SystemExit(f"未対応の増設ユニットです: {pg['model']}(対応: {', '.join(FX5_EXT_SPECS)})")
        e = FX5_EXT_SPECS[key]
        if e["variants"] and m[len(key):] not in e["variants"]:
            raise SystemExit(f"未対応の増設ユニットです: {pg['model']}"
                             f"(対応: {', '.join(key + v for v in e['variants'])})")
        xs, ys0 = int(str(pg.get("x_start", "0")), 8), int(str(pg.get("y_start", "0")), 8)
        inputs = [f"X{oct(xs + i)[2:]}" for i in range(e["inputs"])]
        groups, k = [], 0
        for no, n in e["groups"]:
            groups.append((no, [f"Y{oct(ys0 + k + i)[2:]}" for i in range(n)]))
            k += n
        return dict(key=key, kind=kind, inputs=inputs, groups=groups, confirmed=e["confirmed"],
                    in_common=e["in_common"], sink_only=e["sink_only"], physical_io=e["physical_io"])
    key, var = fx_cpu_lookup(m)
    if key is None:
        raise SystemExit(f"未対応の機種です: {pg['model']}\n対応する形名: {', '.join(fx_cpu_models())}")
    sp = FX5U_SPECS[key]
    return dict(key=key, kind=fx_out_kind(var), power=fx_power(var), inputs=octal("X", sp["inputs"]),
                groups=sp["groups"], confirmed=sp["confirmed"], in_common=sp["in_common"], physical_io=sp["physical_io"])

def fx_cpu_models():
    """FX5本体の登録形名をすべて返す"""
    return [sp["base"] + v for sp in FX5U_SPECS.values() for v in sp["variants"]]

def fx_cpu_lookup(m):
    """形名 → (定義キー, variant)。base + variant と完全一致したものだけ"""
    for k, sp in FX5U_SPECS.items():
        for v in sp["variants"]:
            if m == sp["base"] + v:
                return k, v
    return None, None

def fx_out_kind(var):
    """'R/ES' → relay、'T/DSS' → source、'T/D' → sink"""
    if var.startswith("R"):
        return "relay"
    return "source" if "SS" in var.split("/", 1)[-1] else "sink"

def fx_power(var):
    """'/ES' 'ESS' → AC、'/D' '/DS' '/DSS' → DC"""
    return "AC" if var.split("/", 1)[-1].startswith("E") else "DC"

def model_power(model):
    """電源ページ用。FX5 本体の形名なら AC/DC を返す(わからなければ AC)"""
    _, var = fx_cpu_lookup(model.upper().replace(" ", ""))
    return fx_power(var) if var else "AC"

def fx_model_info(model):
    """'FX5U-32MR/ES' → (系列キー, 出力方式)(本体用)"""
    sp = fx_spec({"kind": "fx5u", "model": model})
    return sp["key"], sp["kind"]

def fx_expected(pg):
    sp = fx_spec(pg)
    return sp["inputs"], [a for _, addrs in sp["groups"] for a in addrs]

def slot_summary(module, is_q):
    """スロットの箱に書く種類と点数(例 入力32点、アナログ入力4ch、CC-Link IE)"""
    if module in IO_UNITS and IO_UNITS[module].get("io"):
        u = IO_UNITS[module]
        return ("入力" if u["io"] == "in" else "出力") + f"{u['points']}点"
    mixed = Q_MIXED if is_q else IQR_MIXED
    if module in mixed:
        spec = mixed[module]
        return f"入力{spec['input']['points']}点\n出力{spec['output']['points']}点"
    analog = Q_ANALOG if is_q else IQR_ANALOG
    if module in analog:
        dirs = set(analog[module]["channels"])
        kind = "入力" if dirs == {"入力"} else "出力" if dirs == {"出力"} else "入出力"
        return f"アナログ{kind} {len(analog[module]['channels'])}ch"
    comm = Q_COMM if is_q else IQR_COMM
    if module in comm:
        return comm[module]["network"]
    return ""

EMPTY_SLOT_POINTS = 16      # 空きスロットの点数(ページ設定 empty_slot_points で変更)

INTELLI_POINTS = {"analog": 16, "comm": 32}   # アナログは16点、通信・インテリユニットは32点として数える

def slot_definition(module, is_q):
    for definitions in ((Q_ANALOG, Q_COMM) if is_q else (IQR_ANALOG, IQR_COMM)):
        if module in definitions:
            return definitions[module]
    return {}

def slot_points(module, is_q, empty_points):
    """スロットが使う点数と、アドレスの種類(X / Y / X/Y)。空きは empty_points"""
    if not module:
        return empty_points, ""
    if module in IO_UNITS and IO_UNITS[module].get("io"):
        u = IO_UNITS[module]
        return u["points"], "X" if u["io"] == "in" else "Y"
    mixed = Q_MIXED if is_q else IQR_MIXED
    if module in mixed:
        m = mixed[module]
        return max(m["input"]["points"], m["output"]["points"]), "X/Y"
    spec = slot_definition(module, is_q)
    if spec.get("occupied_io_points"):
        return spec["occupied_io_points"], "X/Y"
    if module in (Q_ANALOG if is_q else IQR_ANALOG):
        return INTELLI_POINTS["analog"], "X/Y"
    return INTELLI_POINTS["comm"], "X/Y"

IQR_IO_LIMIT = 4096   # iQ-R の入出力点数(X/Y 0〜FFF)

def slot_assignments(pg):
    """iQ-R / Q 構成のスロットごとの先頭XY。各段の module_starts(16進。空欄は自動)の指定を優先し、
    指定の無いスロットは前のスロットの次から詰める(GX Works の割付と同じ考え方)。指定値は直さない。
    戻り値: (段ごとのスロット一覧, 入力エラー, 警告)。スロットは {start, points, head, manual, reserved, module, tag, slot_no, net}"""
    is_q = pg["kind"] == "qbody"
    cpus, bases = (Q_CPU, Q_BASE) if is_q else (iqr_cpu_positions(), IQR_BASE)
    cpu = str(pg.get("model", "")).upper()
    try:
        empty_points = int(pg.get("empty_slot_points", EMPTY_SLOT_POINTS))
    except (TypeError, ValueError):
        empty_points = EMPTY_SLOT_POINTS
    stages, errors, warnings, ranges = [], [], [], []
    address, slot_no = 0, 0
    for s, (stage, base, _, modules) in enumerate(body_stages(pg)):
        config = pg if s == 0 else pg["extensions"][s - 1]
        starts = config.get("module_starts", [])
        tags = config.get("module_tags", [])
        if not isinstance(starts, list) or any(not isinstance(v, str) for v in starts):
            errors.append(f"{stage}の先頭XY(module_starts)は文字列の配列で指定してください")
            starts = []
        slots = []
        netpart = cpus.get(cpu, {}).get("network_part") if s == 0 else None
        offset = netpart.get("slots", 1) if netpart else 0
        for i in range(bases.get(base, {}).get("slots", 0)):
            if i < offset:
                points = netpart.get("points", 32)
                slots.append({"start": address, "points": points, "head": "X/Y", "manual": False, "reserved": False,
                              "module": "", "tag": "", "slot_no": slot_no, "net": True})
                ranges.append((address, address + points - 1, f"スロット{slot_no}(ネットワーク部)"))
                address += points
                slot_no += 1
                continue
            j = i - offset
            module = str(modules[j]).upper() if j < len(modules) and modules[j] else ""
            previous = str(modules[j - 1]).upper() if j and j - 1 < len(modules) and modules[j - 1] else ""
            reserved = slot_definition(previous, is_q).get("slots", 1) == 2
            points, head = (0, "") if reserved else slot_points(module, is_q, empty_points)
            given = starts[j].strip() if j < len(starts) else ""
            manual = bool(given)
            if manual:
                try:
                    value = int(given, 16)
                    if value < 0:
                        raise ValueError
                except ValueError:
                    errors.append(f"スロット{slot_no}の先頭XYは16進数で指定してください: {given}")
                    value = address
                if reserved:
                    warnings.append(f"スロット{slot_no}は2スロットユニットの占有部のため、先頭XYの指定は使われません")
                    manual = False
                else:
                    address = value
                    if value % 16:
                        warnings.append(f"スロット{slot_no}の先頭XY {given} は16点(10h)単位ではありません")
            label = f"スロット{slot_no}({module or ('占有' if reserved else '空き')})"
            if points:
                ranges.append((address, address + points - 1, label))
            tag = str(tags[j]).strip() if module and j < len(tags) and tags[j] else ""
            slots.append({"start": address, "points": points, "head": head, "manual": manual, "reserved": reserved,
                          "module": module, "tag": tag, "slot_no": slot_no, "net": False})
            address += points
            slot_no += 1
        stages.append(slots)
    ranges.sort()
    for (a0, a1, la), (b0, b1, lb) in zip(ranges, ranges[1:]):
        if b0 <= a1:
            warnings.append(f"{la} と {lb} のXYが重なっています({b0:03X}〜{min(a1, b1):03X})")
    limit = cpus.get(cpu, {}).get("io_points") if is_q else IQR_IO_LIMIT
    if limit and ranges and max(r[1] for r in ranges) >= limit:
        last = max(ranges, key=lambda r: r[1])
        warnings.append(f"{last[2]} のXY(〜{last[1]:03X})がCPUの入出力点数 {limit}点(〜{limit - 1:03X})を超えています")
    return stages, errors, warnings

def page_start_warnings(pages):
    """入出力ページの先頭アドレスが、構成ページで同じ形名・タグのスロットの先頭XYと違うときの警告。"""
    warnings = []
    slots = []
    for pg in pages:
        if pg.get("kind") in ("iqrbody", "qbody"):
            try:
                stages, _, _ = slot_assignments(pg)
            except (KeyError, TypeError, AttributeError):
                continue
            slots += [slot for stage in stages for slot in stage if slot["module"]]
    for pg in pages:
        if pg.get("kind") not in ("input", "output", "qmixed", "iqrmixed") or not pg.get("model"):
            continue
        model, tag = str(pg["model"]).upper(), str(pg.get("tag", "")).strip()
        matches = [s for s in slots if s["module"] == model and (not tag or s["tag"] == tag)]
        if len(matches) != 1:
            continue
        try:
            start = int(str(pg.get("start", "0")), 16)
        except ValueError:
            continue
        if start != matches[0]["start"]:
            name = tag or model
            warnings.append(f"{name} のページの先頭アドレス {start:X} が構成のスロット{matches[0]['slot_no']}({matches[0]['start']:X})と違います")
    return warnings

def body_stages(pg):
    """基本ベースと増設ベースの並び: [(段の名前, ベース形名, 電源形名 or "", ユニットの並び)]"""
    stages = [("基本", pg["base_model"].upper(), pg["power_model"].upper(), pg.get("modules", []))]
    for i, ext in enumerate(pg.get("extensions", []), 1):
        stages.append((f"増設{i}段", ext["base_model"].upper(), str(ext.get("power_model", "")).upper(),
                       ext.get("modules", [])))
    return stages

def cpu_option_error(pg, spec):
    """CPUで確認済みの装着可否と型式候補を検証する。"""
    if str(pg.get('model', '')).startswith('MXR'):
        if pg.get('power_model') == 'R62P' and (pg['model'].startswith('MXR500') or pg.get('base_model') not in ('R33B', 'R35B')):
            return 'このMX-R・基本ベースの組合せではR62Pを使用できません'
    batteryless = pg.get('batteryless', '要確認')
    if batteryless not in ('有', '無', '要確認'):
        return 'バッテリレスは有・無・要確認から選んでください'
    if batteryless == '有':
        if not spec.get('batteryless_supported'):
            return 'このCPUにはバッテリレスオプションを装着できません'
        if pg.get('memory_cassette') == '有':
            return 'バッテリレスと拡張SRAMは同時に装着できません'
    for key,title in (('sd_card','SDカード'),('memory_card','メモリカード'),('memory_cassette','拡張SRAM')):
        state=pg.get(key,'要確認')
        if state not in ('有','無','要確認'):
            return title+'は有・無・要確認から選んでください'
        model=pg.get(key+'_model','')
        if not isinstance(model,str):
            return title+'の型式は文字列で指定してください'
        model=model.strip()
        if spec.get(key+'_supported') is not True and (state=='有' or model):
            return title+'はこのCPUに装着できません'
        candidates=spec.get(key+'_models',[])
        if key=='sd_card':
            # SDは自由入力も残すが、他CPU専用と確認済みの純正型式は流用しない。
            known={m for cpu in (*Q_CPU.values(),*IQR_CPU.values()) for m in cpu.get('sd_card_models',[])}
            if model.upper() in known and model.upper() not in candidates:
                return title+'の型式がこのCPUの対応候補にありません'
        elif model and model not in candidates:
            return title+'の型式がこのCPUの対応候補にありません'
    if 'battery_models' in spec:
        model=pg.get('battery_model','')
        if not isinstance(model,str):
            return 'バッテリの型式は文字列で指定してください'
        if model.strip() and model.strip() not in spec['battery_models']:
            return 'バッテリの型式がこのCPUの対応候補にありません'
    return ''

def iqr_cpu_positions():
    return {**IQR_CPU, **{m: s for m, s in IQR_COMM.items() if s.get('mount_position') == 'cpu_slot'}}

def remote_spec(model):
    for definitions in (IO_UNITS, REMOTE_MIXED, REMOTE_ANALOG, REMOTE_IOLINK, REMOTE_PULSE):
        if model in definitions:
            return definitions[model]
    return None

_UNIT_TABLES = ('IO_UNITS', 'FX5U_SPECS', 'FX5_EXT_SPECS', 'FX5_ANALOG_SPECS', 'IQR_CPU', 'IQR_POWER', 'IQR_BASE', 'IQR_ANALOG', 'Q_CPU', 'Q_POWER', 'Q_BASE', 'Q_ANALOG', 'Q_COMM', 'IQR_COMM', 'FX5_COMM', 'Q_MIXED', 'IQR_MIXED', 'REMOTE_MIXED', 'FX5_BOARDS', 'REMOTE_ANALOG', 'REMOTE_IOLINK', 'GOT_BODY', 'GOT_OPTION', 'STANDARD_DEVICES', 'REMOTE_PULSE', 'MX_CPU', 'MX_IO', 'INVERTERS', 'KV_IO', 'UNIT_DIAGRAMS', 'TERMINAL_BLOCKS')
for _name in _UNIT_TABLES:
    globals()[_name] = {}


def use_units(path=UNITS_DIR):
    """検証後に共有辞書を更新し、各描画モジュールの参照を維持する。"""
    loaded = dict(zip(_UNIT_TABLES, load_units(path)))
    loaded["MX_IO"] = {**loaded["MX_CPU"], **loaded["MX_IO"]}
    loaded["DEFAULT_RELAY_TYPES"] = {model: {"poles": list(range(1, len(spec["contacts"]) + 1)), "contacts": spec["contacts"], "coil": spec["coil"]}
                                     for model, spec in loaded["STANDARD_DEVICES"].items() if spec.get("device_type") == "relay"}
    for name, definitions in loaded.items():
        table = globals()[name]
        table.clear()
        table.update(definitions)


use_units()
