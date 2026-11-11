"""MELSEC FX5の本体・デジタル入出力図。"""
import copy
from drawing import (
    BORDER_COLS, COL_SIZE, FX_IN_TEXTS, FX_IN_X, FX_OUT_TEXTS, FX_OUT_X,
    HALF_W, LANE, LANE_TOP_Y, Page, TABLE_ROW, comment_text,
    comment_value, ctext, io_table_header, output_lane_labels, table, u,
    unit_identity_header, vcenter
)
from unit_catalog import (
    FX5U_SPECS, FX5_ANALOG_SPECS, FX5_BOARDS, FX5_COMM, fx_spec, model_power
)
from renderers.relay_references import (
    coil_texts, contact_key, line_no, load_key, ref_header, register_coil,
    register_contact, row_ys
)
from renderers.plc_symbols import (
    fx5_body_symbol
)
from renderers.typography import (
    wrap2
)


FX_PITCH, FX_Y0, FX_GAP, FX_YMAX = 32, 86, 10, 745

def fx_signal_symbol(p, pg, io):
    key = 'fx_' + io
    if fx_spec(pg).get('physical_io', {}).get(io + 'put_signal_contacts', 1) == 2:
        dual = key + '_dual'
        if dual not in p.sym:
            s = copy.deepcopy(p.sym[key])
            s.name = dual
            s.terminals = {k: (u(), orient, x, y) for k, (_, orient, x, y) in s.terminals.items()}
            circle_x = 4 if io == 'in' else -10
            s.circle(circle_x, -3, 6)
            s.circle(circle_x, 7, 6)
            if io == 'in':
                s.dyn = [(name, x + 6 if name == 'label' else x, *rest) for name, x, *rest in s.dyn]
            s.terminal('t2', 'w' if io == 'in' else 'e', 4 if io == 'in' else -4, 10)
            p.sym[dual] = s
        return dual
    return key

def fx_input_commons(pg, rows):
    spec = fx_spec(pg)
    physical = spec.get('physical_io', {}).get('input_commons')
    if not physical:
        return []
    base = int(str(pg.get('x_start', '0')), 8) if pg['kind'] == 'fx5ext' else 0
    addresses = {int(r['アドレス'].strip()[1:], 8) - base for r in rows}
    return [c for c in physical if any(int(c['start'], 8) <= a < int(c['start'], 8) + c['points'] for a in addresses)]

def fx_input_half(p, off, rows, pg, cfg, show_ss, mode):
    """入力の半分: 外側レーン ─ (接点 ─ [S/S│X│用途])。sink: 接点→N、S/S→P"""
    X = {k: v + off for k, v in FX_IN_X.items()}
    sw_lane, ss_lane = ("N", "P") if mode == "sink" else ("P", "N")
    lane_x = {sw_lane: X["inner"], ss_lane: X["outer"]}
    pw = cfg["power"]
    for name, x in lane_x.items():
        p.power_lane_label(x, LANE[name])
    io_table_header(p,pg,X['plc']+4,260,(55,),('アドレス','用途'))

    prev = p.place("junction", X["inner"], LANE_TOP_Y)
    ss_top = p.place("junction", X["outer"], LANE_TOP_Y)
    y = FX_Y0
    for r in rows:
        addr = r["アドレス"].strip().upper()
        dev = r["機器番号"].strip()
        kind = contact_key(dev, r.get("接点", "").strip().lower())
        j = p.place("junction", X["inner"], y)
        p.wire(prev, "s", j, "n")
        prev = j
        ct = p.place(kind, X["contact"], y, label=dev, texts=[("label", -24, -25, 8, True)])
        n = line_no(p, X["num"], y)
        register_contact(p, dev, "b" if r.get("接点", "").strip().lower() == "b" else "a", n, X["contact"], y)
        cv = wrap2(comment_value(r), 190, 8)
        key = fx_signal_symbol(p, pg, "in")
        label_texts = [(name, x + 6 if key.endswith('_dual') else x, *rest) for name, x, *rest in FX_IN_TEXTS]
        plc = p.place(key, X["plc"], y, label=addr, comment=cv,
                      texts=label_texts + [comment_text(cv, 64, 196, 8, FX_PITCH)])
        p.wire(j, "e", ct, "w")
        p.wire(ct, "e", plc, "t", num=r.get("線番", "").strip() or addr, show=True)
        y += FX_PITCH
    physical = fx_input_commons(pg, rows)
    if physical or show_ss:
        y += FX_GAP
        commons = physical or [{'name': fx_spec(pg).get('in_common', 'S/S'), 'contacts': 1}]
        previous = ss_top
        for common in commons:
            for contact in range(common['contacts']):
                line_no(p, X['num'], y)
                sj = p.place('junction', X['outer'], y)
                p.wire(previous, 's', sj, 'n')
                previous = sj
                cm = 'コモン'
                plc = p.place('fx_in', X['plc'], y, label=common['name'], comment=cm,
                              texts=FX_IN_TEXTS + [('comment', 64, vcenter(8), 8, False)])
                p.wire(sj, 'e', plc, 't', num=LANE[ss_lane], show=False)
                y += FX_PITCH
    p.extend_lanes([X["inner"], X["outer"]])

