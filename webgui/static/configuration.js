'use strict';
// ------------------------------------------------------------ 描画
const TITLES = { home: 'PLC・GOT 図面生成', drawing: '三菱電機 PLC・GOT 図面', keyence: 'キーエンス KV・VT', omron: 'オムロン NX・NA', terminals: '三菱電機 I/O図・中継端子台図', parts: '制御部品の書出し・ユーザーコレクション登録' };

function setMode(mode) {
  S.mode = mode;
  $('#view-home').hidden = mode !== 'home';
  $('#view-drawing').hidden = mode !== 'drawing';
  $('#view-keyence').hidden = mode !== 'keyence';
  $('#view-omron').hidden = mode !== 'omron';
  $('#view-parts').hidden = mode !== 'parts';
  $('#view-terminals').hidden = mode !== 'terminals';
  $('#tools-drawing').hidden = mode !== 'drawing';
  $('#tools-parts').hidden = mode !== 'parts';
  document.querySelector('.home-btn').hidden = mode === 'home';
  $('#app-title').textContent = mode === 'drawing' ? drawingTitle() : TITLES[mode];
  if (mode === 'drawing') render();
  else if (mode === 'parts') renderParts();
  else if (mode === 'home') renderHome();
  else {
    if (mode === 'terminals') showTerminalForm('mitsubishi', $('#view-terminals .maker-menu'));
    else renderConfigurationMenu();
    document.title = TITLES[mode];
    setStatus('');
  }
}

function renderHome() {
  $('#file').textContent = '';
  $('#dirty').textContent = '';
  document.title = 'PLC・GOT 図面生成';
  const working = S.snap && (S.snap.pages.length || S.snap.path);
  $('#home-continue').hidden = !working || projectMaker() !== 'mitsubishi';
  if (working) $('#home-continue').textContent = `作業中に戻る（${S.snap.name}${S.snap.dirty ? '・未保存' : ''}）`;
}

function renderConfigurationMenu() {
  const prefix = S.mode === 'keyence' ? 'kv' : 'nx';
  const task = $('input[name="' + prefix + '-task"]:checked').value;
  const config = task === 'configuration';
  const terminal = task === 'terminal';
  const select = $('#' + prefix + '-series');
  select.hidden = terminal;
  $('label[for="' + prefix + '-series"]').hidden = terminal;
  if (select.dataset.task !== task) {
    const series = prefix === 'kv'
      ? (task === 'panel' ? ['VT3', 'VT5'] : KV_CONFIGURATION_SERIES)
      : (task === 'panel' ? ['NA5'] : ['NX']);
    const choices = series.map((s) => new Option(s, s));
    if (!config && series.length > 1) choices.unshift(new Option('すべてのシリーズ', ''));
    select.replaceChildren(...choices);
    select.dataset.task = task;
    $('#' + prefix + '-search').value = '';
    for (const input of $('#' + prefix + '-single').querySelectorAll('input[type="text"]')) input.value = '';
  }
  $('#' + prefix + '-configuration').hidden = !config;
  $('#' + prefix + '-single').hidden = config || terminal;
  $('#terminal-form').hidden = !terminal;
  if (terminal) showTerminalForm(S.mode, $('#view-' + S.mode + ' .maker-menu'));
  else if (!config) showMakerModels(prefix);
  const working = S.snap && (S.snap.pages.length || S.snap.path);
  const button = $('#' + prefix + '-config-continue');
  button.hidden = !working || projectMaker() !== S.mode;
  if (!button.hidden) button.textContent = `作業中の構成に戻る（${S.snap.name}${S.snap.dirty ? '・未保存' : ''}）`;
}

function showTerminalForm(maker, container) {
  const form = $('#terminal-form');
  container.append(form);
  form.hidden = false;
  const models = Object.keys(S.meta.terminal_blocks[maker]).sort();
  $('#terminal-plc').replaceChildren(...models.map((model) => new Option(model, model)));
  showTerminalBlocks();
}

function compatibleTerminalChoices() {
  const maker = S.mode === 'terminals' ? 'mitsubishi' : S.mode;
  return S.meta.terminal_blocks[maker][$('#terminal-plc').value];
}

