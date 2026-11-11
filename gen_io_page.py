#!/usr/bin/env python3
"""
I/OリストCSVから QElectroTech のプロジェクト(.qet)を生成する試作スクリプト。

ページ構成は project.json の "pages" で指定する(1ページ = 32点ユニット1台)。
- 入力(RX41C4 想定、プラスコモン):
    P/N ─ 接点 ─ 中継端子 ─ [ピン│Xアドレス│用途]   (配線はユニットの左から入る)
- 出力(RY41NT2P 想定、シンク):
    [用途│Yアドレス│ピン] ─ 中継端子 ─ 負荷 ─ P/N   (配線はユニットの右から出る)
左半分に先頭16点、右半分に後半16点。

使い方:
    python3 gen_io_page.py project.json out.qet

ユニット側のピン・端子番号は機種別定義から入る。
中継端子台の番号が空欄の場合は「?」と表示し、未設定であることを図面上で明示する。
"""
from runtime_check import require_python

require_python()

import copy
import csv
import io
import json
import math
import os
import re
import sys
import uuid
from datetime import date
import xml.etree.ElementTree as ET
from xml.dom import minidom
from renderers import connectors as CONN
from renderers.analog import channel_rows, extra_rows, readonly_symbol
from renderers.plc_symbols import (
    build_symbols, iqr_cpu_symbol, iqr_netpart_symbol, iqr_power_symbol, fx5_body_symbol
)
from renderers.relay_references import (
    COIL_KINDS, XREF, LINES, xref_reset, line_no, ZONE_ROWS,
    ZONE, zone, contact_key, load_key, coil_texts, REF_LINE,
    REF_WN, REF_WC, is_relay_row, row_ys, register_coil, register_contact,
    RELAY_TB, tb_label, ref_header, _write_ref_header, write_references, xref_devices,
    LAMP_KINDS
)
from renderers.iqr_q import (
    iqr_halves, iqr_input_half, iqr_output_half, iqr_independent_relay_half, build_iqr_page, build_input_page,
    build_output_page, build_iqr_body_page
)
from renderers.fx5 import (
    FX_PITCH, FX_Y0, FX_GAP, FX_YMAX, fx_signal_symbol, fx_input_commons,
    fx_input_half, fx_output_half, fx_pack, fx_split_inputs, build_fx5u_pages, fx_single_half,
    fx_draw_single_half, build_fx5_body_page
)
from renderers.melsec_analog import (
    LANE_POWER, CURRENT_JUMPER, analog_names, analog_method_pins, analog_device_symbol, draw_analog_wiring,
    analog_split, analog_page_channels, build_fx_analog_page
)
from renderers.melsec_communication import (
    comm_settings, build_q_comm_page
)
from unit_catalog import (
    _pins_32,
    TB16, PINS32, PIN_PRESETS, io_unit, configured_unit, unit_addrs,
    IO_COLUMNS, blank_io_rows, iqr_units, DEFAULT_RELAY_TYPES, octal, _groups,
    UNITS_DIR, read_unit_definitions, _checked_signal_pins, load_units, use_units, terminal_block_choice,
    terminal_block_project_pages, fx_spec, fx_cpu_models, fx_cpu_lookup, fx_out_kind, fx_power,
    model_power, fx_model_info, fx_expected, slot_summary, EMPTY_SLOT_POINTS, INTELLI_POINTS,
    slot_definition, slot_points, IQR_IO_LIMIT, slot_assignments, page_start_warnings, body_stages,
    cpu_option_error, iqr_cpu_positions, remote_spec, IO_UNITS, FX5U_SPECS, FX5_EXT_SPECS,
    FX5_ANALOG_SPECS, IQR_CPU, IQR_POWER, IQR_BASE, IQR_ANALOG, Q_CPU,
    Q_POWER, Q_BASE, Q_ANALOG, Q_COMM, IQR_COMM, FX5_COMM,
    Q_MIXED, IQR_MIXED, REMOTE_MIXED, FX5_BOARDS, REMOTE_ANALOG, REMOTE_IOLINK,
    GOT_BODY, GOT_OPTION, STANDARD_DEVICES, REMOTE_PULSE, MX_CPU, MX_IO,
    INVERTERS, KV_IO, UNIT_DIAGRAMS, TERMINAL_BLOCKS
)
from renderers.typography import PX_PER_PT, TEXT_MARGIN, text_w, wrap2, fit_font_size
from drawing import (
    FONT_FAMILY, FONT, COLLECTION, BORDER_COLS, COL_SIZE, BORDER_ROWS,
    ROW_SIZE, ROW_Y0, ROW_PITCH, COM_Y, LANE_BOTTOM_Y, UNIT_BOX_BOTTOM,
    UNIT_BOX_W, LANE_TOP_Y, HALF_W, HALVES, IN_X, u,
    font, STYLE, STYLE_FILL, Symbol, draw_rj45, draw_usb_minib,
    draw_dsub9, draw_minidin8, draw_coax, draw_optical, rotate90, box_symbol,
    LANE, ctext, VCENTER_SYMBOLS, vcenter, comment_value, comment_text,
    ORIENT_NUM, io_text_cell, HEAD_X, HEAD_Y, NOTE_Y, page_heading,
    Page, IN_TEXTS, OUT_TEXTS, OUT_X, page_note, lane_labels,
    output_lane_labels, is_slot_unit, identity_cells, unit_identity_header, io_table_header, FX_IN_X,
    FX_OUT_X, FX_IN_TEXTS, FX_OUT_TEXTS, TABLE_X0, TABLE_Y0, TABLE_ROW,
    table
)

# 図面の文字は MS ゴシック(Windows 標準・等幅: 半角 = 全角の半分)。
# 図枠・線番・参照表示の文字は QElectroTech 本体の設定(図面のフォント)で決まる


def project_config(config=None):
    """GUI新規作成・CLI・直接生成で共通のプロジェクト既定値。指定済みの値は維持する。"""
    if config is not None and not isinstance(config, dict):
        raise ValueError('プロジェクト設定はオブジェクトにしてください')
    result = {key: '' for key in ('project_title', 'company', 'customer', 'machine', 'drawing_no',
                                  'revision', 'author', 'checker', 'approver')}
    result.update(date=date.today().strftime('%Y%m%d'), power={'P': '+24V', 'N': '0V'}, front_pages=True)
    result.update(config or {})
    if not isinstance(result['power'], dict):
        raise ValueError('power（電源設定）はオブジェクトにしてください')
    result['power'] = {'P': '+24V', 'N': '0V', **result['power']}
    return result

# ------------------------------------------------------------ リモートユニット
def remote_connector_pages(pg, symbols, spec):
    from renderers.remote import connector_pages
    if pg.get('_mixed_io') and not pg.get('title'):
        pg = dict(pg, title=pg['model'] + (' 入力' if pg['_mixed_io'] == 'in' else ' 出力'))
    return connector_pages(pg, symbols, spec, Page, Symbol, page_heading)


def build_remote_body_page(pg, symbols):
    model = pg['model'].upper()
    spec = remote_spec(model)
    if any(k in spec for k in ('network_connectors', 'power_connectors')) or spec.get('module_role') == 'extension':
        from renderers.remote import build_body
        return build_body(pg, symbols, spec, Page, Symbol, page_heading)
    p = Page(symbols)
    x = 275
    unit_identity_header(p,pg,x,UNIT_BOX_W)
    if spec['network'] == 'CC-Link':
        ports = spec['network_terminals']
        p.text(x + 12, 62, 'CC-Link・電源', 8, True)
    else:
        ports = spec.get('power_ports', [('1', '+24V'), ('2', '24G'), ('3', 'FG')])
        p.text(x + 12, 62, '電源・FG（コネクタ）', 8, True)
    for i, (pin, label) in enumerate(ports):
        y = 97 + i * 27
        plc = p.place('module_pin', x, y, label=pin, comment=label,
                      texts=[('label',14,-7,8,False), ('comment',72,-7,8,False)])
    y_next = 97 + len(ports) * 27 + 40
    if spec['network'] != 'CC-Link':
        for i, port in enumerate(('P1', 'P2')):
            y = y_next + 20 + i * 65
            plug = p.place('module_rj45', x, y)
            p.text(x + 58, y - 15, port, 8, True)
            p.text(x + 58, y + 3, 'RJ-45', 8)
        y_next += 20 + 2 * 65
    notes = (['配線・終端抵抗はネットワーク構成に従って接続']
             if spec['network'] == 'CC-Link' else spec.get('power_notes', []))
    # 注記は箱の幅で折り返す(箱は中身に合わせた幅 300)
    from renderers.communication import draw_notes
    draw_notes(p,x,UNIT_BOX_W,['※通信・電源の接続先はQETで記入']+list(notes))
    from renderers import settings
    from renderers.box_layout import finish_box
    rows = settings.fields(model=pg['model'], values=pg)
    finish_box(p, x, x + UNIT_BOX_W, y + (24 if spec['network'] == 'CC-Link' else 40), rows, pg,
               minimum=200, limit=min(790, getattr(p, 'communication_footer_top', 800) - 8))
    return p