def fx_output_half(p, off, groups, pg, cfg, kind, relay_com_to):
    """出力の半分: ([用途│Y│COMn] ─ 負荷) ─ レーン。グループごとに COM 行。グループの間は少し空ける"""
    X = {k: v + off for k, v in FX_OUT_X.items()}
    if kind == "sink":
        load_lane, com_lane, com_fmt = "P", "N", "COM{}"
    elif kind == "source":
        load_lane, com_lane, com_fmt = "N", "P", "+V{}"
    else:
        com_lane = relay_com_to
        load_lane = "N" if com_lane == "P" else "P"
        com_fmt = "COM{}"
    pw = cfg["power"]
    output_lane_labels(p,X['inner'],LANE[load_lane],X['outer'],LANE[com_lane])
    io_table_header(p,pg,X['plc']-264,260,(205,),('用途','アドレス'))

    prev_l = p.place("junction", X["inner"], LANE_TOP_Y)
    prev_c = p.place("junction", X["outer"], LANE_TOP_Y)
    y, last = FX_Y0, None
    ref_header(p, X["ref"], 46)
    for gi, (no, rows) in enumerate(groups):
        com = com_fmt.format(no)
        ys, y_com, last = row_ys(rows, y, FX_PITCH, last)
        y_top = ys[0] - FX_PITCH // 2 - 3
        for r, y in zip(rows, ys):
            addr = r["アドレス"].strip().upper()
            dev = r["機器番号"].strip()
            lk = load_key(dev, r.get("負荷", ""))
            cv = wrap2(comment_value(r), 190, 8)
            plc = p.place(fx_signal_symbol(p, pg, "out"), X["plc"], y, label=addr, comment=cv,
                          texts=FX_OUT_TEXTS + [comment_text(cv, -258, 196, 8, FX_PITCH)])
            ld = p.place(lk, X["load"], y, label=dev, infos={"auxiliary1": dev},
                         texts=coil_texts(lk, -25, X["ref"] - X["load"]))
            register_coil(p, dev, line_no(p, X["num"], y), X["ref"], y, X["load"])
            j = p.place("junction", X["inner"], y)
            p.wire(prev_l, "s", j, "n")
            prev_l = j
            p.wire(plc, "t", ld, "w", num=r.get("線番", "").strip() or addr, show=True)
            p.wire(ld, "e", j, "w")
        y = y_com
        # 同名でも物理的な接続口はそれぞれ描く。
        physical = next((c for c in fx_spec(pg).get('physical_io', {}).get('output_commons', []) if c['group'] == no), {})
        count = physical.get('contacts', 1)
        for contact in range(count):
            line_no(p, X['num'], y)
            cj = p.place('junction', X['outer'], y)
            p.wire(prev_c, 's', cj, 'n')
            prev_c = cj
            cm = 'コモン'
            plc = p.place('fx_out', X['plc'], y, label=physical.get('name', com), comment=cm,
                          texts=FX_OUT_TEXTS + [('comment', -258, vcenter(8), 8, False)])
            p.wire(plc, 't', cj, 'w', num=LANE[com_lane], show=False)
            y += FX_PITCH
        y += FX_GAP
    p.extend_lanes([X["inner"], X["outer"]])