function showTerminalBlocks() {
  const models = new Map(compatibleTerminalChoices().map((item) => [item.model, item.maker]));
  $('#terminal-model').replaceChildren(...Array.from(models, ([model, maker]) => new Option(maker + '　' + model, model)));
  showTerminalCables();
}

function showTerminalCables() {
  const choices = compatibleTerminalChoices().filter((row) => row.model === $('#terminal-model').value);
  for (const id of ['terminal-cable', 'terminal-cable2']) {
    $('#' + id).replaceChildren(...choices.map((row) => {
      const label = row.cable_maker + '　' + row.cable + (row.kit ? '（セット ' + row.kit + '）' : '');
      return new Option(label, row.cable);
    }));
  }
  showTerminalPorts();
}

function showTerminalPorts() {
  const choice = compatibleTerminalChoices().find(row =>
    row.model === $('#terminal-model').value && row.cable === $('#terminal-cable').value);
  const ports = choice.ports;
  const ends = ports || choice.branches;
  function field(id, label, visible = true) {
    const title = $('label[for="' + id + '"]');
    if (label) title.textContent = label;
    title.hidden = $('#' + id).hidden = !visible;
  }
  field('terminal-start', null, S.mode === 'terminals');
  field('terminal-block-tag', ends ? ends[0] + ' 端子台タグ' : '端子台タグ');
  field('terminal-block-tag2', ends && ends[1] + ' 端子台タグ', !!ends);
  field('terminal-cable', ports ? ports[0] + ' 接続ケーブル' : '接続ケーブル');
  field('terminal-cable-tag', ports ? ports[0] + ' ケーブル番号' : 'ケーブル番号');
  field('terminal-cable2', null, !!ports);
  field('terminal-cable-tag2', null, !!ports);
}

function render() {
  if (S.mode !== 'drawing') return;
  const active = document.activeElement;
  const focusId = active && active.id;
  const selection = active && active.selectionStart;
  const scroll = ['main', 'drawer', 'pages'].map((id) => [id, $('#' + id).scrollTop, $('#' + id).scrollLeft]);
  renderHeader();
  renderPages();
  renderMain();
  renderDrawer();
  for (const [id, top, left] of scroll) { $('#' + id).scrollTop = top; $('#' + id).scrollLeft = left; }
  const restored = focusId && document.getElementById(focusId);
  if (restored) {
    restored.focus({ preventScroll: true });
    if (typeof selection === 'number' && restored.setSelectionRange && restored.type !== 'number') restored.setSelectionRange(selection, selection);
  }
}

function renderHeader() {
  const vendor = S.snap.pages.some((page) => VENDOR_BODY_KINDS.includes(page.kind));
  $('[data-action="generate"]').hidden = vendor;
  $('[data-action="generate-bundle"]').hidden = !vendor;
  $('[data-action="generate-overview"]').hidden = !vendor;
  $('#app-title').textContent = drawingTitle();
  $('#undo').disabled = !S.snap.can_undo;
  $('#redo').disabled = !S.snap.can_redo;
  $('#file').textContent = S.snap.name;
  $('#file').title = S.snap.path || '';
  $('#dirty').textContent = S.snap.dirty ? '● 未保存の変更あり' : '';
  document.title = (S.snap.dirty ? '* ' : '') + S.snap.name + ' - PLC・GOT 図面生成';
}

function renderPages() {
  const pages = S.snap.pages;
  $('#page-count').textContent = pages.length + ' ページ';
  let html = `<button type="button" class="page-item project${S.index === null ? ' active' : ''}" data-action="select-project">
    <span class="no">—</span><span><div class="k">プロジェクト設定</div><div class="t">${esc(S.snap.project.project_title || '図面情報・電源・表紙')}</div></span></button>`;
  const row = (p, child = false) => `<button type="button" class="page-item${child ? ' child' : ''}${S.index === p.index ? ' active' : ''}" data-action="select-page" data-index="${p.index}" draggable="true" title="ドラッグで並べ替え">
      <span class="no">${p.index + 1}</span>
      <span style="min-width:0">
        <div class="k">${esc(p.kind_name)}</div>
        <div class="m">${esc([p.tag, p.model].filter(Boolean).join('  ')) || '&nbsp;'}</div>
        ${p.title ? `<div class="t">${esc(p.title)}</div>` : ''}
      </span>
      ${p.wiring ? '<span class="badge">配線</span>' : ''}
    </button>`;
  for (const p of pages.filter((p) => p.parent === null || p.parent === undefined)) {
    const children = pages.filter((c) => c.parent === p.index);
    if (children.length) {
      html += `<div class="page-group"><button type="button" class="tree-toggle" data-action="toggle-group" data-index="${p.index}" aria-expanded="${!S.collapsed.has(p.index)}">${S.collapsed.has(p.index) ? '▶' : '▼'} 詳細 ${children.length}ページ</button>${row(p)}`;
      if (!S.collapsed.has(p.index)) html += children.map((c) => row(c, true)).join('');
      html += '</div>';
    } else html += row(p);
  }
  $('#pages').innerHTML = html;
}

