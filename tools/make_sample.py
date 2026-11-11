"""FX5 本体の形名から、サンプルのプロジェクトJSONと入出力CSV(予備で埋めたもの)を作る。
使い方: python3 tools/make_sample.py FX5U-32MT/DS units/fx5u-32mt-ds   (→ .json と _in.csv / _out.csv)
電源ページ付き。DC電源タイプなら DC版の電源ページになる。"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv, json, os
import argparse
import gen_io_page as g

IN_NAMES = ["運転押釦", "停止押釦", "非常停止", "リセット押釦", "自動/手動切替", "原点LS", "終点LS", "ワーク有無センサ"]
OUT_NAMES = [("運転表示灯", "PL1", "PL"), ("異常表示灯", "PL2", "PL"), ("ブザー", "BZ1", "RY"), ("コンベア運転", "MC1", "RY")]


def make(model, out_base):
    if model.upper() in g.Q_MIXED or model.upper() in g.IQR_MIXED or model.upper() in g.REMOTE_MIXED:
        spec = (g.Q_MIXED if model.upper() in g.Q_MIXED else g.IQR_MIXED if model.upper() in g.IQR_MIXED else g.REMOTE_MIXED)[model.upper()]
        name = os.path.basename(out_base)
        for direction, prefix in (("input", "X"), ("output", "Y")):
            part = spec[direction]
            suffix = "in" if direction == "input" else "out"
            with open(out_base + "_" + suffix + ".csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f); w.writerow(["アドレス", "信号名", "機器番号", "接点", "負荷", "線番", "備考"])
                for i in range(part["points"]):
                    w.writerow([f"{prefix}{part['start_offset'] + i:X}", "予備", "", "", "", "", ""])
        cfg = {"project_title": model + " サンプル", "date": "20261028", "author": "", "revision": "A",
               "front_pages": False, "pages": [{"kind": "qmixed" if model.upper() in g.Q_MIXED else "iqrmixed" if model.upper() in g.IQR_MIXED else "remotemixed", "model": model,
               "input_csv": name + "_in.csv", "output_csv": name + "_out.csv"}]}
        with open(out_base + ".json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(out_base + ".json", model, part["points"], "出力")
        return
    sp = g.fx_spec({"kind": "fx5u", "model": model})
    name = os.path.basename(out_base)
    with open(out_base + "_in.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["アドレス", "信号名", "機器番号", "接点", "線番", "備考"])
        for i, a in enumerate(sp["inputs"]):
            nm = IN_NAMES[i] if i < len(IN_NAMES) else "予備"
            w.writerow([a, nm, f"S{i + 1}" if nm != "予備" else "", "b" if nm in ("停止押釦", "非常停止") else "a", "", ""])
    ys = [y for _, grp in sp["groups"] for y in grp]
    with open(out_base + "_out.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["アドレス", "信号名", "機器番号", "負荷", "線番", "備考"])
        for i, a in enumerate(ys):
            nm, dev, ld = OUT_NAMES[i] if i < len(OUT_NAMES) else ("予備", "", "RY")
            w.writerow([a, nm, dev, ld, "", ""])
    cfg = {
        "project_title": f"{model} サンプル", "company": "(会社名)", "machine": "サンプル装置",
        "drawing_no": "E-0001", "revision": "A", "date": "20261028", "author": "(作成者)",
        "checker": "", "approver": "", "power": {"P": "+24V", "N": "0V"},
        "pages": [
            {"kind": "power", "title": "電源回路", "model": model, "ac": "AC100V 50/60Hz",
             "cb": "CB1", "cb_spec": "2P 5A", "psu": "PS1", "psu_spec": "DC24V 2.5A",
             "cp": "CP1", "cp_spec": "1P 3A", "service_power": "unused"},
            {"kind": "fx5u", "model": model, "input_csv": name + "_in.csv", "output_csv": name + "_out.csv",
             "input_mode": "sink", "relay_com_to": "P"}],
        "front_pages": False}
    if sp["power"] == "DC":
        del cfg["pages"][0]["service_power"]
    with open(out_base + ".json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(out_base + ".json", sp["key"], sp["power"], sp["kind"], len(sp["inputs"]), "in /", len(ys), "out")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="FX5本体または混合I/Oの形名")
    parser.add_argument("output", help="出力ファイルのベース名（拡張子なし）")
    args = parser.parse_args()
    make(args.model, args.output)