def fx_pack(groups, rows_by_addr, physical=None):
    """出力グループを半分ずつに詰める(グループは分割しない)"""
    halves, cur = [], []
    y, last = FX_Y0, None
    for no, addrs in groups:
        rows = [rows_by_addr[a] for a in addrs]
        _, com_y, last2 = row_ys(rows, y, FX_PITCH, last)     # このグループの COM 行の Y
        extra = (next((c['contacts'] for c in (physical or {}).get('output_commons', []) if c['group'] == no), 1) - 1) * FX_PITCH
        if cur and com_y + extra > FX_YMAX:
            halves.append(cur)
            cur = []
            _, com_y, last2 = row_ys(rows, FX_Y0, FX_PITCH, None)
        cur.append((no, rows))
        last, y = last2, com_y + extra + FX_PITCH + FX_GAP
    if cur:
        halves.append(cur)
    return halves

def fx_split_inputs(rows):
    """入力を半ページずつに分ける(半分に入るのは20点まで)"""
    if len(rows) <= 20:
        return [rows] if rows else []
    return [rows[i:i + 16] for i in range(0, len(rows), 16)]

def build_fx5u_pages(pg, cfg, symbols, in_rows, out_rows):
    sp = fx_spec(pg)
    kind = sp["kind"]
    mode = pg.get("input_mode", "sink")
    relay_to = pg.get("relay_com_to", "P")
    by_addr = {r["アドレス"].strip().upper(): r for r in out_rows}
    out_halves = fx_pack(sp["groups"], by_addr, sp.get("physical_io")) if sp["groups"] else []
    in_halves = fx_split_inputs(in_rows) if in_rows else []
    name = pg.get("title_prefix", "PLC" if pg["kind"] == "fx5u" else pg["model"] + " ")

    def rng(rows):
        return f"{rows[0]['アドレス'].strip()}〜{rows[-1]['アドレス'].strip()}"

    pages = []
    # 入力・出力がそれぞれ半分に収まれば1ページにまとめる
    if len(in_halves) + len(out_halves) <= 2 and len(in_halves) <= 1 and len(out_halves) <= 1:
        p = Page(symbols)
        parts = []
        if in_halves:
            fx_input_half(p, 0, in_rows, pg, cfg, True, mode)
            parts.append(rng(in_rows))
        if out_halves:
            fx_output_half(p, HALF_W if in_halves else 0, out_halves[0], pg, cfg, kind, relay_to)
            parts.append(rng(out_rows))
        label = "入出力" if in_halves and out_halves else ("入力" if in_halves else "出力")
        pages.append((f"{name}{label} {'・'.join(parts)}", p))
        return pages
    for start in range(0, len(in_halves), 2):
        p = Page(symbols)
        segment = in_halves[start:start + 2]
        for i, hr in enumerate(segment):
            fx_input_half(p, HALF_W * i, hr, pg, cfg, start == 0 and i == 0, mode)
        pages.append((f"{name}入力 {rng(segment[0] + segment[-1])}", p))
    # 出力ページ: グループ単位で左右に詰め、入りきらなければ次ページ
    for i in range(0, len(out_halves), 2):
        p = Page(symbols)
        fx_output_half(p, 0, out_halves[i], pg, cfg, kind, relay_to)
        if i + 1 < len(out_halves):
            fx_output_half(p, HALF_W, out_halves[i + 1], pg, cfg, kind, relay_to)
        segs = out_halves[i:i + 2]
        first, last = segs[0][0][1][0]["アドレス"].strip(), segs[-1][-1][1][-1]["アドレス"].strip()
        pages.append((f"{name}出力 {first}〜{last}", p))
    return pages