function renderMain() {
  const main = $('#main');
  if (S.index === null || !S.page) {
    main.innerHTML = projectView();
    return;
  }
  const page = S.page;
  const info = S.snap.pages[S.index] || {};
  let html = `<div class="card"><div class="page-title">
      <div><h2>${S.index + 1}. ${esc(info.kind_name || '種類を選択')}</h2>
      <div class="lead" style="margin:0">${esc([info.tag, info.model, info.title].filter(Boolean).join('　')) || 'メーカー・シリーズ・種類を選んでください'}</div></div>
      <div class="actions">
        ${page.rack ? '<button type="button" class="btn solid" data-action="all-pages" title="構成のユニットのうち、まだページが無いものを作ります">詳細ページを一括作成</button>' : ''}
        ${!isVendorRack(page.rack) ? `<button type="button" class="btn" data-action="wiring">配線情報${page.wiring_count ? `（${page.wiring_count}）` : ''}</button>` : ''}
        ${page.can_csv ? '<button type="button" class="btn" data-action="page-csv">CSVを作成</button>' : page.can_sample ? '<button type="button" class="btn" data-action="sample">CSV雛形</button>' : ''}
        ${CSV_KEYS.some((key) => page.values[key]) ? '<button type="button" class="btn" data-action="csv-recheck">CSV再チェック</button>' : ''}
        <button type="button" class="btn icon-btn" data-action="move-up" aria-label="上へ" title="上へ">↑</button>
        <button type="button" class="btn icon-btn" data-action="move-down" aria-label="下へ" title="下へ">↓</button>
        <button type="button" class="btn" data-action="duplicate">複製</button>
        <button type="button" class="btn danger" data-action="delete-page">削除</button>
      </div></div></div>`;
  if (page.rack) html += rackView(page.rack);
  html += formView(page);
  main.innerHTML = html;
}

function projectView() {
  const p = S.snap.project;
  const fields = S.meta.project_fields.map(([key, label]) =>
    `<label for="pf-${key}">${esc(label)}</label><input type="text" id="pf-${key}" data-project="${key}" value="${esc(p[key])}">`).join('');
  return `<div class="card">
    <h2>プロジェクト設定</h2>
    <p class="lead">図枠・表紙に入る情報です。ページは左の一覧から選ぶか、「ページ追加」で作ります。</p>
    <div class="form">
      <div class="sub-head">図面情報</div>${fields}
      <div class="sub-head">電源・表紙</div>
      <label for="pf-P">P側電源</label><input type="text" id="pf-P" data-power="P" value="${esc(p.power.P)}">
      <label for="pf-N">N側電源</label><input type="text" id="pf-N" data-power="N" value="${esc(p.power.N)}">
      <span></span><label style="display:flex;gap:8px;align-items:center;color:var(--ink)"><input type="checkbox" data-project-check="front_pages" ${p.front_pages ? 'checked' : ''}>表紙・改訂履歴・目次を作成</label>
    </div></div>`;
}