def build_sensor_connector_page(uc, symbols, start):
    spec = configured_unit(uc)
    p = Page(symbols)
    page_heading(p, f"{uc['model']} センサコネクタ端子")
    p.text(HEAD_X, 800, '※配線はQETで記入', 8)
    for position in range(8):
        index = start + position
        if index >= spec['points']:
            break
        side, slot = divmod(position, 4)
        x, y0 = 275 + side * HALF_W, 88 + slot * 155
        p.text(x - 245, y0 - 24, f"CON{spec.get('sensor_connector_start', 1) + index}  {spec.get('sensor_prefix', 'X')}{index:X}", 8, True)
        for pin, label in enumerate(spec['sensor_pins'], 1):
            y = y0 + (pin - 1) * 31
            plc = p.place('fx_in', x, y, label=str(pin), comment=label,
                          texts=FX_IN_TEXTS + [('comment', 64, vcenter(8), 8, False)])
    return p


# ============================================================ 電源ページ(FX5U 本体・DC24V)
def build_power_page(pg, cfg, symbols):
    """AC電源 → ブレーカ → FX5U本体(L/N/⏚)と DC24V電源 → P/N(入出力ページへ)
    本体が DC電源タイプ(形名 /D…、または "power_type": "DC")なら build_power_page_dc"""
    ptype = (pg.get("power_type") or model_power(pg.get("model", ""))).upper()
    if ptype == "DC":
        return build_power_page_dc(pg, cfg, symbols)
    p = Page(symbols)
    pw = cfg["power"]
    RL, RN, RPE = 150, 200, 250                    # L / N / PE レールの Y
    X0, XCB, XPLC, XPSU, XEND = 60, 180, 340, 700, 1000

    p.text(30, 70, pg.get("ac", "AC100V 50/60Hz"), 10, True)
    for name, y in (("L", RL), ("N", RN), ("PE", RPE)):
        p.text(X0 - 28, y - 9, name, 9, True)
    # 入口
    l0 = p.place("junction", X0, RL)
    n0 = p.place("junction", X0, RN)
    pe0 = p.place("junction", X0, RPE)
    cb = p.place("breaker_2p", XCB, RL, label=pg.get("cb", "CB1"), comment=pg.get("cb_spec", ""),
                 texts=[("label", -16, -30, 9, True), ("comment", -16, 58, 7, False)])
    p.wire(l0, "e", cb, "w0", num="L", show=False)
    p.wire(n0, "e", cb, "w50", num="N", show=False)

    # 分岐点
    lp = p.place("junction", XPLC, RL); np_ = p.place("junction", XPLC + 40, RN)
    pep = p.place("junction", XPLC + 80, RPE)
    ls = p.place("junction", XPSU, RL); ns = p.place("junction", XPSU + 40, RN)
    pes = p.place("junction", XPSU + 80, RPE)
    p.wire(cb, "e0", lp, "w", num="L1", show=True)
    p.wire(cb, "e50", np_, "w", num="N1", show=True)
    p.wire(lp, "e", ls, "w")
    p.wire(np_, "e", ns, "w")
    p.wire(pe0, "e", pep, "w", num="PE", show=True)
    p.wire(pep, "e", pes, "w")

    # FX5U 本体
    plc = p.place("fx5u_power", XPLC, 330, label=pg.get("model", "FX5U"), comment="本体電源",
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 192)])
    p.wire(lp, "s", plc, "L"); p.wire(np_, "s", plc, "N"); p.wire(pep, "s", plc, "⏚")
    sp = pg.get("service_power", "unused")
    if sp == "unused":
        p.text(XPLC - 20, 430, "24+ / 0V:サービス電源 未使用(入出力は外部DC24V電源から供給)", 7)
    # DC24V 電源
    psu = p.place("psu_24v", XPSU, 330, label=pg.get("psu", "PS1"), comment=pg.get("psu_spec", "DC24V"),
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 152)])
    p.wire(ls, "s", psu, "L"); p.wire(ns, "s", psu, "N"); p.wire(pes, "s", psu, "⏚")

    # P / N へ
    YN, YP = 500, 540
    nj = p.place("junction", XPSU + 40, YN)
    pj = p.place("junction", XPSU, YP)
    ne = p.place("junction", XEND, YN)
    pe_ = p.place("junction", XEND, YP)
    p.wire(psu, "-V", nj, "n"); p.wire(nj, "e", ne, "w", num=LANE["N"], show=True)
    p.wire(psu, "+V", pj, "n"); p.wire(pj, "e", pe_, "w", num=LANE["P"], show=True)
    p.text(XEND + 12, YN - 9, f"{LANE['N']} → 各ページ", 9, True)
    p.text(XEND + 12, YP - 9, f"{LANE['P']} → 各ページ", 9, True)
    return p


def build_power_page_dc(pg, cfg, symbols):
    """DC電源タイプ: AC電源 → ブレーカ → DC24V電源 → P/N(入出力ページへ)、
    P → サーキットプロテクタ → 本体[+]、N → 本体[-]"""
    p = Page(symbols)
    RL, RN, RPE = 150, 200, 250
    X0, XCB, XPSU, XPLC, XEND = 60, 180, 340, 700, 1000
    YN, YP = 500, 540

    p.text(30, 70, pg.get("ac", "AC100V 50/60Hz"), 10, True)
    for name, y in (("L", RL), ("N", RN), ("PE", RPE)):
        p.text(X0 - 28, y - 9, name, 9, True)
    l0 = p.place("junction", X0, RL)
    n0 = p.place("junction", X0, RN)
    pe0 = p.place("junction", X0, RPE)
    cb = p.place("breaker_2p", XCB, RL, label=pg.get("cb", "CB1"), comment=pg.get("cb_spec", ""),
                 texts=[("label", -16, -30, 9, True), ("comment", -16, 58, 7, False)])
    p.wire(l0, "e", cb, "w0", num="L", show=False)
    p.wire(n0, "e", cb, "w50", num="N", show=False)

    # DC24V 電源
    psu = p.place("psu_24v", XPSU, 330, label=pg.get("psu", "PS1"), comment=pg.get("psu_spec", "DC24V"),
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 152)])
    ls = p.place("junction", XPSU, RL); ns = p.place("junction", XPSU + 40, RN)
    p.wire(cb, "e0", ls, "w", num="L1", show=True); p.wire(ls, "s", psu, "L")
    p.wire(cb, "e50", ns, "w", num="N1", show=True); p.wire(ns, "s", psu, "N")
    pes = p.place("junction", XPSU + 80, RPE)
    pep = p.place("junction", XPLC + 80, RPE)
    p.wire(pe0, "e", pes, "w", num="PE", show=True)
    p.wire(pes, "e", pep, "w")
    p.wire(pes, "s", psu, "⏚")

    # P / N へ(本体の電源もここから取る)
    nj = p.place("junction", XPSU + 40, YN)
    pj = p.place("junction", XPSU, YP)
    nb = p.place("junction", XPLC + 40, YN)
    pb = p.place("junction", XPLC, YP)
    ne = p.place("junction", XEND, YN)
    pe_ = p.place("junction", XEND, YP)
    p.wire(psu, "-V", nj, "n")
    p.wire(nj, "e", nb, "w", num=LANE["N"], show=True); p.wire(nb, "e", ne, "w")
    p.wire(psu, "+V", pj, "n")
    p.wire(pj, "e", pb, "w", num=LANE["P"], show=True); p.wire(pb, "e", pe_, "w")
    p.text(XEND + 12, YN - 9, f"{LANE['N']} → 各ページ", 9, True)
    p.text(XEND + 12, YP - 9, f"{LANE['P']} → 各ページ", 9, True)

    # 本体(DC電源)
    cp = p.place("cp_1p", XPLC, 580, label=pg.get("cp", "CP1"), comment=pg.get("cp_spec", ""),
                 texts=[("label", 12, 4, 9, True), ("comment", 12, 20, 7, False)])
    p.wire(pb, "s", cp, "n")
    model = pg.get("model", "FX5U")
    terms = "電源コネクタ 1(赤)=+24V 2(黒)=0V 3=アース" if model.upper().startswith("FX5UC") else "本体電源 DC24V"
    plc = p.place("fx5_power_dc", XPLC, 680, label=model, comment=terms,
                  texts=[("label", -14, 26, 10, True), ("comment", -14, 44, 8, False, 192)])
    p.wire(cp, "s", plc, "+", num="P1", show=True)
    p.wire(nb, "s", plc, "-")
    p.wire(pep, "s", plc, "⏚")
    return p