def fx_single_half(pg, in_rows, out_rows):
    """入力だけ・出力だけで半分に収まるユニットなら、その描き方を返す(左右に2台並べるため)"""
    if pg["kind"] != "fx5ext" or (in_rows and out_rows):
        return None
    if in_rows:
        return ("in", in_rows) if len(fx_split_inputs(in_rows)) == 1 else None
    if not out_rows:
        return None
    sp = fx_spec(pg)
    halves = fx_pack(sp["groups"], {r["アドレス"].strip().upper(): r for r in out_rows}, sp.get("physical_io")) if sp["groups"] else []
    return ("out", halves[0]) if len(halves) == 1 else None

def fx_draw_single_half(p, off, pg, cfg, single):
    """fx_single_half() の結果を半分(off)に描く。戻り値: 図面名称に使う文字"""
    sp = fx_spec(pg)
    io, data = single
    if io == "in":
        fx_input_half(p, off, data, pg, cfg, True, pg.get("input_mode", "sink"))
        first, last = data[0]["アドレス"].strip(), data[-1]["アドレス"].strip()
        return f"{pg['model']} 入力 {first}〜{last}"
    fx_output_half(p, off, data, pg, cfg, sp["kind"], pg.get("relay_com_to", "P"))
    first, last = data[0][1][0]["アドレス"].strip(), data[-1][1][-1]["アドレス"].strip()
    return f"{pg['model']} 出力 {first}〜{last}"

