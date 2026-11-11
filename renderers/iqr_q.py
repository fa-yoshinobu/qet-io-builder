"""MELSEC iQ-R/Qの本体・デジタル入出力図。"""
import copy
from drawing import (
    COM_Y, FX_IN_X, HALVES, IN_TEXTS, IN_X, LANE,
    LANE_TOP_Y, OUT_TEXTS, OUT_X, Page, ROW_PITCH, ROW_Y0,
    Symbol, TABLE_ROW, comment_text, comment_value, ctext, draw_rj45,
    io_table_header, output_lane_labels, page_heading, table, u
)
from unit_catalog import (
    EMPTY_SLOT_POINTS, IQR_BASE, IQR_POWER, Q_BASE, Q_CPU, Q_POWER,
    body_stages, configured_unit, iqr_cpu_positions, iqr_units, slot_assignments, slot_definition,
    slot_points, slot_summary
)
from renderers.typography import (
    TEXT_MARGIN, text_w, wrap2
)
from renderers.relay_references import (
    coil_texts, contact_key, line_no, load_key, ref_header, register_coil,
    register_contact, row_ys, tb_label
)
from renderers.plc_symbols import (
    iqr_cpu_symbol, iqr_netpart_symbol, iqr_power_symbol
)


def iqr_halves(pg, rows):
    """ページの半分ごとに (ユニット設定, その半分の行, ユニット内の何番目の半分, 1点目の番号)"""
    halves = []
    for uc, urows in iqr_units(pg, rows):
        unit = configured_unit(uc)
        per_half = 8 if unit.get('paired_com_pins') else 16
        halves += [(uc, urows[i:i + per_half], i // per_half, i) for i in range(0, unit["points"], per_half)]
    return halves

def iqr_input_half(p, off, uc, rows, h, base):
    unit = configured_unit(uc)
    X = {k: v + off for k, v in IN_X.items()}
    pin_title = '端子' if unit.get('terminal_block') or unit['points']<32 else 'ピン'
    io_table_header(p,uc,X['plc']+4,250,(45,100),(pin_title,'アドレス','用途'))
    p.text(X["tb"] - 18, 46, uc.get("tb_name", "TB"), 8, True)
    voltage = str(uc.get("input_voltage", unit.get("input_voltages", [""])[0]))
    lanes = {"P": "P" + voltage, "N": "N" + voltage} if voltage else LANE
    p.power_lane_label(X["P"], lanes["P"])
    p.power_lane_label(X["N"], lanes["N"])

    common_lane = "N" if unit.get("input_common") == "negative" else "P"
    contact_lane = "P" if common_lane == "N" else "N"
    p_top = p.place("junction", X[common_lane], LANE_TOP_Y)
    prev_n = p.place("junction", X[contact_lane], LANE_TOP_Y)
    for i, r in enumerate(rows):
        y = ROW_Y0 + ROW_PITCH * (2 if unit.get('paired_com_pins') else 1) * i
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        ab = "b" if r.get("接点", "").strip().lower() == "b" else "a"
        n = line_no(p, X["num"], y)
        nj = p.place("junction", X[contact_lane], y)
        p.wire(prev_n, "s", nj, "n")
        prev_n = nj
        ct = p.place(contact_key(dev, ab), X["contact"], y, label=dev, texts=[("label", -24, -27, 8, True)])
        register_contact(p, dev, ab, n, X["contact"], y)
        tb = p.place("tb_terminal", X["tb"], y, label=r.get("端子台番号", "").strip() or tb_label(uc, base + i),
                     texts=[("label", -10, -22, 7, False)])
        cv = wrap2(comment_value(r), 136, 8)
        pin = r.get("コネクタピン", "").strip() or unit["pins"][base + i]
        plc = p.place("plc_in", X["plc"], y, label=addr, comment=cv, infos={"auxiliary1": pin},
                      texts=IN_TEXTS[:2] + [comment_text(cv, 108, 142, 8, ROW_PITCH)])
        p.wire(nj, "e", ct, "w")
        p.wire(ct, "e", tb, "w", num=r.get("線番", "").strip() or addr, show=True)
        p.wire(tb, "e", plc, "t")

        if unit.get('paired_com_pins'):
            label = unit['paired_com_labels'][base + i]
            lane = 'P' if label == 'COM A' else 'N'
            cy = y + ROW_PITCH
            common = p.place('plc_in', X['plc'], cy, label=label, comment='コモン',
                             infos={'auxiliary1':unit['paired_com_pins'][base+i]}, texts=IN_TEXTS)
            tb_com = p.place('tb_terminal',X['tb'],cy,label='',texts=[('label',-10,-22,7,False)])
            j = p.place('junction',X[lane],cy)
            previous = p_top if lane == common_lane else prev_n
            p.wire(previous,'s',j,'n')
            if lane == common_lane: p_top=j
            else: prev_n=j
            p.wire(j,'e',tb_com,'w',num=lanes[lane])
            p.wire(tb_com,'e',common,'t',num=lanes[lane],show=True)

    if unit.get('paired_com_pins'):
        if h == 0:
            for k, (label,pin,lane) in enumerate(unit['paired_power_terminals']):
                y = COM_Y + k * ROW_PITCH
                plc = p.place('plc_in',X['plc'],y,label=label,comment='外部電源',infos={'auxiliary1':pin},texts=IN_TEXTS)
                j = p.place('junction',X[lane],y)
                previous = p_top if lane == common_lane else prev_n
                p.wire(previous,'s',j,'n')
                if lane == common_lane: p_top=j
                else: prev_n=j
                p.wire(j,'e',plc,'t',num=lanes[lane],show=True)
        p.extend_lanes([X['P'],X['N']])
        return

    if unit.get("manual_input_power"):
        if not unit.get('extra_terminals'):
            from .communication import draw_notes
            draw_notes(p, 30, 1200, [unit.get('manual_input_note', '入力電源は構成ページを参照')])
        p.extend_lanes([X["P"], X["N"]])
        return
    # 一つの端子しかない32点機種は、同一端子を左右に重複して描かない。
    if unit["points"] == 32 and len(unit["common"]) == 1 and h == 1:
        p.extend_lanes([X["P"], X["N"]])
        return
    coms = unit["common"] if unit.get("common_group_points") == 8 or unit.get("show_all_commons") else [unit["common"][min(h, len(unit["common"]) - 1)]]
    terminals = [("COM", pin, common_lane) for pin in coms]
    if unit.get("input_power_pin"):
        terminals.append(("V+", unit["input_power_pin"], "P"))
    for i, (label, pin, lane) in enumerate(terminals):
        label = unit.get('terminal_names', {}).get(pin, label)
        y = COM_Y + i * ROW_PITCH
        line_no(p, X["num"], y)
        pj = p.place("junction", X[lane], y)
        previous = p_top if lane == common_lane else prev_n
        p.wire(previous, "s", pj, "n")
        if lane == common_lane: p_top = pj
        else: prev_n = pj
        tb = p.place("tb_terminal", X["tb"], y, label=tb_label(uc, pin=pin),
                     texts=[("label", -14, -22, 7, False)])
        plc = p.place("plc_in", X["plc"], y, label=label, comment='外部電源' if label == 'V+' else 'コモン',
                      infos={"auxiliary1": pin}, texts=IN_TEXTS)
        p.wire(pj, "e", tb, "w", num=lanes[lane])
        p.wire(tb, "e", plc, "t", num=lanes[lane], show=True)
    p.extend_lanes([X["P"], X["N"]])

def iqr_output_half(p, off, uc, rows, h, base):
    """シンク: 負荷は P24 から、V+ → P24、COM → N24。リレー: 負荷は N24 へ、COM → P24"""
    unit = configured_unit(uc)
    if unit["out"] == "independent_relay":
        return iqr_independent_relay_half(p, off, uc, rows, base)
    X = {k: v + off for k, v in OUT_X.items()}
    sink = unit["out"] == "sink"
    load_lane, other_lane = ("P", "N") if sink else ("N", "P")   # 内側(X["P"])が負荷側のレーン
    pin_title = '端子' if unit.get('terminal_block') or unit['points']<32 else 'ピン'
    io_table_header(p,uc,X['plc']-234,230,(130,185),('用途','アドレス',pin_title))
    ref_header(p, X["ref"], 46)
    p.text(X["tb"] - 18, 46, uc.get("tb_name", "TB"), 8, True)
    output_lane_labels(p,X['P'],LANE[load_lane],X['N'],LANE[other_lane])

    prev_in = p.place("junction", X["P"], LANE_TOP_Y)      # 負荷側のレーン
    prev_out = p.place("junction", X["N"], LANE_TOP_Y)     # 反対側のレーン
    ys, _, _ = row_ys(rows, ROW_Y0, ROW_PITCH)
    if unit.get('paired_com_pins'):
        ys = [ROW_Y0 + ROW_PITCH * 2 * i for i in range(len(rows))]
    if ys[-1] > COM_Y - 40:                       # 入りきらなければ間隔を広げない
        ys = [ROW_Y0 + ROW_PITCH * i for i in range(len(rows))]
    for i, (r, y) in enumerate(zip(rows, ys)):
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        kind = load_key(dev, r.get("負荷", ""))
        cv = wrap2(comment_value(r), 116, 8)
        pin = r.get("コネクタピン", "").strip() or unit["pins"][base + i]
        plc = p.place("plc_out", X["plc"], y, label=addr, comment=cv, infos={"auxiliary1": pin},
                      texts=[comment_text(cv, -228, 122, 8, ROW_PITCH)] + OUT_TEXTS[1:])
        tb = p.place("tb_terminal", X["tb"], y, label=r.get("端子台番号", "").strip() or tb_label(uc, base + i),
                     texts=[("label", -10, -22, 7, False)])
        ld = p.place(kind, X["load"], y, label=dev, infos={"auxiliary1": dev},
                     texts=coil_texts(kind, -27, X["ref"] - X["load"]))
        register_coil(p, dev, line_no(p, X["num"], y), X["ref"], y, X["load"])
        p.wire(plc, "t", tb, "w")
        p.wire(tb, "e", ld, "w", num=r.get("線番", "").strip() or addr, show=True)
        if unit.get('paired_com_pins'):
            # 出力ごとの COM 端子(負荷電源の分配端子。内部で電源端子につながる)。負荷は Y とこの端子の間につなぐ
            cy = y + ROW_PITCH
            label = unit.get('paired_com_labels', ['COM'] * unit['points'])[base+i]
            common = p.place('plc_out', X['plc'], cy, label=label, comment='コモン',
                             infos={'auxiliary1': unit['paired_com_pins'][base + i]}, texts=OUT_TEXTS)
            common_tb = p.place('tb_terminal', X['tb'], cy, label='', texts=[('label', -12, -22, 7, False)])
            p.wire(common, 't', common_tb, 'w')
            # 右向き端子同士を1本で結ぶ。折り返し用のダミー端子は段差・短い枝線の原因になる。
            p.wire(ld, 'e', common_tb, 'e')
        else:
            pj = p.place("junction", X["P"], y)
            p.wire(prev_in, "s", pj, "n")
            prev_in = pj
            p.wire(ld, "e", pj, "w")

    # 電源・コモンの行: (表示, 端子, つなぐレーン)
    vplus = unit.get("vplus", "")
    com = unit["com"]
    if isinstance(vplus, list): vplus = vplus[h if unit.get("common_by_half") else h // 2]
    if isinstance(com, list): com = com[h if unit.get("common_by_half") else h // 2]
    if unit["out"] == "source":
        com_rows = [("COM", vplus, "P"), ("0V", com, "N")] if unit["points"] <= 16 else (
            [("COM", vplus, "P")] if h % 2 == 0 else [("0V", com, "N")])
        com_rows = [row for row in com_rows if row[1]]
    elif sink:
        com_rows = []
        if vplus and (unit.get("common_by_half") or unit["points"] <= 16 or h % 2 == 0):
            com_rows.append(("V+", vplus, "P"))
        if com and (unit.get("common_by_half") or unit["points"] <= 16 or h % 2 == 1):
            com_rows.append(("COM", com, "N"))
    else:
        com_rows = [("COM", unit["com"], "P")] if unit["com"] else []
    if unit.get('paired_com_pins') and h:
        com_rows = []
    elif unit.get('paired_com_pins'):
        com_rows = unit.get('paired_power_terminals', [('DC24V', vplus, 'P'), ('DC24G', com, 'N')])
    if unit.get("manual_output_note"):
        from .communication import draw_notes
        draw_notes(p, 30, 1200, [unit['manual_output_note']])
    if sum(len(pin.split('/')) for _, pin, _ in com_rows) <= 2:
        com_rows = [(lab, part, lane) for lab, pin, lane in com_rows for part in pin.split('/') if part]
    for k, (lab, pin, lane) in enumerate(com_rows):
        lab = unit.get('terminal_names', {}).get(pin, lab)
        y = COM_Y + ROW_PITCH * k          # 2行(V+ と COM)のときは下に続けて並べる
        line_no(p, X["num"], y)
        key = 'plc_out'
        contacts = pin.split('/')
        if len(contacts) > 1:
            key = 'plc_out_common_' + str(len(contacts))
            if key not in p.sym:
                s = copy.deepcopy(p.sym['plc_out']); s.name = key
                s.terminals = {k: (u(), o, x, y) for k, (_, o, x, y) in s.terminals.items()}
                for ti in range(1, len(contacts)):
                    dy = ti * 10
                    s.circle(-10, dy - 3, 6)
                    s.terminal('t' + str(ti + 1), 'e', -4, dy)
                p.sym[key] = s
        plc = p.place(key, X["plc"], y, label=lab, comment='外部電源' if lab in ('V+', '0V', 'DC24V', 'DC24G') else 'コモン',
                      infos={"auxiliary1": pin}, texts=OUT_TEXTS)
        tb = p.place("tb_terminal", X["tb"], y, label=tb_label(uc, pin=pin), texts=[("label", -12, -22, 7, False)])
        p.wire(plc, "t", tb, "w")
        if lane == load_lane:
            j = p.place("junction", X["P"], y)
            p.wire(prev_in, "s", j, "n")
            prev_in = j
        else:
            j = p.place("junction", X["N"], y)
            p.wire(prev_out, "s", j, "n")
            prev_out = j
        p.wire(tb, "e", j, "w", num=LANE[lane], show=True)
    p.extend_lanes([X["P"], X["N"]])

def iqr_independent_relay_half(p, off, uc, rows, base):
    """各接点の両端を別々に表示し、外部側のみ配線する。"""
    unit = configured_unit(uc)
    X = {k: v + off for k, v in OUT_X.items()}
    io_table_header(p,uc,X['plc']-234,230,(130,185),('用途','アドレス','端子'))
    p.text(X["tb"] - 18, 46, uc.get("tb_name", "TB"), 8, True)
    ref_header(p, X["ref"], 46)
    output_lane_labels(p,X['P'],LANE['N'],X['N'],LANE['P'])
    prev_n = p.place("junction", X["P"], LANE_TOP_Y)
    prev_p = p.place("junction", X["N"], LANE_TOP_Y)
    for i, r in enumerate(rows):
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        y = ROW_Y0 + i * ROW_PITCH * 2
        p.rect(X["plc"] - 106, y - 15, X["plc"] + 24, y + ROW_PITCH + 15, dash=False)
        feed = p.place("plc_out", X["plc"], y, label=addr, comment="外部電源",
                       infos={"auxiliary1": unit["feed_pins"][base + i]}, texts=OUT_TEXTS)
        ftb = p.place("tb_terminal", X["tb"], y, label="", texts=[("label", -10, -22, 7, False)])
        pj = p.place("junction", X["N"], y)
        p.wire(prev_p, "s", pj, "n"); prev_p = pj
        p.wire(feed, "t", ftb, "w"); p.wire(ftb, "e", pj, "w", num=LANE["P"], show=True)
        y += ROW_PITCH
        cv = wrap2(comment_value(r), 116, 8)
        plc = p.place("plc_out", X["plc"], y, label=addr, comment=cv,
                      infos={"auxiliary1": unit["pins"][base + i]},
                      texts=[comment_text(cv, -228, 122, 8, ROW_PITCH)] + OUT_TEXTS[1:])
        tb = p.place("tb_terminal", X["tb"], y, label=r.get("端子台番号", "").strip() or tb_label(uc, base + i),
                     texts=[("label", -10, -22, 7, False)])
        kind = load_key(dev, r.get("負荷", ""))
        ld = p.place(kind, X["load"], y, label=dev, infos={"auxiliary1": dev},
                     texts=coil_texts(kind, -27, X["ref"] - X["load"]))
        register_coil(p, dev, line_no(p, X["num"], y), X["ref"], y, X["load"])
        nj = p.place("junction", X["P"], y)
        p.wire(prev_n, "s", nj, "n"); prev_n = nj
        p.wire(plc, "t", tb, "w"); p.wire(tb, "e", ld, "w", num=r.get("線番", "").strip() or addr, show=True)
        p.wire(ld, "e", nj, "w")
    p.extend_lanes([X["P"], X["N"]])

def build_iqr_page(rows, pg, cfg, symbols, halves=None):
    p = Page(symbols)
    for (uc, hrows, h, base), off in zip(halves if halves is not None else iqr_halves(pg, rows), HALVES):
        unit = configured_unit(uc)
        if unit["io"] == "in":
            iqr_input_half(p, off, uc, hrows, h, base)
        else:
            iqr_output_half(p, off, uc, hrows, h, base)
        if h == 0:
            X = {k:v+off for k,v in (IN_X if unit['io']=='in' else OUT_X).items()}
            for i, (pin, name) in enumerate(unit.get('extra_terminals', [])):
                y = ROW_Y0 + ROW_PITCH * (len(hrows) + i)
                key, texts = ('plc_in', IN_TEXTS) if unit['io']=='in' else ('plc_out', OUT_TEXTS)
                terminal = p.place(key, X['plc'], y, label=name,
                                   comment='コモン' if name.startswith('COM') else '外部電源',
                                   infos={'auxiliary1':pin}, texts=texts)
                tb = p.place('tb_terminal', X['tb'], y, label=tb_label(uc, pin=pin),
                             texts=[('label',-12,-22,7,False)])
                if unit['io']=='in':
                    p.wire(tb,'e',terminal,'t')
                else:
                    p.wire(terminal,'t',tb,'w')
    return p

build_input_page = build_output_page = build_iqr_page

def build_iqr_body_page(pg, symbols):
    """iQ-R / Q の電源・CPU・ベースとスロットを、実機の並びに近い形で描く。
    増設ベースがあれば段ごとに下へ並べる(1ページ2段まで。入らなければ次のページ)。戻り値: [(名称, ページ)]"""
    is_q = pg["kind"] == "qbody"
    series = "MELSEC-Q" if is_q else "MX-R" if pg["model"].upper().startswith("MXR") else "iQ-R"
    cpus, powers, bases = (Q_CPU, Q_POWER, Q_BASE) if is_q else (iqr_cpu_positions(), IQR_POWER, IQR_BASE)
    stages = body_stages(pg)
    per_page = 1 if len(stages) == 1 else 2
    MH = 380 if per_page == 1 else 190          # ユニットの高さ(電源・CPU・スロットで共通)
    TOP, RX, SLOT_W = 80, 205, 73               # RX: ベースの左端(電源の端子は左へ出るので、その左は配線用に空ける)
    ROW_H = MH + 40 + 34                        # 1段の高さ(ベースの枠 + 段の見出し)
    centered = lambda t, size, cx: round(cx - text_w(t, size) / 2 - TEXT_MARGIN, 1)
    empty_points = int(pg.get("empty_slot_points", EMPTY_SLOT_POINTS))
    cpu = pg["model"].upper()

    def power_symbol(model):
        power = powers[model]
        base = "iqr_dc" if power["supply"] == "DC" else ("iqr_ac_24" if power["service_24v"] else "iqr_ac")
        key = f"{base}_{model}_{MH}" if power.get("terminal_labels_top_to_bottom") else (base if MH == 380 else f"{base}_{MH}")
        if key not in symbols:
            symbols[key] = iqr_power_symbol(key, power["supply"], power["service_24v"], MH, power.get("terminal_labels_top_to_bottom"), power.get('additional_terminals'))
        return key

    def cpu_symbol():
        if cpu.startswith('MXR'):
            from renderers.controllers import mxr_symbol
            key = f'mxr_cpu_{MH}'
            if key not in symbols:
                symbols[key] = mxr_symbol(key, MH)
            return key
        if cpus[cpu].get('module_role') == 'remote_head':
            key = f'iqr_remote_head_{MH}'
            if key not in symbols:
                # CPU と同じ幅・位置(電源との間に隙間を作らない)。中身は箱の中央(x=30)にそろえる
                head = Symbol(key, 'リモートヘッド', 80, MH, 10, 0)
                head.rect(-10, 0, 80, MH)
                for i in range(2):
                    draw_rj45(head, 10, 65 + i * 50)
                head.rect(14, 160, 32, 12)
                symbols[key] = head
            return key
        key = "iqr_cpu" + ("_lan" if cpus[cpu]["ethernet"] else "") + ("_usb" if cpus[cpu]["usb_port"] else "")
        joined = bool(cpus[cpu].get("network_part"))
        if joined:
            key += "_en"
        if MH != 380 or joined:
            key += f"_{MH}" if MH != 380 else ""
            if key not in symbols:
                symbols[key] = iqr_cpu_symbol(key, cpus[cpu]["ethernet"], cpus[cpu]["usb_port"], MH, joined)
        return key

    assignments, _, _ = slot_assignments(pg)
    pages, slot_no, address, used = [], 0, 0, set()
    for start in range(0, len(stages), per_page):
        p = Page(symbols)
        chunk = stages[start:start + per_page]
        title = f"{series} ユニット構成" + (f" ({start // per_page + 1}/{(len(stages) + per_page - 1) // per_page})"
                                          if len(stages) > per_page else "")
        page_heading(p, f"{series} ユニット構成  ベース: " + "・".join(st[1] for st in stages) if start == 0 else title, x=RX)
        # 実際に給電先を接続したレーンだけを finish 時に残す。
        for name, lx in (("P", FX_IN_X["outer"]), ("N", FX_IN_X["inner"])):
            p.power_lane_label(lx, LANE[name])
            p.place("junction", lx, LANE_TOP_Y)
        p.extend_lanes([FX_IN_X["outer"], FX_IN_X["inner"]])
        slot_boxes = []
        for r, (stage, base_model, power_model, modules) in enumerate(chunk):
            y0 = TOP + r * ROW_H + (24 if per_page > 1 else 0)
            slots = bases[base_model]["slots"]
            x = RX + 10                                  # ユニットを左から隙間なく並べる
            units_x0 = x
            if per_page > 1:
                p.text(RX, y0 - 22, f"{stage}  {base_model}", 9, True)
            if power_model:
                stage_config = pg if stage == '基本' else pg['extensions'][start+r-1]
                p.place(power_symbol(power_model), x + 10, y0 + 20, label=power_model, tag=stage_config.get('power_tag',''),
                        texts=[("label", centered(power_model, 10, 25), 20, 10, True)])
                x += 70
            netpart = None
            if stage == "基本":
                p.place(cpu_symbol(), x + 10, y0 + 20, label=cpu, tag=pg.get('tag',''), texts=[("label", centered(cpu, 9, 30), 20, 9, True)])
                x += 80
                netpart = cpus[cpu].get("network_part")      # RnENCPU: CPU の右のネットワーク部がスロット0を占める
            p.rect(RX, y0, x + slots * SLOT_W + 10, y0 + MH + 40, dash=False)
            stage_config = pg if stage == '基本' else pg['extensions'][start+r-1]
            if stage_config.get('base_tag'):
                p.text(RX+10, y0+MH+25, stage_config['base_tag'], 9, True)
            offset = netpart.get("slots", 1) if netpart else 0
            for i in range(slots):
                sx, sy = round(x + i * SLOT_W, 1), y0 + 20
                address = assignments[start + r][i]["start"]
                j = i - offset
                module = modules[j].upper() if j >= 0 and j < len(modules) and modules[j] else ""
                previous = modules[j - 1].upper() if j > 0 and j - 1 < len(modules) and modules[j - 1] else ""
                current_spec, previous_spec = slot_definition(module, is_q), slot_definition(previous, is_q)
                power_front = bool(current_spec.get('power_ports') and current_spec.get('slot_io_points') == [16, 32])
                network_back = bool(previous_spec.get('power_ports') and previous_spec.get('slot_io_points') == [16, 32])
                if i < offset:
                    p.line(sx, sy, sx + SLOT_W, sy, width=1.0)
                    p.line(sx, sy + MH, sx + SLOT_W, sy + MH, width=1.0)
                    p.line(sx, sy, sx, sy + MH, width=1.5, dash=True)
                    if i == offset - 1:
                        p.line(sx + SLOT_W, sy, sx + SLOT_W, sy + MH, width=1.5)
                elif power_front or network_back:
                    p.line(sx, sy, sx + SLOT_W, sy, width=1.5)
                    p.line(sx, sy + MH, sx + SLOT_W, sy + MH, width=1.5)
                    if power_front:
                        p.line(sx, sy, sx, sy + MH, width=1.5)
                    else:
                        p.line(sx, sy, sx, sy + MH, width=1.5, dash=True)
                        p.line(sx + SLOT_W, sy, sx + SLOT_W, sy + MH, width=1.5)
                else:
                    p.rect(sx, sy, sx + SLOT_W, sy + MH, dash=False)
                cx = sx + SLOT_W / 2
                ctext(p, cx, sy + 16, f"{slot_no}", 9, True)
                p.line(sx, sy + 30, sx + SLOT_W, sy + 30, width=0.5)
                if i < offset:
                    # ネットワーク部(CPU と一体。RJ71EN71 相当)。ポート P1・P2 は下へ配線する
                    ports = netpart.get('ports_by_slot', [netpart['ports']])[i] if netpart.get('ports_by_slot') else netpart['ports']
                    key = f"iqr_netpart_{MH}_" + '_'.join(ports)
                    if key not in symbols:
                        symbols[key] = iqr_netpart_symbol(key, ports, SLOT_W, MH - 30)
                    p.place(key, sx, sy + 30)
                    points = netpart.get("points", 32)
                    if MH >= 300:
                        ctext(p, cx, sy + 52, netpart.get("names_by_slot", ["ネットワーク部"] * offset)[i], 7, True)
                        if netpart.get("equivalent"):
                            ctext(p, cx, sy + 72, f"{netpart['equivalent']}相当", 7)
                        ctext(p, cx, sy + 93, f"X/Y{address:03X}〜", 7)
                        ctext(p, cx, sy + 107, f"X/Y{address + points - 1:03X}", 7)
                    else:                                    # 2段構成: 低いので2行にまとめる
                        ctext(p, cx, sy + 42, netpart.get("names_by_slot", ["ネットワーク部"] * offset)[i], 7, True)
                        ctext(p, cx, sy + 56, f"X/Y{address:03X}〜{address + points - 1:03X}", 6)
                    address += points
                    slot_no += 1
                    continue
                reserved = slot_definition(previous, is_q).get("slots", 1) == 2
                display_module = previous if network_back else '' if power_front else module
                name = '外部供給電源' if power_front else display_module or ("占有" if reserved else "空き")
                size = next((z for z in (9, 8, 7, 6) if text_w(name, z) <= SLOT_W - 12), 6)   # 隣のスロットに掛からないよう余白を取る
                ctext(p, cx, sy + 52, name, size, bool(display_module) or power_front)
                tags = stage_config.get('module_tags', [])
                tag_index = j - 1 if network_back else j
                tag = tags[tag_index].strip() if display_module and tag_index < len(tags) and tags[tag_index] else ''
                if display_module and tag:
                    ctext(p, cx, sy + MH - 46, tag, 9, True)
                info = slot_summary(display_module, is_q) if display_module else ""
                info_size = next((z for z in (8, 7, 6)
                                  if all(text_w(line, z) <= SLOT_W - 4
                                         for line in wrap2(info, SLOT_W - 8, z).split('\n'))), 6)
                lines = wrap2(info, SLOT_W - 8, info_size).split('\n') if info else []
                for k, part in enumerate(lines):
                    ctext(p, cx, sy + 72 + k * 15, part, info_size)
                # 先頭アドレス(16進)。占有スロットはアドレスを使わない
                points, kind = (0, "") if reserved else slot_points(module, is_q, empty_points)
                if power_front:
                    points = 0
                elif network_back:
                    address = assignments[start + r][i - 1]['start'] + previous_spec['slot_io_points'][0]
                    points, kind = previous_spec['slot_io_points'][1], 'X/Y'
                if points:
                    for k, label in enumerate((f"{kind}{address:03X}〜", f"{kind}{address + points - 1:03X}")):
                        ctext(p, cx, sy + MH - 84 + k * 14, label, 7)
                    address += points
                if display_module:
                    slot_boxes.append((display_module, tag, cx, sy + MH - 24))
                slot_no += 1
        if start == 0:
            # CPU に関すること(電池・SD・メモリカセット)は欄外の表に書く(USB・Ethernet は CPU の箱に絵で描く)
            def option_value(key, supported):
                if supported is False:
                    return '搭載不可'
                state=pg.get(key,'要確認')
                model=pg.get(key+'_model','')
                if key == 'battery' and cpu.startswith('MXR') and not model:
                    model = cpus[cpu]['battery_type']
                return state+(' ('+model+')' if model and state in ('有','装着') else '')
            info_rows = [["バッテリ", option_value('battery',cpus[cpu].get('battery_supported'))]]
            if cpus[cpu].get('batteryless_supported'):
                value = pg.get('batteryless', '要確認')
                info_rows.append(['バッテリレス', value + (' (' + cpus[cpu]['batteryless_model'] + ')' if value == '有' else '')])
            if cpus[cpu].get("cc_link_ie"):
                info_rows.append([cpus[cpu].get("network_type", "CC-Link IE"), "あり"])
            info_rows += [["SDメモリカード",option_value('sd_card',cpus[cpu].get('sd_card_supported',False))]]
            if cpus[cpu].get('memory_card_supported'):
                info_rows.append(['メモリカード',option_value('memory_card',True)])
            info_rows.append(['メモリカセット',option_value('memory_cassette',cpus[cpu].get('memory_cassette_supported',False))])
            from .communication import draw_notes
            note = f"※先頭アドレスは空きスロット{empty_points}点・アナログ16点・通信ユニット32点として自動で割り付けた値"
            footer = draw_notes(p, 30, 1200, [note])
            ty = min(790, footer - 8) - (len(info_rows) + 1) * TABLE_ROW
            p.text(RX, ty - 24, "CPUの設定/オプション", 9, True)
            table(p, RX, ty, [("項目", 140), ("内容", 180)], info_rows)

        def post(pages_rows, page_of, p=p, slot_boxes=slot_boxes):
            """タグがあれば形名と組で照合し、未指定時は同形名の登場順に対応させる。"""
            for module, tag, cx, ty in slot_boxes:
                for other, _ in pages_rows:
                    if other is pg:
                        continue
                    identities = [(other.get(m, ''), other.get(t, ''))
                                  for m, t in (('model', 'tag'), ('left_model', 'left_tag'), ('right_model', 'right_tag'))]
                    identities.append((other.get('right', {}).get('model', ''), other.get('right', {}).get('tag', '')))
                    for index, (model, other_tag) in enumerate(identities):
                        identity = (id(other), index)
                        if identity in used or str(model).upper() != module or (tag and tag != str(other_tag).strip()):
                            continue
                        n = page_of(other)
                        if n:
                            used.add(identity)
                            ctext(p, cx, ty, f"→ {n}頁", 8, True)
                        break
                    else:
                        continue
                    break
        if start == 0:
            from renderers import settings
            settings.draw(p, settings.fields(model=cpu, values=pg), pg, RX + 360, RX + 680, bottom=750)
        p.post = post
        pages.append((pg.get("title", title), p))
    return pages