function rackView(rack) {
  const stats = [];
  if (rack.io_total !== null && rack.io_total !== undefined) {
    stats.push(`<div class="stat"><div class="l">${isVendorRack(rack) ? '入出力点数' : '入出力占有点数（空きを除く）'}</div><div class="v">${rack.io_total}${rack.io_limit ? `<small> / ${rack.io_limit}</small>` : ''}</div></div>`);
  }
  stats.push(`<div class="stat"><div class="l">${rack.slots_total && !isVendorRack(rack) ? 'スロット使用' : 'ユニット数'}</div><div class="v">${rack.slots_used}${rack.slots_total ? `<small> / ${rack.slots_total}</small>` : ''}</div></div>`);
  let html = `<div class="card"><div class="stats">${stats.join('')}</div>`;
  if (rack.message) html += `<div class="notice">${esc(rack.message)}</div>`;
  if (rack.alarms && rack.alarms.length) {
    html += `<div class="alarm" role="alert"><b>${isVendorRack(rack) ? '接続条件の警告' : 'XY割付の警告'}</b><ul>${(rack.alarm_targets || rack.alarms.map((text) => ({ text, targets: [] }))).map((a) =>
      `<li>${esc(a.text)} ${(a.targets || []).map((t) => `<button type="button" class="alarm-link" data-action="goto-alarm" data-id="${esc(t.id)}" data-field="${esc(t.field)}">${esc(t.label)}へ</button>`).join(' ')}</li>`).join('')}</ul></div>`;
  }
  for (const stage of rack.stages) {
    const baseId = 'base:' + (stage.stage ?? 0);
    html += `<div class="stage"><div class="stage-head">
      <span class="name">${esc(stage.name)}</span>
      ${isLinearRack(rack) ? '' : `<button type="button" class="base${S.sel === baseId ? ' sel' : ''}" data-action="select-item" data-id="${baseId}" title="ベースを選択">${esc(stage.base || 'ベース未選択')}</button>`}
      </div><div class="rack-scroll"><div class="rack">`;
    for (const item of stage.items) html += slotView(item, rack);
    html += '</div></div></div>';
    if (!isLinearRack(rack)) html += slotTable(stage);
  }
  if (!isLinearRack(rack)) {
    html += `<div class="legend"><button type="button" class="btn blue" data-action="add-extension">＋ 増設ベース追加</button>
      <span><i style="background:var(--in)"></i>入力</span><span><i style="background:var(--out)"></i>出力</span>
      <span><i style="background:var(--analog)"></i>アナログ</span><span><i style="background:var(--comm)"></i>通信・インテリ</span>
      <span><i style="background:var(--mixed)"></i>入出力混合</span></div>`;
  }
  return html + '</div>';
}

function slotTable(stage) {
  const rows = stage.items.filter((i) => i.type === 'module' || i.type === 'reserved' || i.type === 'net');
  return `<div class="slot-table-wrap"><table class="slot-table"><caption>${esc(stage.name)}・スロット一覧</caption>
    <thead><tr><th>スロット</th><th>形名</th><th>タグ名</th><th>先頭XY</th><th>割付範囲</th></tr></thead>
    <tbody>${rows.map((i) => `<tr><td>${esc(i.head)}</td><td>${i.type === 'module' ?
      `<button type="button" class="btn small" data-action="add-module" data-stage="${i.stage}" data-slot="${i.slot}">${esc(i.model || '＋ 選択')}</button>` : esc(i.model)}</td>
      <td>${i.type === 'module' && i.model ? `<input id="slot-tag-${i.stage}-${i.slot}" type="text" data-module-tag data-stage="${i.stage}" data-slot="${i.slot}" value="${esc(i.tag || '')}" aria-label="スロット${esc(i.head)} タグ名">` : '—'}</td>
      <td>${i.type === 'module' ? `<input id="slot-start-${i.stage}-${i.slot}" type="text" class="mono" data-module-start data-stage="${i.stage}" data-slot="${i.slot}" value="${esc(i.given || '')}" placeholder="自動: ${esc(i.auto || '')}" aria-label="スロット${esc(i.head)} 先頭XY">` : '—'}</td>
      <td class="mono">${esc(i.addr || '')}</td></tr>`).join('')}</tbody></table></div>`;
}

