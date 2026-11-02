"""gen_io_page.py が対応しているユニットの一覧を units_supported.csv に書き出す。
機種別定義から作るので、ユニットを追加したら再実行すればよい。
使い方: python3 tools/export_units_csv.py"""
import csv, importlib.util, json, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "gen_io_page.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

PDF = {  # サンプルPDF(pdf/ 以下)
    "RX41C4": "iQ-R_32点_RX41C4_RY41NT2P.pdf", "RY41NT2P": "iQ-R_32点_RX41C4_RY41NT2P.pdf",
    "RX40C7": "iQ-R_16点_RX40C7_RY40NT5P_RY10R2.pdf", "RY40NT5P": "iQ-R_16点_RX40C7_RY40NT5P_RY10R2.pdf",
    "RY10R2": "iQ-R_16点_RX40C7_RY40NT5P_RY10R2.pdf",
    **{k: "Q_QX41_QY41P_QX40_QY10.pdf" for k in ("QX41", "QY41P", "QX40", "QY10")},
    "FX5U-32M": "FX5U-32MR.pdf / FX5U-32MT.pdf / FX5U-32MT-DS.pdf", "FX5U-64M": "FX5U-64MR.pdf", "FX5U-80M": "FX5U-80MR.pdf",
    "FX5UJ-24M": "FX5UJ-24MR.pdf", "FX5UJ-40M": "FX5UJ-40MT.pdf", "FX5UJ-60M": "FX5UJ-60MR.pdf",
    "FX5S-30M": "FX5S-30MR.pdf", "FX5S-80M": "FX5S-80MR.pdf", "FX5UJ-24M": "FX5UJ-24MR.pdf / FX5UJ-24MR-DS.pdf",
    "FX5UC-64M-D": "FX5UC-64MT-D.pdf", "FX5UC-96M-DSS": "FX5UC-96MT-DSS.pdf", "FX5UC-32M-TS-R": "FX5UC-32MR-DS-TS.pdf",
    **{k: "FX5U-32MR_増設ユニット.pdf" for k in ("FX5-16EX", "FX5-16EY", "FX5-32ET", "FX5-8EY")},
}
OUT_KIND = {"sink": "トランジスタ(シンク)", "source": "トランジスタ(ソース)", "relay": "リレー", "independent_relay": "リレー(独立接点)"}
rows = []
_d = g.read_unit_definitions()
notes = {k: v.get("note", "") for sec in ("fx5_cpu", "fx5_ext") for k, v in _d[sec].items()}
for m in _d["iqr_q"]:
    m = m.upper(); u = g.IO_UNITS[m]
    series = "iQ-R" if m.startswith("R") else "Q"
    if u["io"] == "in":
        io, nin, nout, out, com = "入力", u["points"], 0, "", "COM " + "/".join(u["common"])
    else:
        io, nin, nout, out = "出力", 0, u["points"], OUT_KIND[u["out"]]
        show = lambda v: "/".join(v) if isinstance(v, list) else v
        com = ("各接点独立" if u["out"] == "independent_relay" else f"COM {show(u['vplus'])} / 0V {show(u['com'])}" if u["out"] == "source" else f"V+ {show(u['vplus'])} / COM {show(u['com'])}" if u["out"] == "sink" else f"COM {show(u['com'])}")
    pins = u.get('terminal_block') or ("コネクタ(40ピン) → A6TBXY36" if u["points"] >= 32 else "端子台(18点)")
    rows.append([series, m, m, "input" if u["io"] == "in" else "output", io, nin, nout, out, "16進",
                 pins, com, ("確認済" if u.get("confirmed") else "要確認") + (f": {u['note']}" if u.get("note") else ""), PDF.get(m, "")])

for model, spec in _d["remote_io"].items():
    is_input = spec["io"] == "in"
    commons = " / ".join(spec["common"]) if is_input else spec["vplus"] + " / " + spec["com"]
    rows.append(["CC-Link IE 増設IO" if spec.get("module_role") == "extension" else spec.get("network", "CC-Link IE") + " リモートIO", model, model, "input" if is_input else "output", "入力" if is_input else "出力",
                 spec["points"] if is_input else 0, 0 if is_input else spec["points"], "" if is_input else OUT_KIND[spec["out"]],
                 "局内X/Y番号（16進）", spec.get("terminal_block", "I/O端子台"), commons, "端子を資料照合、実機未確認", ""])