# ============================================================ 表紙・改訂履歴・目次


def build_cover(cfg, symbols, latest_rev):
    p = Page(symbols)
    dx = 20 + BORDER_COLS * COL_SIZE // 2 - 470 - 260   # 枠(幅940)を図枠の中央に
    p.text(dx + 300, 170, cfg.get("customer", ""), 14)
    p.text(dx + 300, 220, cfg["machine"], 28, True)
    p.text(dx + 300, 290, "電気図面", 24, True)
    rows = [["図番", cfg["drawing_no"]], ["最新改訂", latest_rev], ["作成日", fmt_date(cfg["date"])],
            ["作成", cfg["author"]], ["会社", cfg["company"]]]
    for i, (k, v) in enumerate(rows):
        y = 400 + i * 40
        p.line(dx + 300, y + 36, dx + 900, y + 36, 0.8)
        p.text(dx + 310, y + 8, k, 11, True)
        p.text(dx + 460, y + 8, v, 12)
    p.rect(dx + 260, 130, 940, 620, dash=False, width=2.0)
    return p


def build_revision_pages(cfg, symbols, revs, per_page=19):
    cols = [("改訂", 70), ("日付", 120), ("変更内容", BORDER_COLS * COL_SIZE - 2 * (TABLE_X0 - 20) - 570), ("対象ページ", 200), ("作成", 90), ("承認", 90)]
    pages = []
    chunks = [revs[i:i + per_page] for i in range(0, max(len(revs), 1), per_page)] or [[]]
    for ci, chunk in enumerate(chunks):
        p = Page(symbols)
        p.text(TABLE_X0, 60, "改訂履歴(全ページ共通)" + (f"  {ci + 1}/{len(chunks)}" if len(chunks) > 1 else ""), 14, True)
        rows = [[r.get("改訂", ""), r.get("日付", ""), r.get("変更内容", ""), r.get("対象ページ", ""),
                 r.get("作成", ""), r.get("承認", "")] for r in chunk]
        rows += [[""] * len(cols)] * (per_page - len(rows))   # 空行で表を埋める
        table(p, TABLE_X0, TABLE_Y0, cols, rows)
        pages.append(("改訂履歴" if len(chunks) == 1 else f"改訂履歴 {ci + 1}", p))
    return pages


def build_toc_pages(cfg, symbols, entries, per_col=19):
    """entries: [(ページ番号, 名称)]。1ページ2列(左右)"""
    cols = [("頁", 60), ("図面名称", HALF_W - 120)]          # 2つの表で図枠の幅いっぱいを使う
    per_page = per_col * 2
    pages = []
    for start in range(0, len(entries), per_page):
        p = Page(symbols)
        p.text(50, 60, "目次", 14, True)
        chunk = entries[start:start + per_page]
        for side, sub in enumerate((chunk[:per_col], chunk[per_col:])):
            # 右の表は中身がなくても枠を描く(あとでページが増えたときに書き足せるように)
            rows = [[n, t] for n, t in sub] + [["", ""]] * (per_col - len(sub))
            table(p, 50 + side * HALF_W, TABLE_Y0, cols, rows)
        pages.append(("目次", p))
    return pages


def fmt_date(d):
    d = str(d)
    return f"{d[:4]}/{d[4:6]}/{d[6:8]}" if len(d) == 8 and d.isdigit() else d


BUILDERS = {"input": (build_input_page, "X"), "output": (build_output_page, "Y")}


# ------------------------------------------------------------ 図枠(日本語・下部2段)
TITLEBLOCK_NAME = "JP_A3_2dan"


def titleblock_xml():
    tb = ET.Element("titleblocktemplate", name=TITLEBLOCK_NAME)
    ET.SubElement(tb, "information").text = "日本語 下部2段 図枠(改訂履歴は別ページ)"
    ET.SubElement(tb, "logos")
    grid = ET.SubElement(tb, "grid", rows="25;25;", cols="t16%;t20%;t12%;t12%;t10%;t10%;r100%;")

    def field(row, col, name, value, label, colspan=0, size=9, show_label=True, align="center"):
        f = ET.SubElement(grid, "field", row=str(row), col=str(col), name=name,
                          displaylabel="true" if show_label else "false",
                          align=align, valign="center", hadjust="true", fontsize=str(size))
        if colspan > 0:  # QElectroTech の colspan は「右に追加で結合する列数」
            f.set("colspan", str(colspan))
        v = ET.SubElement(f, "value")
        for lang in ("ja", "en"):
            ET.SubElement(v, "translation", lang=lang).text = value
        lb = ET.SubElement(f, "label")
        for lang in ("ja", "en"):
            ET.SubElement(lb, "translation", lang=lang).text = label

    # 上段: 会社名 / 装置名 / 図面名称
    field(0, 0, "company", "%{company}", "会社", show_label=False, size=10)
    field(0, 1, "machine", "%{machine}", "装置名", colspan=1, size=10)
    field(0, 3, "title", "%title", "図面名称", colspan=3, size=11, show_label=False)
    # 下段: 図番 / 日付 / 改訂 / 作成 / 検図 / 承認 / ページ
    field(1, 0, "drawing_no", "%{drawing_no}", "図番", size=9)
    field(1, 1, "date", "%date", "日付", size=8)
    field(1, 2, "rev", "%indexrev", "改訂", size=9)
    field(1, 3, "author", "%author", "作成", size=8)
    field(1, 4, "checker", "%{checker}", "検図", size=8)
    field(1, 5, "approver", "%{approver}", "承認", size=8)
    field(1, 6, "page", "%{folio-id} / %{folio-total}", "頁", size=10)
    return tb


# ------------------------------------------------------------ プロジェクト出力
def add_diagram(proj, cfg, title, order, page):
    dg = ET.SubElement(proj, "diagram", {
        "title": title, "author": cfg["author"], "date": cfg["date"],
        "indexrev": cfg["revision"], "folio": "%id/%total", "order": str(order),
        "cols": str(BORDER_COLS), "colsize": str(COL_SIZE),
        "rows": str(BORDER_ROWS), "rowsize": str(ROW_SIZE),
        "displaycols": "true", "displayrows": "true", "displayAt": "bottom",
        "titleblocktemplate": TITLEBLOCK_NAME, "titleblocktemplateCollection": "embedded",
        "version": "0.100.0", "freezeNewConductor": "false", "freezeNewElement": "false",
        "filename": "", "plant": "", "locmach": "", "auto_page_num": "", "uuid": u(),
    })
    dprops = ET.SubElement(dg, "properties")
    for k in ("company", "machine", "drawing_no", "checker", "approver"):
        ET.SubElement(dprops, "property", name=k, show="1").text = cfg.get(k, "")
    ET.SubElement(dg, "defaultconductor", type="multi", num="_", displaytext="1", numsize="7",
                  condsize="1", horizrotatetext="0", vertirotatetext="270")
    for tag, items in (("elements", page.elements), ("conductors", page.conductors), ("inputs", page.texts)):
        holder = ET.SubElement(dg, tag)
        for it in items:
            holder.append(it)
    shapes = ET.SubElement(dg, "shapes")
    for sh in page.shapes:
        shapes.append(sh)