function slotView(item, rack) {
  const classes = ['unit', 't-' + item.type];
  if (item.group) classes.push('g-' + item.group);
  if (S.sel === item.id) classes.push('sel');
  let label = item.model;
  if (item.type === 'module' && !item.model) label = '空き';
  if (item.type === 'add') label = '＋ 追加';
  const aria = `${item.head} ${label}`;
  return `<div class="slot${item.alarm ? ' alarmed' : ''}"><div class="h">${esc(item.head)}</div>${!isVendorRack(rack) ? `<div class="a${item.manual ? ' manual' : ''}" title="${item.manual ? '先頭XYを指定' : '自動割付'}">${esc(item.addr || '')}</div>` : ''}
    <button type="button" class="${classes.join(' ')}" data-action="select-item" data-id="${esc(item.id)}" aria-label="${esc(aria)}">
      <span class="vm">${esc(label)}</span>
      ${item.summary ? `<span class="sm">${esc(item.summary)}</span>` : ''}
      ${item.tag ? `<span class="tg">${esc(item.tag)}</span>` : ''}
    </button></div>`;
}

function fieldControl(key, value, options, id, attrs = '') {
  const opts = options[key];
  if (key === 'maker' || key === 'series' || key === 'kind') {
    const list = opts || [];
    const known = list.some(([code]) => code === value);
    return `<select id="${id}" data-field="${key}" ${attrs}>
      <option value="">${list.length ? '選択してください' : '—'}</option>
      ${!known && value ? `<option value="${esc(value)}" selected>${esc(value)}</option>` : ''}
      ${list.map(([code, label]) => `<option value="${esc(code)}"${code === value ? ' selected' : ''}>${esc(label)}</option>`).join('')}
    </select>`;
  }
  if (MODEL_KEYS.includes(key)) {
    return `<div class="row"><input type="text" id="${id}" value="${esc(value)}" readonly placeholder="未選択">
      <button type="button" class="btn blue small" data-action="pick-field" data-key="${key}">選択</button>
      ${value ? `<button type="button" class="btn small" data-action="clear-field" data-key="${key}" aria-label="クリア">×</button>` : ''}</div>`;
  }
  if (CSV_KEYS.includes(key)) {
    return `<div class="row"><input type="text" id="${id}" data-field="${key}" value="${esc(value)}" ${attrs}>
      <button type="button" class="btn small" data-action="pick-csv" data-key="${key}">参照</button>
      ${value ? `<button type="button" class="btn small" data-action="open-csv" data-key="${key}">開く</button>` : ''}</div>`;
  }
  if (Array.isArray(opts) && FREE_SELECT.includes(key)) {
    return `<input type="text" id="${id}" data-field="${key}" value="${esc(value)}" list="${id}-list" ${attrs}>
      <datalist id="${id}-list">${opts.filter(Boolean).map((o) => `<option value="${esc(o)}">`).join('')}</datalist>`;
  }
  if (Array.isArray(opts)) {
    const list = opts.includes('') ? opts : [''].concat(opts);
    const known = list.includes(value);
    return `<select id="${id}" data-field="${key}" ${attrs}>
      ${!known ? `<option value="${esc(value)}" selected>${esc(value)}</option>` : ''}
      ${list.map((o) => `<option value="${esc(o)}"${o === value ? ' selected' : ''}>${esc(o || '—')}</option>`).join('')}</select>`;
  }
  return `<input type="text" id="${id}" data-field="${key}" value="${esc(value)}" ${attrs}>`;
}

function formView(page) {
  const owned = page.rack && (!isLinearRack(page.rack) || isVendorRack(page.rack)) ? [...CPU_KEYS, ...POWER_KEYS, ...BASE_KEYS] : page.rack ? CPU_KEYS : [];
  const settings = page.settings || [];
  const keys = ['maker', 'series', ...page.visible.filter((k) => !owned.includes(k) && !settings.some((s) => s.key === k))];
  const rows = keys.map((key) => `<label for="f-${key}">${esc(fieldLabel(key))}</label>${fieldControl(key, page.values[key] || '', page.options, 'f-' + key)}`).join('');
  const settingRows = settings.map((s) => `<div class="setting-row"><label class="setting-check"><input type="checkbox" data-setting-visible="${esc(s.key)}"${s.visible ? ' checked' : ''}>${esc(s.label)}</label>
    ${s.visible ? fieldControl(s.key, page.values[s.key] || '', page.options, 'f-' + s.key, `aria-label="${esc(s.label)}"`) : '<span class="muted">非表示（入力値を保持）</span>'}</div>`).join('');
  const note = owned.length ? `<p class="lead">${isVendorRack(page.rack) ? 'CPU・電源・ユニットは' : isLinearRack(page.rack) ? '本体の形名・ボード・SDは' : 'CPU・電源・ベースは'}上の図をクリックして右側で設定します。</p>` : '';
  return `<div class="card"><h2>ページ設定</h2>${note}
    ${page.summary ? `<div class="summary-box">${esc(page.summary)}</div>` : ''}
    <div class="form">${rows}</div>
    ${settingRows ? `<fieldset class="cpu-group"><legend>通信・機器設定（チェックで表示）</legend>${settingRows}</fieldset>` : ''}
    <details class="extra"${page.extra ? ' open' : ''}><summary>その他の設定（JSON・上級者向け）</summary>
      <textarea id="extra" data-extra spellcheck="false" placeholder='{ "empty_slot_points": 16 }'>${esc(page.extra)}</textarea>
    </details></div>`;
}