def build_fx5_body_page(pg, symbols):
    """本体の電源・内蔵アナログ・通信を接続可能なQET端子で描く。"""
    p = Page(symbols)
    spec = FX5U_SPECS[pg["model"].upper()]
    battery = pg.get("battery", "要確認" if spec["battery_supported"] else "搭載不可")
    usb = "あり" if spec["usb_port"] else "なし"
    power = model_power(pg["model"])
    module_board = next((m.upper() for m in pg.get('modules', []) if FX5_COMM[m.upper()]['form'] == 'board'), '')
    board = pg.get('board_model', '') or module_board
    key = "fx5_body_" + pg["model"].upper().replace("/", "_").replace("-", "_") + '_' + board.replace('-', '_')
    if key not in symbols:
        pairs = 2 if pg["model"].upper().startswith(("FX5U-64", "FX5U-80")) else 1
        connector = pg["model"].upper().startswith("FX5UC-")
        symbols[key] = fx5_body_symbol(key, power == "AC", spec["analog"], spec["rs485"], spec["service"], pairs,
                                       connector, not connector, FX5_BOARDS.get(board))
    sym = symbols[key]
    BX = 300                                  # 本体の左上。端子は左へ出るので、レーンとの間を配線用に空ける
    if spec["battery_supported"]:
        battery_first = ("■" if battery == "装着" else "□") + " 有 (FX3U-32BL)"
        battery_second = ("■" if battery == "非装着" else "□") + " 無"
    else:
        battery_first = "■ 装着不可"
        battery_second = ""
    usb_choice = "■ " + ("有 (Mini-B)" if spec["usb_port"] else "無")
    sd_card = pg.get("sd_card", "要確認")
    sd_model = pg.get("sd_card_model", "").strip()
    sd_first = ("■" if sd_card == "有" else "□") + " 有 (" + (sd_model or "　　　") + ")"
    sd_second = ("■" if sd_card == "無" else "□") + " 無"
    sd_available = not pg['model'].upper().startswith('FX5S-') or board == 'FX5-SDCD'
    sd_in_board = board == 'FX5-SDCD'
    board_label = board if board and board != 'なし' else '型式：'
    module_tags = pg.get('module_tags', [])
    board_tag = pg.get('board_tag', '') or next((module_tags[i] for i,m in enumerate(pg.get('modules', []))
                                                if m.upper()==board and i<len(module_tags)), '')
    unit_identity_header(p,pg,BX-20,350)
    cpu = p.place(key, BX, 52, label=pg.get('tag',''), comment="バッテリ: " + battery,
            infos={"auxiliary1": usb_choice, "auxiliary2": battery_first, "auxiliary3": battery_second,
                   "auxiliary4": "バッテリ", "auxiliary5": "USBポート",
                   "auxiliary6": "SD CARD" if sd_available else "", "auxiliary7": sd_first if sd_available else "", "auxiliary8": sd_second if sd_available else "",
                   "auxiliary10": board_label, "auxiliary11": board_tag, 'manufacturer_reference':pg['model'], 'auxiliary13':'CPU',
                   "description": "USBポート: " + usb},
            texts=[("auxiliary13", 10, 26, 10, True), ("auxiliary4", 75, sym.status_y, 8, False),
                   ("auxiliary2", 135, sym.status_y, 8, False),
                   ("auxiliary3", 135, sym.status_y + 19, 8, False),
                   ("auxiliary5", 75, sym.status_y + 38, 8, False),
                   ("auxiliary1", 135, sym.status_y + 38, 8, False),
                   ("auxiliary6", 183 if sd_in_board else 75, 125 if sd_in_board else sym.status_y + 57, 8, False),
                   ("auxiliary7", 227 if sd_in_board else 135, 125 if sd_in_board else sym.status_y + 57, 7 if sd_in_board else 8, False),
                   ("auxiliary8", 227 if sd_in_board else 135, 144 if sd_in_board else sym.status_y + 76, 7 if sd_in_board else 8, False)] +
                  ([] if board not in FX5_BOARDS else
                   [("auxiliary11", 183, 100, 8, True), ("auxiliary10", 183, 80, 8, False)]))
    # 端子は QET でそのまま配線できるので、行き先の決まらない線は引き出さない
    # 右側にユニット構成の表(本体の入出力・増設・アナログ・通信と、そのページ番号)を置く
    adapters = [(m, module_tags[i] if i<len(module_tags) else '') for i,m in enumerate(pg.get('modules', []))
                if FX5_COMM[m.upper()]['form'] != 'board']

    def post(pages_rows, page_of):
        rows = [(pg["model"], "本体", "")]
        rows += [((tag+'  ' if tag else '')+m, "通信 " + FX5_COMM[m.upper()].get('network', ''), "") for m,tag in adapters]
        for other, _ in pages_rows:
            k = other["kind"]
            if k == "fx5u":
                if other['model'].upper() != pg['model'].upper():
                    continue
                if pg.get('tag', '').strip() and other.get('tag', '').strip() != pg['tag'].strip():
                    continue
                rows.append((other["model"], "本体の入出力", page_of(other)))
            elif k == "fx5ext":
                sp = fx_spec(other)
                n_out = sum(len(g) for _, g in sp["groups"])
                what = "・".join(t for t in ((f"入力{len(sp['inputs'])}点" if sp["inputs"] else ""),
                                             (f"出力{n_out}点" if n_out else "")) if t)
                rows.append((other["model"], "増設 " + what, page_of(other)))
            elif k == "fx5analog":
                rows.append((other["model"], f"アナログ {len(FX5_ANALOG_SPECS[other['model'].upper()]['channels'])}ch", page_of(other)))
            elif k == "fxcomm":
                for side in ("left_model", "right_model"):
                    if other.get(side):
                        rows.append((other[side], "通信 " + FX5_COMM[other[side].upper()].get('network', ''), page_of(other)))
        if len(rows) <= 1:
            return
        cols = [("形名", 130), ("内容", 170), ("頁", 40)]
        # 図枠の右下に置く(拡張ボードの端子は右へ配線するので、本体の右は空けておく)
        TX = 20 + BORDER_COLS * COL_SIZE - 10 - sum(w for _, w in cols)
        TY = 790 - (len(rows) + 1) * TABLE_ROW
        p.text(TX, TY - 24, "ユニット構成", 9, True)
        table(p, TX, TY, cols,
              [[m, w, str(n) if n else ""] for m, w, n in rows])
    from renderers import settings
    from renderers.box_layout import finish_box
    frame_bottom = 52 + max(float(a['y']) + float(a['height']) for tag, a in sym.parts if tag == 'rect')
    # 外枠は本体記号に含まれるため、設定欄の基準だけ共通処理へ渡す。
    finish_box(p, BX - 20, BX + 330, frame_bottom,
               settings.fields(model=pg['model'], values=pg), pg, settings_x=650, settings_width=230,
               draw_frame=False, limit=frame_bottom)

    p.post = post
    return p