def build_project(cfg, pages_rows):
    cfg = project_config(cfg)
    symbols = build_symbols()
    proj = ET.Element("project", title=cfg["project_title"], version="0.100.0")
    props = ET.SubElement(proj, "properties")
    ET.SubElement(props, "property", name="saveddate", show="1").text = cfg["date"]
    ET.SubElement(proj, "titleblocktemplates").append(titleblock_xml())

    nd = ET.SubElement(proj, "newdiagrams")
    ET.SubElement(nd, "border", cols=str(BORDER_COLS), colsize=str(COL_SIZE),
                  rows=str(BORDER_ROWS), rowsize=str(ROW_SIZE), displaycols="true", displayrows="true")
    # クロスリファレンスの表示: 位置は「ページ-列行」(例 5-12C)
    xr = ET.SubElement(nd, "xrefs")
    for t, disp, snap in (("coil", "contacts", "label"), ("protection", "cross", "label"),
                          ("commutator", "cross", "label")):
        ET.SubElement(xr, "xref", type=t, displayhas=disp, snapto=snap, offset="0",
                      master_label="%f-%c%l", slave_label="(%f-%c%l)", showpowerctc="false",
                      xrefpos="AlignRight", switchprefix="", delayprefix="", powerprefix="")
    ET.SubElement(nd, "inset", title="", author=cfg["author"], folio="%id/%total",
                  date="null", displayAt="bottom", indexrev=cfg["revision"],
                  titleblocktemplate=TITLEBLOCK_NAME, titleblocktemplateCollection="embedded")

    ZONE["col_start"] = int(cfg.get("zone_col_start", 1))
    LANE["P"] = cfg.get("power", {}).get("P_name", "P24")
    LANE["N"] = cfg.get("power", {}).get("N_name", "N24")
    xref_reset(xref_devices(pages_rows, cfg))
    body = []
    post_rows = []
    pages_of = {}          # id(pg) → その設定から作ったページ(構成ページの参照に使う)
    cable_sheets = []
    cable_ids = set()
    shared = None          # 右半分が空いている増設ユニットのページ(body の番号)
    for pg, rows in pages_rows:
        if pg["kind"] not in ("gotoption", "qcomm", "iqrcomm", "fxcomm"):
            post_rows.append((pg, rows))
        first = len(body)
        single = fx_single_half(pg, rows["in"], rows["out"]) if pg["kind"] == "fx5ext" else None
        if single and shared is not None:
            # 入力だけ・出力だけの小さいユニットは、前のユニットの右半分に並べる
            title, page = body[shared]
            body[shared] = (title + " / " + fx_draw_single_half(page, HALF_W, pg, cfg, single), page)
            pages_of[id(pg)] = [page]
            shared = None
            continue
        if single:
            page = Page(symbols)
            body.append((fx_draw_single_half(page, 0, pg, cfg, single), page))
            shared = len(body) - 1
            pages_of[id(pg)] = [page]
            continue
        shared = None
        if pg["kind"] in ("fx5u", "fx5ext"):
            body += build_fx5u_pages(pg, cfg, symbols, rows["in"], rows["out"])
        elif pg["kind"] in ("fx5analog", "iqranalog", "qanalog", "remoteanalog"):
            spec = {"iqranalog": IQR_ANALOG, "qanalog": Q_ANALOG, "fx5analog": FX5_ANALOG_SPECS, "remoteanalog": REMOTE_ANALOG}[pg["kind"]][pg["model"].upper()]
            page_channels = analog_page_channels(pg['kind'],spec)
            count = (len(spec["channels"]) + page_channels-1) // page_channels
            for part in range(count):
                title = pg.get("title", pg["model"] + " アナログ端子")
                if count > 1: title += f" ({part + 1}/{count})"
                body.append((title, build_fx_analog_page(pg, cfg, symbols, rows, part * page_channels)))
        elif pg["kind"] in ("kvbody", "nxbody"):
            from renderers.plc_configuration import build_pages
            body.extend(build_pages(pg, symbols))
        elif pg["kind"] == "terminal_block":
            from renderers.cable_routes import build_sheets
            sheets, refs = build_sheets(pg, *terminal_block_choice(pg), symbols, cable_ids)
            body.extend(sheets)
            cable_sheets.extend(refs)
        elif pg["kind"] == "unit_diagram":
            from renderers.unit_diagrams import build_pages
            body.extend(build_pages(pg, UNIT_DIAGRAMS[pg["model"].upper()], symbols))
        elif pg["kind"] == "kv_io":
            from renderers.keyence import build_pages
            body.extend(build_pages(pg, KV_IO[pg["model"].upper()], symbols))
        elif pg["kind"] in ("remotepulse", "mxio"):
            from renderers.terminal_pages import build_pages
            spec = (REMOTE_PULSE if pg['kind'] == 'remotepulse' else MX_IO)[pg['model'].upper()]
            body += build_pages(pg, spec, symbols, rows)
        elif pg["kind"] == "inverter":
            from renderers.inverter import build_body
            body.append((pg.get("title", pg["model"]), build_body(pg, INVERTERS[pg["model"].upper()], symbols)))
        elif pg["kind"] == "mxbody":
            from renderers.controllers import build_body
            body.append((pg.get('title', pg['model'] + ' 本体'), build_body(pg, MX_CPU[pg['model'].upper()], symbols)))
        elif pg["kind"] == "gotbody":
            from renderers.hmi import build_body
            body.append((pg.get('title', pg['model'] + ' 接続図'), build_body(pg, symbols, GOT_BODY[pg['model'].upper()], Page, Symbol, page_heading, (LANE, LANE_TOP_Y, ctext))))
        elif pg["kind"] in ("gotoption", "qcomm", "iqrcomm", "fxcomm"):
            from renderers.box_layout import single_units
            from renderers.hmi import build_options
            for unit in single_units(pg):
                page = (build_options(unit, symbols, GOT_OPTION, Page, Symbol, page_heading)
                        if pg['kind'] == 'gotoption' else build_q_comm_page(unit, symbols))
                body.append((pg.get('title', unit['left_model'] + ' 接続図'), page))
                pages_of[id(unit)] = [page]
                post_rows.append((unit, rows))
        elif pg["kind"] in ("remotebody", "remoteiolink"):
            body.append((pg.get("title", pg["model"] + " 通信・電源"), build_remote_body_page(pg, symbols)))
            if pg["kind"] == "remoteiolink":
                body += remote_connector_pages(pg, symbols, remote_spec(pg["model"].upper()))
        elif pg["kind"] == "fx5body":
            body.append((pg.get("title", pg["model"] + " 本体"), build_fx5_body_page(pg, symbols)))
        elif pg["kind"] in ("iqrbody", "qbody"):
            body += build_iqr_body_page(pg, symbols)
        elif pg["kind"] == "power":
            body.append((pg.get("title", "電源回路"), build_power_page(pg, cfg, symbols)))
        else:
            halves = iqr_halves(pg, rows)
            for i in range(0, len(halves), 2):
                part = halves[i:i + 2]
                title = pg.get("title", pg["model"]) if len(halves) <= 2 else f"{pg.get('title', pg['model'])} ({i // 2 + 1}/{(len(halves) + 1) // 2})"
                body.append((title, build_iqr_page(rows, pg, cfg, symbols, part)))
            for uc, _ in iqr_units(pg, rows):
                spec = configured_unit(uc)
                if spec.get('io_connectors') and not (pg['kind'] == 'remotemixed' and REMOTE_MIXED[pg['model'].upper()].get('io_connectors')):
                    body += remote_connector_pages(uc, symbols, spec)
                elif spec.get('sensor_pins'):
                    for start in range(0, spec['points'], 8):
                        title = f"{uc['model']} センサ端子 {start + 1}〜{min(start + 8, spec['points'])}"
                        body.append((title, build_sensor_connector_page(uc, symbols, start)))
        if pg['kind'] == 'remotemixed' and REMOTE_MIXED[pg['model'].upper()].get('io_connectors'):
            body += remote_connector_pages(pg, symbols, REMOTE_MIXED[pg['model'].upper()])
        pages_of[id(pg)] = [page for _, page in body[first:]]
        for page in pages_of[id(pg)]:
            if getattr(page, 'identity_headers', False):
                continue
            for text in page.texts:
                if float(text.get('y', '0')) > 60:
                    continue
                scope = pg.get('right', pg) if float(text.get('x', '0')) >= HALF_W else pg
                for model_key, tag_key in (('model','tag'), ('left_model','left_tag'), ('right_model','right_tag')):
                    model, tag = scope.get(model_key, ''), scope.get(tag_key, '').strip()
                    if model and tag and text.get('text', '').upper().startswith(model.upper()):
                        if model_key == 'left_model' and float(text.get('x','0')) >= HALF_W:
                            continue
                        if model_key == 'right_model' and float(text.get('x','0')) < HALF_W:
                            continue
                        text.set('text', tag + '  ' + text.get('text'))
                        break


    # 表紙 → 改訂履歴 → 目次 → 本文
    from project_wiring.data import normalize, page_identity
    from renderers import wiring as wiring_renderer
    wiring_references = []
    for pg, _ in pages_rows:
        wiring = normalize(pg.get('wiring'))
        targets = pages_of[id(pg)]
        for row in wiring['boundaries'] + wiring['connections']:
            if row['part'] > len(targets):
                raise ValueError(f"[{pg.get('model', '')}] 配線情報の分割ページ{row['part']}がありません（全{len(targets)}ページ）")
        for row in wiring['connections']:
            if not row['unit_tag'].strip():
                row['unit_tag'] = page_identity(pg)[1]
        for part, page in enumerate(targets, 1):
            wiring_references += wiring_renderer.apply(page, wiring, part, Symbol,
                                                       f"{pg.get('model', '')} 分割ページ{part}")
    wiring_renderer.link_references(wiring_references)
    if wiring_references:
        ET.SubElement(nd, 'report', label='%f-%c%l')

    from renderers.terminal_plan import build_pages as build_terminal_plan_pages
    body += build_terminal_plan_pages(pages_rows, symbols, Page, table, page_heading)

    revs = cfg.get("_revisions", [])
    latest = revs[-1].get("改訂", cfg["revision"]) if revs else cfg["revision"]
    front = []
    if cfg.get("front_pages", True):
        front.append(("表紙", build_cover(cfg, symbols, latest)))
        front += build_revision_pages(cfg, symbols, revs)
        n_toc = 1
        while True:   # 目次のページ数は総ページ数で決まるので収束するまで数え直す
            total = len(front) + n_toc + len(body)
            entries = [(i + 1, t) for i, (t, _) in enumerate(front)]
            entries += [(len(front) + i + 1, "目次") for i in range(n_toc)]
            entries += [(len(front) + n_toc + i + 1, t) for i, (t, _) in enumerate(body)]
            toc = build_toc_pages(cfg, symbols, entries)
            if len(toc) == n_toc:
                break
            n_toc = len(toc)
        front += toc

    nums = {id(page): i for i, (_, page) in enumerate(front + body, 1)}
    from renderers.cable_routes import label_sheets
    for reference in cable_sheets:
        label_sheets(reference, nums)
    # 構成ページに各ユニットのページ番号を書く(ページ番号が決まってから)
    def page_of(pg_):
        got = pages_of.get(id(pg_))
        return nums[id(got[0])] if got else None
    for _, page in body:
        if hasattr(page, "post"):
            page.post(post_rows, page_of)
    ref_errs = write_references(lambda pg_: nums[id(pg_)])
    if ref_errs:
        raise SystemExit("参照エラー:\n  " + "\n  ".join(ref_errs))
    n_links = sum(1 for c in LINES["contacts"] if c[1] in LINES["coil"])

    cfg = dict(cfg, revision=latest)
    stats = []
    for order, (title, page) in enumerate(front + body, 1):
        page.finish()
        add_diagram(proj, cfg, title, order, page)
        stats.append((title, len(page.elements), len(page.conductors)))

    col = ET.SubElement(proj, "collection")
    imp = ET.SubElement(col, "category", name="import")
    n = ET.SubElement(imp, "names")
    ET.SubElement(n, "name", lang="en").text = "Imported elements"
    ET.SubElement(n, "name", lang="ja").text = "取り込み要素"
    cat = ET.SubElement(imp, "category", name="plc_io")
    n = ET.SubElement(cat, "names")
    ET.SubElement(n, "name", lang="en").text = "PLC I/O"
    ET.SubElement(n, "name", lang="ja").text = "PLC I/O(試作)"
    for sym in symbols.values():
        cat.append(sym.to_xml())
    stats.append((f"区分参照 {n_links} 接点", 0, 0))
    return proj, stats