// ------------------------------------------------------------ 右メニュー
function findItem(id) {
  if (!S.page || !S.page.rack) return null;
  for (const stage of S.page.rack.stages) {
    for (const item of stage.items) if (item.id === id) return { item, stage };
  }
  return null;
}

function drawerFields(keys) {
  const page = S.page;
  return keys.filter((k) => page.visible.includes(k)).map((key) =>
    `<label class="field">${esc(fieldLabel(key))}${fieldControl(key, page.values[key] || '', page.options, 'd-' + key)}</label>`).join('');
}

function cpuFields() {
  const groups = [
    ['管理番号', ['tag']],
    ['バッテリ', ['battery', 'battery_model', 'batteryless']],
    ['SD・カセット', ['sd_card', 'sd_card_model', 'memory_cassette', 'memory_cassette_model', 'memory_card', 'memory_card_model']],
    ['拡張ボード', ['board_model', 'board_tag']],
  ];
  return groups.map(([title, keys]) => {
    const fields = drawerFields(keys);
    return fields ? `<fieldset class="cpu-group"><legend>${esc(title)}</legend>${fields}</fieldset>` : '';
  }).join('');
}

function renderDrawer() {
  const el = $('#drawer');
  if (S.index === null || !S.page) {
    el.innerHTML = `<div class="where">はじめに</div><div class="model" style="font-size:16px;font-family:inherit">使い方</div>
      <div class="hint">1. 左の「ページ追加」でページを作ります。<br>2. シリーズ・種類を選びます。<br>3. ${projectMaker() === 'mitsubishi' ? '本体ページの構成図でスロットを選び、ユニットを追加します。' : '構成図でCPUと接続位置を選び、ユニットを追加します。'}<br>4. 「詳細ページを一括作成」で各ユニットの図面を作り、「図面生成」で .qet を出力します。</div>`;
    return;
  }
  const page = S.page;
  if (!page.rack) {
    el.innerHTML = `<div class="where">${S.index + 1} ページ目</div><div class="model">${esc(page.values.model || page.values.right_model || page.values.left_model || '—')}</div>
      <div class="desc">${esc((S.snap.pages[S.index] || {}).kind_name || '')}</div>
      <div class="divider"></div>
      <button type="button" class="dbtn" data-action="wiring">配線情報・端子台${page.wiring_count ? `（${page.wiring_count}件）` : ''}</button>
      ${page.can_sample ? '<button type="button" class="dbtn" data-action="sample">CSV雛形を作成</button>' : ''}
      <button type="button" class="dbtn" data-action="check">構成チェック</button>
      <div class="hint">設定はすぐに反映されます。保存は上の「保存」で行います。</div>`;
    return;
  }
  const found = S.sel ? findItem(S.sel) : null;
  if (S.sel && S.sel.startsWith('base:')) {
    const stage = S.page.rack.stages[Number(S.sel.slice(5))];
    el.innerHTML = baseDrawer(stage);
    return;
  }
  if (!found) {
    el.innerHTML = `<div class="where">ユニット構成</div><div class="model" style="font-size:16px;font-family:inherit">${isVendorRack() ? 'CPU・ユニットを選んでください' : 'スロットを選んでください'}</div>
      <div class="hint">${isVendorRack() ? '構成図のCPU・電源・ユニットをクリックして設定します。各接続位置の「追加」からユニットを選べます。' : '図の電源・CPU・スロットをクリックすると、ここに設定と操作が出ます。空きスロットを選ぶとユニットを追加できます。'}</div>`;
    return;
  }
  const { item, stage } = found;
  if (item.type === 'cpu') {
    el.innerHTML = `<div class="where">${isLinearRack(page.rack) && !isVendorRack(page.rack) ? '本体' : 'CPU'}</div><div class="model">${esc(item.model)}</div>
      ${page.summary ? `<div class="desc">${esc(page.summary)}</div>` : ''}
      <button type="button" class="dbtn" data-action="pick-field" data-key="model">${page.values.model ? '変更' : '選択'}</button>
      <div class="divider"></div>${cpuFields()}
      ${page.rack.kind === 'mxbody' || isVendorRack() ? `<button type="button" class="dbtn" data-action="create-cpu-io">${isVendorRack() ? '本体の詳細ページを開く・作成' : '内蔵IOページを開く・作成'}</button>` : ''}`;
  } else if (item.type === 'adapter') {
    el.innerHTML = `<div class="where">必要な接続変換器</div><div class="model">${esc(item.model)}</div>
      <div class="desc">${esc(item.summary || '')}</div>
      <div class="hint">選んだCPU・ユニットの接続に必要なため、構成に合わせて表示します。</div>`;
  } else if (item.type === 'power') {
    if (stage.stage === 0) {
      el.innerHTML = `<div class="where">${isVendorRack() ? '電源' : '電源（基本ベース）'}</div><div class="model">${esc(item.model)}</div><div class="desc">${esc(item.summary)}</div>
        <button type="button" class="dbtn" data-action="pick-field" data-key="power_model">${page.values.power_model ? '変更' : '選択'}</button>
        <div class="divider"></div>${drawerFields(['power_tag'])}`;
    } else {
      el.innerHTML = `<div class="where">電源（${esc(stage.name)}）</div><div class="model">${esc(item.model)}</div><div class="desc">${esc(item.summary)}</div>
        <button type="button" class="dbtn" data-action="stage-pick" data-stage="${stage.stage}" data-key="power_model">変更</button>
        <div class="divider"></div><label class="field">タグ名<input type="text" data-stage-tag="power_model" data-stage="${stage.stage}" value="${esc(item.tag)}"></label>`;
    }
  } else if (item.type === 'net') {
    el.innerHTML = `<div class="where">スロット${esc(item.head)}・CPUと一体</div><div class="model">${esc(item.model)}</div>
      <div class="desc">${esc(item.summary)}</div><div class="kv"><span>アドレス</span><span class="mono">${esc(item.addr)}</span></div>
      <div class="hint">ENCPU のネットワーク部は CPU と一体で、このスロットを使います。</div>`;
  } else if (item.type === 'reserved') {
    el.innerHTML = `<div class="where">スロット${esc(item.head)}</div><div class="model">占有</div>
      <div class="hint">左隣の2スロットユニットが使っています。</div>`;
  } else if (item.type === 'add' || !item.model) {
    el.innerHTML = `<div class="where">${isVendorRack() ? esc(stage.name) : item.type === 'add' ? '増設ユニット' : 'スロット' + esc(item.head)}</div><div class="model">空き</div>
      <div class="desc">${item.addr ? '空きスロットも ' + esc(item.points) + '点を使います' : ''}</div>
      <div class="divider"></div>
      <button type="button" class="dbtn" data-action="add-module" data-stage="${item.stage}" data-slot="${item.slot}" data-bus="${esc(item.bus || '')}">ユニットを追加</button>`;
  } else {
    el.innerHTML = moduleDrawer(item, stage);
    loadUnitPages(item);
  }
}