for model, spec in _d["remote_mixed"].items():
    rows.append([spec.get("network", "CC-Link") + " リモートIO", model, model, "remotemixed", "入出力", spec["input"]["points"], spec["output"]["points"],
                 OUT_KIND[spec["output"]["out"]], "局内X/Y番号（16進）", "端子台", "", "端子を資料照合、実機未確認", ""])

for model, spec in {**_d["q_mixed"], **_d["iqr_mixed"]}.items():
    ins, outs = spec["input"], spec["output"]
    rows.append(["iQ-R" if model in _d["iqr_mixed"] else "Q", model, model, "iqrmixed" if model in _d["iqr_mixed"] else "qmixed", "入出力", ins["points"], outs["points"], "トランジスタ(シンク)",
                 "16進", "端子台" if ins["points"] < 32 else "40ピンコネクタ2個",
                 "入力 COM " + "/".join(ins["common"]) + "、出力 V+ " + ("/".join(outs["vplus"]) if isinstance(outs["vplus"], list) else outs["vplus"]) + " / COM " + ("/".join(outs["com"]) if isinstance(outs["com"], list) else outs["com"]),
                 "資料で端子確認、実機未確認", ""])

def groups_txt(gr):
    return " / ".join(f"COM{no}: {ys[0]}〜{ys[-1]}" if isinstance(ys, list) else f"COM{no}: {ys}点" for no, ys in gr)

KIND = {"relay": "リレー", "sink": "トランジスタ(シンク)", "source": "トランジスタ(ソース)"}
for k in _d["fx5_cpu"]:
    k = k.upper(); s = g.FX5U_SPECS[k]
    nout = sum(len(ys) for _, ys in s["groups"])
    models = [s["base"] + v for v in s["variants"]]
    outs = sorted({KIND[g.fx_out_kind(v)] for v in s["variants"]}, key=list(KIND.values()).index)
    pw = sorted({"AC" if g.fx_power(v) == "AC" else "DC" for v in s["variants"]})
    pdf_key = s["base"]
    if k.startswith("FX5UC-"):
        pdf_key += "-TS-R" if k.endswith("R/DS-TS") else ("-DSS" if k.endswith("T/DSS") else "-D")
    rows.append([s["series"], k, ", ".join(models), "fx5u", "入出力(本体) 電源" + "/".join(pw), s["inputs"], nout,
                 " / ".join(outs), "8進", "本体コネクタ" if "FX5UC" in k and "TS" not in k else "本体端子台",
                 f"入力 {s['in_common']}、出力 " + groups_txt(s["groups"]),
                 ("確認済" if s["confirmed"] else "要確認") + (f": {notes[k]}" if notes.get(k) else ""),
                 PDF.get(pdf_key, "")])
for k in _d["fx5_ext"]:
    k = k.upper(); s = g.FX5_EXT_SPECS[k]
    nout = sum(n for _, n in s["groups"])
    io = "入力" if not nout else ("出力" if not s["inputs"] else "入出力")
    models = [k + v for v in s["variants"]]
    out = "" if not nout else " / ".join(sorted({KIND[g.fx_spec({"kind": "fx5ext", "model": m})["kind"]] for m in models}))
    com = ("入力 " + s["in_common"] if s["inputs"] else "") + (("、" if s["inputs"] else "") + "出力 " + groups_txt(s["groups"]) if nout else "")
    rows.append(["FX5 増設", k, ", ".join(models), "fx5ext", io, s["inputs"], nout, out,
                 "8進(x_start / y_start で先頭指定)", "コネクタ" if k.startswith("FX5-C") and not k.endswith("-TS") else "ユニット端子台", com,
                 ("確認済" if s["confirmed"] else "要確認") + (f": {notes[k]}" if notes.get(k) else ""),
                 next((v for key, v in PDF.items() if key.startswith("FX5-") and k.startswith(key)), "")])

for k, s in _d["fx5_analog"].items():
    nin, nout = s["channels"].count("入力"), s["channels"].count("出力")
    rows.append(["FX5 アナログ", k, k, "fx5analog", "入力・出力" if nin and nout else ("入力" if nin else "出力"),
                 nin, nout, "アナログ", "CH", "端子台", " / ".join(s["terminals"]),
                 "端子展開のみ、外部配線は要確認", ""])