def validate(rows, pg):
    """iQ-R / Q のユニット: アドレスが機種・先頭アドレスどおりか、ピン指定が配置と合うか"""
    errs = []
    for uc, urows in iqr_units(pg, rows):
        unit = configured_unit(uc)
        tag = f"[{uc.get('csv') or uc['model']}] "
        if unit.get("input_voltages") and str(uc.get("input_voltage", unit["input_voltages"][0])) not in unit["input_voltages"]:
            errs.append(tag + f"{uc['model']} の入力電圧は {', '.join(unit['input_voltages'])} Vから選択してください")
        exp = unit_addrs(uc)
        got = [r["アドレス"].strip().upper() for r in urows]
        if got != exp:
            errs.append(tag + f"アドレスが {uc['model']} と一致しません(16進で {exp[0]}〜{exp[-1]} の {len(exp)} 点"
                        f"、先頭は project.json の start)")
        for i, r in enumerate(urows[:len(exp)]):
            given = r.get("コネクタピン", "").strip().upper()
            if given and given != unit["pins"][i]:
                errs.append(tag + f"{r['アドレス']}: ピン {given} は {uc['model']} の配置({unit['pins'][i]})と一致しません")
        if unit["io"] == "out":
            devs = [r["機器番号"].strip() for r in urows if r["機器番号"].strip()]
            for d in sorted({d for d in devs if devs.count(d) > 1}):
                errs.append(tag + f"機器番号重複: {d}")
    return errs


def validate_fx(pg, in_rows, out_rows):
    exp_in, exp_out = fx_expected(pg)
    errs = []
    if fx_spec(pg).get("sink_only") and pg.get("input_mode", "sink") != "sink":
        errs.append(f"[{pg['model']}] この入力ユニットはシンク入力のみ対応しています")
    for label, rows, exp in (("入力", in_rows, exp_in), ("出力", out_rows, exp_out)):
        got = [r["アドレス"].strip().upper() for r in rows]
        if not exp and not got:
            continue
        if not exp:
            errs.append(f"[{pg['model']}] {label}のないユニットに{label}のCSVが指定されています")
            continue
        if got != exp:
            missing = [a for a in exp if a not in got]
            extra = [a for a in got if a not in exp]
            errs.append(f"[{pg['model']} {label}] アドレスが機種と一致しません"
                        f"(8進数で {exp[0]}〜{exp[-1]} の {len(exp)} 点)"
                        + (f" 不足: {','.join(missing)}" if missing else "")
                        + (f" 余分: {','.join(extra)}" if extra else ""))
    # 出力(コイル・負荷)は1機器1か所。入力の接点は同じ機器を何度使ってもよい(リレー接点など)
    devs = [r["機器番号"].strip() for r in out_rows if r["機器番号"].strip()]
    for d in sorted({d for d in devs if devs.count(d) > 1}):
        errs.append(f"[{pg['model']} 出力] 機器番号重複: {d}")
    return errs