function baseDrawer(stage) {
  if (!stage) return '';
  if (stage.stage === 0) {
    return `<div class="where">基本ベース</div><div class="model">${esc(stage.base || '未選択')}</div>
      <button type="button" class="dbtn" data-action="pick-field" data-key="base_model">${stage.base ? '変更' : '選択'}</button>
      <div class="divider"></div>${drawerFields(['base_tag'])}
      <div class="hint">ベースのスロット数を超えるユニットは置けません。</div>`;
  }
  return `<div class="where">${esc(stage.name)}</div><div class="model">${esc(stage.base)}</div>
    <button type="button" class="dbtn" data-action="stage-pick" data-stage="${stage.stage}" data-key="base_model">ベースを変更</button>
    <label class="field">タグ名<input type="text" data-stage-tag="base_model" data-stage="${stage.stage}" value="${esc(stage.base_tag || '')}"></label>
    <div class="divider"></div>
    <button type="button" class="dbtn ghost" data-action="remove-extension" data-stage="${stage.stage}">この増設ベースを外す</button>`;
}

function moduleDrawer(item, stage) {
  return `<div class="where">${isVendorRack() ? esc(stage.name) + '・' + esc(item.head) : isLinearRack() ? '増設 ' + esc(item.head) : 'スロット' + esc(item.head)}${item.group ? '・' + esc(GROUP_LABEL[item.group] || '') : ''}</div>
    <div class="model">${esc(item.model)}</div><div class="desc">${esc(item.summary || '')}</div>
    ${item.addr ? `<div class="kv"><span>アドレス</span><span class="mono">${esc(item.addr)}</span><span>占有点数</span><span>${esc(item.points)}点</span></div>` : ''}
    <label class="field">タグ名（管理番号）<input type="text" data-module-tag data-stage="${item.stage}" data-slot="${item.slot}" value="${esc(item.tag)}" placeholder="例: DI1"></label>
    ${moduleBusField(item)}
    ${item.mode_options?.length ? `<label class="field">通信方式<select data-module-mode data-stage="${item.stage}" data-slot="${item.slot}">${!item.communication_mode ? '<option value="" selected disabled>未指定（詳細図の設定を使用）</option>' : ''}${item.mode_options.map((mode) =>
      `<option${mode === item.communication_mode ? ' selected' : ''}>${esc(mode)}</option>`).join('')}</select></label>` : ''}
    ${!isLinearRack() ? `<label class="field">先頭XY（16進・空欄は自動）<input type="text" class="mono" data-module-start data-stage="${item.stage}" data-slot="${item.slot}" value="${esc(item.given || '')}" placeholder="自動: ${esc(item.auto || '')}"></label>` : ''}
    <div class="divider"></div>
    <div class="where">図面ページ</div><div id="unit-pages" class="hint">読み込み中…</div>
    <div class="divider"></div>
    <button type="button" class="dbtn" data-action="add-module" data-stage="${item.stage}" data-slot="${item.slot}" data-bus="${esc(item.bus || '')}">ユニット変更</button>
    <button type="button" class="dbtn ghost" data-action="remove-module" data-stage="${item.stage}" data-slot="${item.slot}">取り外す</button>`;
}