for category, series, kind in (("iqr_analog", "iQ-R アナログ", "iqranalog"), ("q_analog", "Q アナログ", "qanalog"), ("remote_analog", "CC-Link IE アナログ", "remoteanalog")):
    for k, s in _d[category].items():
        nin, nout = s["channels"].count("入力"), s["channels"].count("出力")
        terminals = s.get("terminals_by_direction")
        terminal_text = " / ".join(f"{direction}: {', '.join(names)}" for direction, names in terminals.items()) if terminals else " / ".join(s["terminals"])
        rows.append([s.get("network", series), k, k, kind, "入力・出力" if nin and nout else "入力" if nin else "出力", nin, nout, "アナログ", "CH", "端子台", terminal_text, "端子展開のみ、外部配線は要確認", ""])

for category, label in (("iqr_cpu", "CPU"), ("iqr_power", "電源"), ("iqr_base", "ベース")):
    for k in _d[category]:
        rows.append(["MX-R" if k.startswith("MXR") else "iQ-R", k, k, "iqrbody", label, "", "", "", "", "", "", "構成図対応", ""])

for category, label in (("q_cpu", "CPU"), ("q_power", "電源"), ("q_base", "ベース")):
    for k in _d[category]:
        rows.append(["Q", k, k, "qbody", label, "", "", "", "", "", "", "構成図対応", ""])

for category, series, kind in (("q_comm", "Q", "qbody"), ("iqr_comm", "iQ-R", "iqrbody"), ("fx5_comm", "iQ-F", "fx5body")):
    for model, spec in _d[category].items():
        rows.append([series, model, model, kind, "通信", "", "", "", "", " / ".join(spec["ports"]), "", "構成図対応", ""])

# FX5 の拡張ボード(本体図の board_model で指定)
for model, spec in _d["fx5_board"].items():
    if model in _d["fx5_comm"]:
        continue
    rows.append(["iQ-F", model, model, "fx5body", "拡張ボード", "", "", "", "", " / ".join(spec.get("ports", [])), "", "本体図の board_model で指定", ""])

for model, spec in _d['remote_iolink'].items():
    rows.append([spec['network'] + ' IO-Link', model, model, 'remoteiolink', 'IO-Linkマスタ', '', '', '',
                 'CH/ポート', 'I/Oコネクタ', '', 'ポート端子展開・接続は手動', ''])

for model, spec in _d['got_body'].items():
    rows.append([spec['series'], model, model, 'gotbody', '表示器', '', '', '', '',
                 ' / '.join(i['name'] for i in spec['interfaces']),
                 ' / '.join(spec['power'].get('ports', [])), '端子・コネクタを資料照合、実機未確認', ''])

for model, spec in _d['got_option'].items():
    rows.append(['GOT オプション', model, model, 'gotoption', '通信・接続オプション', '', '', '', '',
                 ' / '.join(i['name'] for i in spec['interfaces']), '', '適用機種・結線は手動確認', ''])

for model, spec in _d['remote_pulse'].items():
    rows.append(['CC-Link', model, model, 'remotepulse', spec.get('function', 'パルス'), '', '', '', '', '実端子', '', '端子資料照合・配線は手動', ''])
for model, spec in _d['mx_cpu'].items():
    rows.append(['MX-F', model, model, 'mxbody / mxio', '本体・入出力', 16, 16, 'トランジスタ', '16進', '端子台・RJ-45', '', '端子資料照合・実機未確認', ''])
for model, spec in _d['mx_io'].items():
    rows.append(['MX-F', model, model, 'mxio', '入出力', spec['inputs'], spec['outputs'], '', '16進', '端子台', '', '端子資料照合・実機未確認', ''])

for model, spec in _d['inverter'].items():
    rows.append([spec['series'], model, model, 'inverter', spec['function'], '', '', '', '',
                 '端子台・通信コネクタ', '', '端子資料照合・実機未確認', ''])

head = ["シリーズ", "形名", "JSONのmodel指定例", "JSONのkind", "入出力", "入力点数", "出力点数", "出力方式",
        "アドレス表記", "配線先", "コモン端子", "確認状態", "サンプルPDF"]
path = os.path.join(HERE, "units_supported.csv")
with open(path, "w", newline="", encoding="utf-8-sig") as f:   # Excel で文字化けしないよう BOM 付き
    w = csv.writer(f); w.writerow(head); w.writerows(rows)
print(path, len(rows), "units")