def write_iolist(path, pages_rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ユニット", "アドレス", "用途", "機器番号", "ピン/端子/コモン", "端子台番号", "線番"])
        for pg, rows in pages_rows:
            if pg['kind'] == 'unit_diagram':
                from renderers.unit_diagrams import terminal_records
                for section, terminal in terminal_records(UNIT_DIAGRAMS[pg['model'].upper()]):
                    w.writerow([pg['model'], terminal['signal'], terminal.get('purpose', ''), '',
                                section['name'] + ' ' + terminal.get('pin', ''), '', ''])
                continue
            if pg['kind'] == 'kv_io':
                kv_spec = KV_IO[pg['model'].upper()]
                for terminal in kv_spec.get('analog', {}).get('terminals', []):
                    w.writerow([pg['model'], terminal['signal'], terminal['purpose'], '', terminal['pin'], '', ''])
                module = kv_spec.get('module', {})
                for terminal in module.get('power', []):
                    w.writerow([pg['model'], terminal['signal'], '外部電源' if terminal['lane'] else '接地', '', '', '', ''])
                modes = module.get('modes', {})
                interfaces = modes[pg.get('communication_mode') or next(iter(modes))] if modes else module.get('interfaces', [])
                for interface in interfaces:
                    for terminal in interface.get('pinout', []):
                        w.writerow([pg['model'], terminal['signal'], terminal.get('description', ''), '',
                                    interface['name'] + ' ' + terminal['pin'], '', ''])
                for section in kv_spec['pages']:
                    for side, terminals in enumerate(section['halves']):
                        location = section.get('labels', ['', ''])[side] or section['section']
                        for pin, signal in terminals:
                            w.writerow([pg['model'], signal, '', '', f'{location} {pin}'.strip(), '', ''])
                continue
            if pg['kind'] == 'terminal_block':
                from renderers.cable_routes import iolist_rows
                w.writerows(iolist_rows(pg, *terminal_block_choice(pg)))
                continue
            if pg['kind'] in ('mxbody', 'inverter'):
                continue
            if pg['kind'] in ('mxio', 'remotepulse'):
                from renderers.terminal_pages import terminal_rows
                spec = (MX_IO if pg['kind'] == 'mxio' else REMOTE_PULSE)[pg['model'].upper()]
                for row in terminal_rows(pg, spec, rows):
                    w.writerow([pg['model'], row['signal'], row.get('description', ''), '', row.get('pin', ''), '', ''])
                continue
            if pg["kind"] in ("kvbody", "nxbody", "power", "fx5body", "iqrbody", "qbody", "qcomm", "iqrcomm", "fxcomm", "remotebody", "remoteiolink", "gotbody", "gotoption"):
                continue
            if pg["kind"] in ("fx5analog", "iqranalog", "qanalog", "remoteanalog"):
                for r in rows:
                    w.writerow([pg["model"], "CH" + r["CH"], r.get("用途", ""), "", "", "", ""])
                continue
            if pg["kind"] in ("fx5u", "fx5ext"):
                sp = fx_spec(pg)
                fmt = "+V{}" if sp["kind"] == "source" else "COM{}"
                com_of = {a: fmt.format(no) for no, addrs in sp["groups"] for a in addrs}
                for r in rows["in"] + rows["out"]:
                    a = r["アドレス"].strip().upper()
                    w.writerow([pg["model"], a, r["信号名"], r["機器番号"], com_of.get(a, fx_spec(pg).get("in_common", "S/S")), "",
                                r.get("線番", "").strip() or a])
                continue
            for uc, urows in iqr_units(pg, rows):
                unit = configured_unit(uc)
                for i, r in enumerate(urows):
                    a = r["アドレス"].strip().upper()
                    w.writerow([uc["model"], a, r["信号名"], r["機器番号"],
                                r.get("コネクタピン", "").strip() or unit["pins"][i],
                                r.get("端子台番号", "").strip() or tb_label(uc, i), r.get("線番", "").strip() or a])
                if unit.get("out") == "independent_relay":
                    for i, r in enumerate(urows):
                        w.writerow([uc["model"], r["アドレス"], "外部電源", "", unit["feed_pins"][i], "", ""])
                    continue
                commons = {"COM": unit["common"]} if unit["io"] == "in" else (
                    {"COM": unit["vplus"], "0V": unit["com"]} if unit["out"] == "source" else
                    {"V+": unit["vplus"], "COM": unit["com"]} if unit["out"] == "sink" else {"COM": unit["com"]})
                for pin, name in unit.get("extra_terminals", []):
                    w.writerow([uc["model"], name, "補助端子", "", pin, "", ""])
                for i, pin in enumerate(unit.get('paired_com_pins', [])):
                    name = unit.get('paired_com_labels', ['COM'] * unit['points'])[i]
                    w.writerow([uc['model'], name, 'コモン', '', pin, '', ''])
                if unit.get('paired_power_terminals'):
                    commons = {name:pin for name,pin,lane in unit['paired_power_terminals']}
                if unit.get("input_power_pin"):
                    commons["V+"] = unit["input_power_pin"]
                for name, pins in commons.items():
                    for group in pins if isinstance(pins, list) else [pins]:
                        for pin in group.split("/"):
                            if pin:
                                w.writerow([uc["model"], name, "共通", "", pin, tb_label(uc, pin=pin), ""])


def main(cfg_path, out_path):
    base = os.path.dirname(os.path.abspath(cfg_path))
    with open(cfg_path, encoding="utf-8") as f:
        cfg = project_config(json.load(f))
    if "units_file" in cfg:
        raise SystemExit("units_file は廃止されました。機種別定義フォルダを units_dir に指定してください")
    use_units(os.path.join(base, cfg["units_dir"]) if cfg.get("units_dir") else UNITS_DIR)
    pages_rows, errs, warnings = [], [], []
    def read(name):
        with open(os.path.join(base, name), 'rb') as f:
            data = f.read()
        try:
            content = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            content = data.decode('cp932')
        return list(csv.DictReader(io.StringIO(content, newline='')))

    rev_file = cfg.get("revisions_csv")
    cfg["_revisions"] = read(rev_file) if rev_file else []
    for pg in cfg["pages"]:
        from renderers.settings import LABELS, controls
        try:
            controls(pg)
            keys = [prefix + key for prefix in ('', 'left_', 'right_') for key in LABELS]
            if any(not isinstance(pg.get(key, ''), str) for key in keys):
                raise ValueError('通信・機器設定欄は文字列で指定してください')
        except ValueError as error:
            errs.append(str(error))
            continue
        if pg['kind'] in ('kvbody', 'nxbody'):
            from plc_configuration import validate as validate_configuration
            try:
                validate_configuration(pg, {'kv_io': KV_IO, 'unit_diagram': UNIT_DIAGRAMS})
            except ValueError as error:
                errs.append(str(error))
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'terminal_block':
            try:
                terminal_block_choice(pg)
            except ValueError as error:
                errs.append(str(error))
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'unit_diagram':
            model = str(pg.get('model', '')).upper()
            if model not in UNIT_DIAGRAMS:
                errs.append('未対応のユニットです: ' + model)
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'kv_io':
            model = str(pg.get('model', '')).upper()
            if model not in KV_IO:
                errs.append('未対応のKVユニットです: ' + model)
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'inverter':
            if str(pg.get('model', '')).upper() not in INVERTERS:
                errs.append('対応済みインバータを指定してください')
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] in ('remotepulse', 'mxbody', 'mxio'):
            definitions = {'remotepulse': REMOTE_PULSE, 'mxbody': MX_CPU, 'mxio': MX_IO}[pg['kind']]
            model = str(pg.get('model', '')).upper()
            if model not in definitions:
                errs.append('未対応の形名です: ' + model)
            elif pg['kind'] == 'mxbody' and cpu_option_error(pg, definitions[model]):
                errs.append(cpu_option_error(pg, definitions[model]))
            else:
                if pg['kind'] == 'mxbody':
                    from renderers.controllers import expansion_items
                    try:
                        expansion_items(pg)
                    except ValueError as error:
                        errs.append(str(error))
                rows = read(pg['csv']) if pg.get('csv') and pg['kind'] != 'mxbody' else None
                if pg['kind'] != 'mxbody':
                    from renderers.terminal_pages import terminal_rows
                    try:
                        terminal_rows(pg, definitions[model], rows)
                    except ValueError as error:
                        errs.append(f'[{model}] {error}')
                pages_rows.append((pg, rows))
            continue
        if pg['kind'] == 'gotbody':
            model = str(pg.get('model', '')).upper()
            spec = GOT_BODY.get(model)
            if spec is None:
                errs.append('対応済みGOT本体を指定してください')
            elif pg.get('battery', '要確認') not in ('装着', '非装着', '搭載不可', '要確認'):
                errs.append('GOTのバッテリ状態が不正です')
            elif not spec.get('battery_supported') and pg.get('battery') == '装着':
                errs.append('このGOTにはバッテリを装着できません')
            elif spec.get('battery_supported') and pg.get('battery') == '搭載不可':
                errs.append('このGOTはバッテリを装着可能です')
            elif pg.get('sd_card', '要確認') not in ('有', '無', '要確認'):
                errs.append('SDカード状態は有・無・要確認から選んでください')
            elif not spec.get('sd_card_supported') and pg.get('sd_card') == '有':
                errs.append('このGOTの本体SDカードスロットは使用できません')
            elif pg.get('serial_mode', '') and pg['serial_mode'] not in set(spec.get('serial_modes', {})).union(*(set(i.get('modes', {})) for i in spec['interfaces'])):
                errs.append('このGOTに対応するシリアル方式を指定してください')
            elif any(not isinstance(pg.get(k, ''), str) for k in ('ip', 'station', 'dip', 'sd_card_model')):
                errs.append('GOT設定欄は文字列で指定してください')
            else:
                pages_rows.append((pg, None))
            continue
        if pg['kind'] == 'gotoption':
            models = [pg.get(k, '') for k in ('left_model', 'right_model')]
            if not any(models) or any(not isinstance(m, str) or m and m.upper() not in GOT_OPTION for m in models):
                errs.append('対応済みGOTオプションを左右に指定してください')
            elif any(not isinstance(pg.get(f'{side}_{key}', ''), str) for side in ('left', 'right') for key in ('station', 'ip', 'dip', 'module')):
                errs.append('GOTオプションの設定欄は文字列で指定してください')
            elif any(pg.get(f'{side}_module') and pg.get(f'{side}_module', '').upper() not in GOT_OPTION.get(str(pg.get(f'{side}_model', '')).upper(), {}).get('module_interfaces', {})
                     for side in ('left', 'right')):
                errs.append('GOTオプションの通信モジュールはその機種に対応するものを指定してください')
            else:
                pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("remotebody", "remoteiolink"):
            model = str(pg.get("model", "")).upper()
            spec = remote_spec(model)
            if not spec or (not spec.get("network") and spec.get("module_role") != "extension") or (pg["kind"] == "remoteiolink" and model not in REMOTE_IOLINK):
                errs.append("対応済みリモートIOを指定してください")
            elif any(not isinstance(pg.get(k, ""), str) for k in ("station", "ip", "dip")):
                errs.append("局番・IPアドレス・ディップスイッチは文字列で指定してください")
            else:
                pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("qcomm", "iqrcomm", "fxcomm"):
            values = [pg.get(k, "") for k in ("left_model", "right_model")]
            comm = {'iqrcomm': IQR_COMM, 'qcomm': Q_COMM, 'fxcomm': FX5_COMM}[pg['kind']]
            if any(not isinstance(m, str) for m in values) or not any(values) or any(m and m.upper() not in comm for m in values):
                errs.append("通信ページの左右には対応済みの同一シリーズの通信ユニットを少なくとも1台指定してください")
            elif any(not isinstance(pg.get(f"{side}_{key}", ""), str) for side in ("left", "right") for key in ("station", "ip", "dip")):
                errs.append("通信ユニットの局番・IPアドレス・ディップスイッチ設定は文字列で指定してください")
            else:
                pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("iqrbody", "qbody"):
            model, power_model, base_model = (str(pg.get(k, "")).upper() for k in ("model", "power_model", "base_model"))
            modules = pg.get("modules", [])
            is_q = pg["kind"] == "qbody"
            cpus, powers, bases, analog = (Q_CPU, Q_POWER, Q_BASE, Q_ANALOG) if is_q else (iqr_cpu_positions(), IQR_POWER, IQR_BASE, IQR_ANALOG)
            comm = Q_COMM if is_q else IQR_COMM
            series = "Q" if is_q else "R"
            def module_error(base, modules, reserved=0):
                """1段分のユニットの並びを調べる。問題なければ空文字。reserved: CPU が占めるスロット数(RnENCPU のネットワーク部)"""
                allowed = cpus.get(model, {}).get('compatible_modules')
                if allowed is not None and isinstance(modules, list) and any(m and m not in allowed for m in modules):
                    return 'このCPUに対応するユニットを指定してください'
                if isinstance(modules, list) and any(isinstance(m, str) and comm.get(m.upper(), {}).get('mount_position') == 'cpu_slot' for m in modules):
                    return 'リモートヘッドはCPUスロット（model）に指定してください'
                if not isinstance(modules, list) or len(modules) > bases[base]["slots"] - reserved or any(not isinstance(m, str) or (m and ((not m.upper().startswith(series) and m.upper() not in comm) or m.upper() not in IO_UNITS and m.upper() not in (Q_MIXED if is_q else IQR_MIXED) and m.upper() not in analog and m.upper() not in comm)) for m in modules):
                    return "スロット数またはユニット形名が不正です"
                if any(slot_definition(m.upper(), is_q).get("slots", 1) == 2 and
                                    (i + 1 >= bases[base]["slots"] - reserved or i + 1 < len(modules) and modules[i + 1])
                                    for i, m in enumerate(modules) if m):
                    return "2スロットユニットの次のスロットを空けてください"
                return ""
            extensions = pg.get("extensions", [])
            ext_err = ""
            limit=cpus.get(model,{}).get('max_extension_stages',7)
            if not isinstance(extensions, list) or len(extensions) > limit:
                ext_err = f"このCPUの増設ベースは{limit}段までのリストで指定してください"
            else:
                for i, ext in enumerate(extensions, 1):
                    eb, ep = str(ext.get("base_model", "")).upper(), str(ext.get("power_model", "")).upper()
                    if eb not in bases or not bases[eb].get("extension"):
                        ext_err = f"増設{i}段のベースは対応済みの増設ベースを指定してください"
                    elif bases[eb].get("power_required", True) and ep not in powers:
                        ext_err = f"増設{i}段の電源ユニットを指定してください"
                    elif not bases[eb].get("power_required", True) and ep:
                        ext_err = f"増設{i}段のベース {eb} は電源ユニットを使いません"
                    else:
                        ext_err = module_error(eb, ext.get("modules", []))
                        ext_err = f"増設{i}段: {ext_err}" if ext_err else ""
                    if ext_err:
                        break
            if model not in cpus or power_model not in powers or base_model not in bases or bases[base_model].get("extension"):
                errs.append("構成には対応済みのCPU、電源、ベース(基本ベース)を指定してください")
            elif module_error(base_model, modules, cpus[model].get("network_part", {}).get("slots", 0)):
                errs.append(module_error(base_model, modules, cpus[model].get("network_part", {}).get("slots", 0)))
            elif ext_err:
                errs.append(ext_err)
            elif cpus[model].get('max_module_slots') and sum(bases[b]['slots'] for _,b,_,_ in body_stages(pg))>cpus[model]['max_module_slots']:
                errs.append(f"このCPUの合計スロット数は{cpus[model]['max_module_slots']}までです")
            elif not str(pg.get("empty_slot_points", EMPTY_SLOT_POINTS)).isdigit():
                errs.append("空きスロットの点数(empty_slot_points)は0以上の整数で指定してください")
            elif pg.get("battery", "要確認") not in ("装着", "非装着", "要確認"):
                errs.append("バッテリ状態は装着・非装着・要確認から選んでください")
            elif cpu_option_error(pg,cpus[model]):
                errs.append(cpu_option_error(pg,cpus[model]))
            elif slot_assignments(pg)[1]:
                errs += slot_assignments(pg)[1]
            else:
                warnings += slot_assignments(pg)[2]
                pages_rows.append((pg, None))
            continue
        if pg["kind"] == "fx5body":
            model = pg.get("model", "").upper()
            modules = pg.get('modules', [])
            if model not in FX5U_SPECS or any(FX5U_SPECS[model][key] is None for key in ("battery_supported", "usb_port", "analog", "rs485", "service")):
                errs.append(f"本体図の機種定義が未対応です: {pg.get('model', '')}")
            elif not isinstance(modules, list) or any(not isinstance(m, str) or m.upper() not in FX5_COMM for m in modules):
                errs.append('FX5本体の通信ユニット形名が不正です')
            elif model.startswith('FX5UC-') and any(FX5_COMM[m.upper()]['form'] == 'board' for m in modules):
                errs.append('FX5UCには通信ボードを装着できません')
            elif sum(FX5_COMM[m.upper()]['form'] == 'board' for m in modules) > 1:
                errs.append('FX5の通信ボードは1台までです')
            elif pg.get('board_model', '') not in ('', 'なし', *FX5_BOARDS):
                errs.append('拡張ボードの型式が不正です')
            elif model.startswith('FX5UC-') and pg.get('board_model', '') not in ('', 'なし'):
                errs.append('FX5UCには拡張ボードを装着できません')
            elif pg.get('board_model') == 'FX5-SDCD' and not model.startswith('FX5S-'):
                errs.append('FX5-SDCDはFX5S専用です')
            elif any(FX5_COMM[m.upper()]['form'] == 'board' and pg.get('board_model', '') not in ('', m.upper()) for m in modules):
                errs.append('拡張ボードの指定が重複しています')
            elif sum(FX5_COMM[m.upper()]['form'] == 'adapter' for m in modules) > (2 if model.startswith('FX5UJ-') else 4):
                errs.append('FX5の通信アダプタの台数が上限を超えています')
            elif pg.get('sd_card', '要確認') not in ('有', '無', '要確認'):
                errs.append('SDカードの状態は有・無・要確認から選んでください')
            elif not isinstance(pg.get('sd_card_model', ''), str):
                errs.append('SDカードの型式は文字列で指定してください')
            elif model.startswith('FX5S-') and pg.get('board_model') != 'FX5-SDCD' and (pg.get('sd_card') == '有' or pg.get('sd_card_model', '').strip()):
                errs.append('FX5SでSDカードを使用するには拡張ボードにFX5-SDCDを選択してください')
            else:
                supported = FX5U_SPECS[model]["battery_supported"]
                battery = pg.get("battery", "要確認" if supported else "搭載不可")
                if battery not in ("装着", "非装着", "搭載不可", "要確認"):
                    errs.append(f"電池の指定が不正です: {battery}")
                elif battery == "搭載不可" and supported:
                    errs.append(f"[{pg['model']}] オプション電池が使用できるため「搭載不可」は指定できません")
                elif not supported and battery != "搭載不可":
                    errs.append(f"[{pg['model']}] バッテリは搭載できません")
                pages_rows.append((pg, None))
            continue
        if pg["kind"] == "power":
            pages_rows.append((pg, None))
            continue
        if pg["kind"] in ("fx5analog", "iqranalog", "qanalog", "remoteanalog"):
            model = pg.get("model", "").upper()
            analog_specs = {"iqranalog": IQR_ANALOG, "qanalog": Q_ANALOG, "fx5analog": FX5_ANALOG_SPECS, "remoteanalog": REMOTE_ANALOG}[pg["kind"]]
            if model not in analog_specs:
                errs.append(f"未対応のアナログ機種です: {model}")
                continue
            rows = read(pg["csv"]) if pg.get("csv") else []
            seen = set()
            for r in rows:
                ch = r.get("CH", "").strip()
                if not ch.isascii() or not ch.isdecimal() or not 1 <= int(ch) <= len(analog_specs[model]["channels"]):
                    errs.append(f"[{model}] CHが不正です: {ch}")
                elif int(ch) in seen:
                    errs.append(f"[{model}] CHが重複しています: {ch}")
                else:
                    seen.add(int(ch))
                    r["CH"] = str(int(ch))
                    method = r.get("方式", "").strip()
                    if method:
                        spec_a = analog_specs[model]
                        direction = spec_a["channels"][int(ch) - 1]
                        if spec_a.get("auto_wiring") is False:
                            errs.append(f"[{model}] 自動配線は未対応です。方式を空欄にしてメーカー配線図に従って手動で接続してください")
                        elif method not in ("電圧", "電流"):
                            errs.append(f"[{model}] CH{ch} の方式は 電圧 か 電流 で指定してください: {method}")
                        elif not analog_method_pins(analog_names(spec_a, int(ch) - 1), direction, method):
                            errs.append(f"[{model}] CH{ch} は {method}{direction}の自動配線に対応していません(端子は手で配線)")
            pages_rows.append((pg, rows))
            continue
        if pg["kind"] in ("qmixed", "iqrmixed", "remotemixed"):
            model = str(pg.get("model", "")).upper()
            if model not in ({"qmixed": Q_MIXED, "iqrmixed": IQR_MIXED, "remotemixed": REMOTE_MIXED}[pg["kind"]]):
                errs.append("混合ユニットの形名を指定してください")
                continue
            try:
                start = int(str(pg.get("start", "0")), 16)
                if start < 0: raise ValueError()
            except ValueError:
                errs.append(f"[{model}] 先頭アドレスは0以上の16進数で指定してください")
                continue
            rows = {"in": read(pg["input_csv"]) if pg.get("input_csv") else None,
                    "out": read(pg["output_csv"]) if pg.get("output_csv") else None}
            for uc, _ in iqr_units(pg, {"in": [], "out": []}):
                if rows[uc["_mixed_io"]] is None:
                    rows[uc["_mixed_io"]] = blank_io_rows(uc)
            errs += validate(rows, pg)
        elif pg["kind"] in ("fx5u", "fx5ext"):
            rows = {"in": read(pg["input_csv"]) if pg.get("input_csv") else [],
                    "out": read(pg["output_csv"]) if pg.get("output_csv") else []}
            errs += validate_fx(pg, rows["in"], rows["out"])
        else:
            if not pg.get("csv") and str(pg.get("model", "")).upper() not in IO_UNITS:
                errs.append(f"[{pg.get('model', '')}] 対応済みの入出力ユニットを指定してください")
                continue
            rows = read(pg["csv"]) if pg.get("csv") else blank_io_rows(pg)
            if pg.get("right"):
                pg["_right_rows"] = read(pg["right"]["csv"])
            errs += validate(rows, pg)
        pages_rows.append((pg, rows))
    if errs:
        print("入力エラー:\n  " + "\n  ".join(errs))
        sys.exit(1)
    warnings += page_start_warnings(cfg["pages"])
    if warnings:
        # 割付の誤りらしきものは知らせるだけで、値は直さない
        print("警告（XY割付）:\n  " + "\n  ".join(warnings))
    try:
        proj, stats = build_project(cfg, pages_rows)
    except ValueError as error:
        raise SystemExit(f"入力エラー:\n  {error}") from error
    xml = minidom.parseString(ET.tostring(proj, encoding="unicode")).toprettyxml(indent="    ")
    xml = xml.split("\n", 1)[1]  # QElectroTech 形式に合わせ XML宣言を外す
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    list_path = out_path.rsplit(".", 1)[0] + "_iolist.csv"
    write_iolist(list_path, pages_rows)
    from project_wiring.data import terminal_rows, write_terminal_csv
    terminal_records = terminal_rows(pages_rows)
    if terminal_records:
        terminal_path = out_path.rsplit('.', 1)[0] + '_terminals.csv'
        write_terminal_csv(terminal_path, terminal_records)
        print(f"端子台接続表: {terminal_path}")
    for title, ne, nc in stats:
        print(f"  {title}: 要素 {ne} / 配線 {nc}")
    print(f"出力: {out_path}\n帳票: {list_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(*sys.argv[1:])