function moduleBusField(item) {
  const options = item.bus_options || [];
  if (!isVendorRack() || options.length < 2) return '';
  return `<label class="field">接続位置<select data-module-bus data-stage="${item.stage}" data-slot="${item.slot}">${options.map(([value, label]) =>
    `<option value="${esc(value)}"${value === item.bus ? ' selected' : ''}>${esc(label)}</option>`).join('')}</select></label>`;
}

async function loadUnitPages(item) {
  const index = S.index;
  const result = await call('unit_pages', index, item.stage, item.slot);
  const box = $('#unit-pages');
  if (!box || S.index !== index || S.sel !== item.id) return;
  if (!result || result.error) {
    box.textContent = result ? result.error : '';
    return;
  }
  let html = '';
  for (const page of result.existing) {
    html += `<button type="button" class="dbtn link" data-action="goto-page" data-index="${page.index}">→ ${esc(page.label)}</button>`;
  }
  for (const [kind, label] of result.kinds) {
    html += `<button type="button" class="dbtn" data-action="create-unit-page" data-kind="${kind}" data-stage="${item.stage}" data-slot="${item.slot}">＋ ${esc(label)}ページを作成</button>`;
  }
  box.className = '';
  box.style.display = 'flex';
  box.style.flexDirection = 'column';
  box.style.gap = '6px';
  box.innerHTML = html || '<span class="hint">このユニットの図面ページはありません（構成図に載ります）。</span>';
}
