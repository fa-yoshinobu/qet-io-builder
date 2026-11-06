'use strict';
/* PLC・GOT 図面生成 画面。処理はすべて Python(webgui/api.py)が行い、ここは表示と操作だけ。 */

const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ------------------------------------------------------------ Python との接続
const apiReady = new Promise((resolve) => {
  if (window.BROWSER_MODE) {
    resolve((name) => (...args) => fetch('/api/' + name, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args),
    }).then((r) => r.json()));
    return;
  }
  const done = () => resolve((name) => (...args) => window.pywebview.api[name](...args));
  if (window.pywebview && window.pywebview.api) done();
  else window.addEventListener('pywebviewready', done);
});

async function call(name, ...args) {
  const api = await apiReady;
  try {
    return await api(name)(...args);
  } catch (error) {
    return { error: String(error && error.message ? error.message : error) };
  }
}

// エラーは画面に出して null を返す。取消も null。
async function run(name, ...args) {
  const result = await call(name, ...args);
  if (!result) return null;
  if (result.error) {
    await showMessage('エラー', result.error, { error: true });
    if (result.snapshot) applySnapshot(result.snapshot);
    return null;
  }
  if (result.cancelled) return null;
  return result;
}

// ------------------------------------------------------------ 状態
const S = {
  collapsed: new Set(),
  meta: null,
  snap: null,      // プロジェクト全体(ページ一覧など)
  index: null,     // 選択ページ。null はプロジェクト設定
  page: null,      // 選択ページの詳細
  sel: null,       // ベース図で選んだ項目の id
  status: { text: '', warn: false },
  mode: 'home',    // home: 最初のメニュー / drawing: PLC・GOT 図面 / parts: 制御部品の書出し・ユーザーコレクション登録
};
const MODEL_KEYS = ['model', 'left_model', 'right_model', 'power_model', 'base_model'];
const CSV_KEYS = ['csv', 'input_csv', 'output_csv'];
const CPU_KEYS = ['model', 'tag', 'battery', 'battery_model', 'batteryless', 'sd_card', 'sd_card_model', 'memory_cassette', 'memory_cassette_model',
  'memory_card', 'memory_card_model', 'board_model', 'board_tag'];
const POWER_KEYS = ['power_model', 'power_tag'];
const BASE_KEYS = ['base_model', 'base_tag'];
const FREE_SELECT = ['sd_card_model'];   // 候補から選ぶか自由に入力
const GROUP_LABEL = { in: '入力', out: '出力', analog: 'アナログ', comm: '通信・インテリ', mixed: '入出力混合' };
const LINEAR_KINDS = ['fx5body', 'mxbody', 'kvbody', 'nxbody'];
const VENDOR_BODY_KINDS = ['kvbody', 'nxbody'];
const KV_CONFIGURATION_SERIES = ['KV Nano', 'KV-8000', 'KV-7000', 'KV-X'];

function isLinearRack(rack = S.page && S.page.rack) { return !!rack && LINEAR_KINDS.includes(rack.kind); }
function isVendorRack(rack = S.page && S.page.rack) { return !!rack && VENDOR_BODY_KINDS.includes(rack.kind); }
function projectMaker() { return (S.snap && S.snap.maker) || 'mitsubishi'; }
function drawingTitle() {
  return { keyence: 'キーエンス KV 構成・図面', omron: 'オムロン NX 構成・図面' }[projectMaker()] || TITLES.drawing;
}

function fieldLabel(key) {
  if (key === 'maker') return 'メーカー';
  if (key === 'series') return 'シリーズ';
  const found = S.meta.fields.find(([k]) => k === key);
  return found ? found[1] : key;
}

function setStatus(text, warn = false) {
  S.status = { text, warn };
  const el = $('#status');
  el.textContent = text;
  el.className = 'status' + (warn ? ' warn' : '');
}

function applySnapshot(snap) {
  if (!snap || !snap.pages) return;
  S.snap = snap;
  if (S.index !== null && S.index >= snap.pages.length) {
    S.index = null;
    S.page = null;
  }
}

function applyPage(result) {
  if (!result) return;
  if (result.pages) {
    S.snap.pages = result.pages;
  }
  if (result.dirty !== undefined) S.snap.dirty = result.dirty;
  for (const key of ['can_undo', 'can_redo']) if (result[key] !== undefined) S.snap[key] = result[key];
  if (result.values) S.page = result;
}

// ------------------------------------------------------------ 描画
const TITLES = { home: 'PLC・GOT 図面生成', drawing: '三菱電機 PLC・GOT 図面', keyence: 'キーエンス KV・VT', omron: 'オムロン NX・NA', parts: '制御部品の書出し・ユーザーコレクション登録' };

function setMode(mode) {
  S.mode = mode;
  $('#view-home').hidden = mode !== 'home';
  $('#view-drawing').hidden = mode !== 'drawing';
  $('#view-keyence').hidden = mode !== 'keyence';
  $('#view-omron').hidden = mode !== 'omron';
  $('#view-parts').hidden = mode !== 'parts';
  $('#tools-drawing').hidden = mode !== 'drawing';
  $('#tools-parts').hidden = mode !== 'parts';
  document.querySelector('.home-btn').hidden = mode === 'home';
  $('#app-title').textContent = mode === 'drawing' ? drawingTitle() : TITLES[mode];
  if (mode === 'drawing') render();
  else if (mode === 'parts') renderParts();
  else if (mode === 'home') renderHome();
  else {
    renderConfigurationMenu();
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
  const select = $('#' + prefix + '-series');
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
  $('#' + prefix + '-single').hidden = config;
  if (!config) showMakerModels(prefix);
  const working = S.snap && (S.snap.pages.length || S.snap.path);
  const button = $('#' + prefix + '-config-continue');
  button.hidden = !working || projectMaker() !== S.mode;
  if (!button.hidden) button.textContent = `作業中の構成に戻る（${S.snap.name}${S.snap.dirty ? '・未保存' : ''}）`;
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

// ------------------------------------------------------------ ダイアログ
let dialogDepth = 0;
function openDialog(html, { narrow = false, onKey } = {}) {
  const host = document.createElement('div');
  host.className = 'overlay';
  host.innerHTML = `<div class="dialog${narrow ? ' narrow' : ''}" role="dialog" aria-modal="true">${html}</div>`;
  $('#dialogs').appendChild(host);
  dialogDepth += 1;
  host.close = () => { host.remove(); dialogDepth -= 1; };
  host.onKey = onKey;
  const first = host.querySelector('[autofocus]') || host.querySelector('input, select, button.primary-choice, button');
  if (first) setTimeout(() => first.focus(), 0);
  return host;
}

function showMessage(title, text, { error = false, buttons = [['ok', 'OK', true]] } = {}) {
  return new Promise((resolve) => {
    const host = openDialog(`<div class="dialog-head"><span class="t">${esc(title)}</span>
      <button type="button" class="x" data-close aria-label="閉じる">×</button></div>
      <div class="dialog-body"><div class="msg${error ? ' err' : ''}">${esc(text)}</div></div>
      <div class="dialog-foot"><span class="hint"></span>${buttons.map(([id, label, primary]) =>
        `<button type="button" class="btn${primary ? ' solid primary-choice' : ''}" data-choice="${id}">${esc(label)}</button>`).join('')}</div>`, { narrow: true });
    const finish = (value) => { host.close(); resolve(value); };
    host.addEventListener('click', (e) => {
      const choice = e.target.closest('[data-choice]');
      if (choice) finish(choice.dataset.choice);
      else if (e.target.closest('[data-close]')) finish(null);
    });
    host.onKey = (e) => { if (e.key === 'Escape') finish(null); };
  });
}

async function confirmBox(text, ok = 'OK') {
  return (await showMessage('確認', text, { buttons: [['cancel', 'キャンセル', false], ['ok', ok, true]] })) === 'ok';
}

function askFields(title, fields, okLabel = 'OK') {
  // fields: [{key, label, value, options:[[value,label]]|null}]
  return new Promise((resolve) => {
    const body = fields.map((f) => `<label>${esc(f.label)}${f.options
      ? `<select data-k="${f.key}">${f.options.map(([v, l]) => `<option value="${esc(v)}"${v === f.value ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`
      : `<input type="text" data-k="${f.key}" value="${esc(f.value || '')}">`}</label>`).join('');
    const host = openDialog(`<div class="dialog-head"><span class="t">${esc(title)}</span>
      <button type="button" class="x" data-close aria-label="閉じる">×</button></div>
      <div class="dialog-body"><div class="grid2" style="grid-template-columns:1fr">${body}</div></div>
      <div class="dialog-foot"><span class="hint"></span><button type="button" class="btn" data-close>キャンセル</button>
      <button type="button" class="btn solid" data-ok>${esc(okLabel)}</button></div>`, { narrow: true });
    const finish = (value) => { host.close(); resolve(value); };
    const collect = () => Object.fromEntries([...host.querySelectorAll('[data-k]')].map((el) => [el.dataset.k, el.value.trim()]));
    host.addEventListener('click', (e) => {
      if (e.target.closest('[data-ok]')) finish(collect());
      else if (e.target.closest('[data-close]')) finish(null);
    });
    host.onKey = (e) => {
      if (e.key === 'Escape') finish(null);
      if (e.key === 'Enter' && e.target.tagName === 'INPUT') finish(collect());
    };
  });
}

// ブラウザ確認用: ファイル選択の代わりにパスを入力する
async function pathFor(title, value = '') {
  if (!S.meta.browser_paths) return undefined;
  const result = await askFields(title, [{ key: 'path', label: 'ファイルの場所（フルパス）', value }]);
  return result && result.path ? result.path : null;
}

async function showDifferences() {
  const result = await run('detail_differences');
  if (!result) return;
  if (!result.rows.length) { await showMessage('構成との比較', '構成と詳細ページに差分はありません。'); return; }
  const rows = result.rows;
  const host = openDialog(`<div class="dialog-head"><span class="t">構成と詳細ページの差分</span><button type="button" class="x" data-close aria-label="閉じる">×</button></div>
    <div class="dialog-body"><p>修正する詳細ページを選択してください。CSVの内容は変更しません。先頭XYを変更した場合はCSVのアドレスも確認してください。</p>
    <div class="table-wrap"><table class="list"><thead><tr><th>修正</th><th>詳細ページ</th><th>項目</th><th>現在 → 構成</th></tr></thead><tbody>
    ${rows.map((row, i) => `<tr><td><input type="checkbox" data-diff="${i}" aria-label="${esc(row.label)}を修正" ${row.can_sync ? '' : 'disabled'}></td>
      <td><button type="button" class="btn small" data-diff-page="${row.page}">${esc(row.label)}</button></td>
      <td>${row.changes.map((c) => esc(c.label)).join('<br>')}</td><td>${row.changes.map((c) => `${esc(c.before || '空欄')} → ${esc(c.after || '空欄')}`).join('<br>')}${row.reason ? `<p>${esc(row.reason)}</p>` : ''}</td></tr>`).join('')}
    </tbody></table></div></div><div class="dialog-foot"><span class="hint">詳細ページの設定だけを変更します。「元に戻す」に対応しています。</span>
    <button type="button" class="btn solid" data-sync>選択した詳細を構成に合わせる</button></div>`);
  host.addEventListener('click', async (event) => {
    const page = event.target.closest('[data-diff-page]');
    if (page) { host.close(); await loadPage(Number(page.dataset.diffPage)); return; }
    const button = event.target.closest('[data-sync]');
    if (!button) return;
    const selected = Array.from(host.querySelectorAll('[data-diff]:checked')).map((input) => rows[Number(input.dataset.diff)]);
    if (!selected.length) { await showMessage('構成との比較', '修正する差分を選んでください。'); return; }
    button.disabled = true;
    const snapshot = await run('sync_details', selected);
    if (snapshot) { host.close(); await refreshAll(snapshot); setStatus(`${selected.length}件の詳細ページ設定を構成に合わせました。CSVは変更していません。`); }
    else button.disabled = false;
  });
  host.onKey = (event) => { if (event.key === 'Escape') host.close(); };
}

// 部品の選定ダイアログ
async function pickPart({ title, key, index = null, hint = '', stage = 0, bus = '' }) {
  const result = await run('catalog', key, index, stage, bus);
  if (!result) return null;
  return choosePart(title, key, result.rows, hint);
}

async function choosePart(title, key, rows, hint = '') {
  if (!rows.length) {
    await showMessage(title, 'この欄で選べる部品がありません。先にメーカー・シリーズ・種類を選んでください。');
    return null;
  }
  const showMaker = key === 'standard_model';
  const isModule = key === 'modules';
  const showLifecycle = rows.some((r) => r.production_end);
  return new Promise((resolve) => {
    const P = { group: '', maker: '', q: '', sel: null };
    const groups = () => {
      const counts = new Map();
      for (const r of rows) if (!P.maker || r.maker === P.maker) counts.set(r.group, (counts.get(r.group) || 0) + 1);
      return counts;
    };
    const filtered = () => rows.filter((r) => (!P.maker || r.maker === P.maker) && (!P.group || r.group === P.group) &&
      (!P.q || (r.model + ' ' + r.summary + ' ' + r.series + ' ' + r.production_end).toLowerCase().includes(P.q.toLowerCase())));
    const host = openDialog(`<div class="dialog-head"><span class="t">${esc(title)}</span>
        <button type="button" class="x" data-close aria-label="閉じる">×</button></div>
      <div class="dialog-body split"><div class="filters" id="pp-filters"></div><div class="table-wrap" id="pp-table"></div></div>
      <div class="dialog-foot"><span class="hint">${esc(hint || '一覧は部品データ（parts）に登録済みの機種です。')}</span>
        <button type="button" class="btn" data-close>キャンセル</button>
        <button type="button" class="btn solid" data-ok>OK</button></div>`);
    const drawFilters = () => {
      const makers = [...new Set(rows.map((r) => r.maker))];
      let html = `<div><div class="fh">検索</div><input type="text" id="pp-q" value="${esc(P.q)}" placeholder="形名・仕様"></div>`;
      if (showMaker && makers.length > 1) {
        html += `<div><div class="fh">メーカー</div><select id="pp-maker"><option value="">すべて</option>${makers.map((m) =>
          `<option${m === P.maker ? ' selected' : ''}>${esc(m)}</option>`).join('')}</select></div>`;
      }
      const counts = groups();
      html += `<div><div class="fh">種類</div><button type="button" class="pill${P.group ? '' : ' on'}" data-group="">すべて<span class="n">${[...counts.values()].reduce((a, b) => a + b, 0)}</span></button>`;
      for (const [g, n] of [...counts.entries()].sort()) html += `<button type="button" class="pill${P.group === g ? ' on' : ''}" data-group="${esc(g)}">${esc(g)}<span class="n">${n}</span></button>`;
      $('#pp-filters', host).innerHTML = html + '</div>';
    };
    const drawTable = () => {
      const list = filtered();
      if (P.sel && !list.some((r) => r.model === P.sel)) P.sel = null;
      $('[data-ok]', host).disabled = !P.sel;
      const cols = isModule ? ['形名', '種類', '仕様', '占有', '図面ページ'] : showMaker ? ['形名', 'メーカー', 'シリーズ', '種類', '仕様'] : ['形名', '種類', '仕様'];
      if (showLifecycle) cols.push('生産終了');
      let html = `<table class="list"><thead><tr><th style="width:36px"></th>${cols.map((c) => `<th>${c}</th>`).join('')}</tr></thead><tbody>`;
      for (const r of list) {
        const on = P.sel === r.model;
        html += `<tr class="row${on ? ' on' : ''}" data-model="${esc(r.model)}"><td><input type="radio" name="pp" ${on ? 'checked' : ''} aria-label="${esc(r.model)}"></td>
          <td class="model">${esc(r.model)}</td>`;
        if (isModule) html += `<td>${esc(r.group)}</td><td>${esc(r.summary)}</td><td class="muted">${r.slots > 1 ? r.slots + 'スロット<br>' : ''}${esc(r.points)}</td><td class="muted">${esc(r.pages || '構成図のみ')}</td>`;
        else if (showMaker) html += `<td>${esc(r.maker)}</td><td class="muted">${esc(r.series)}</td><td>${esc(r.group)}</td><td>${esc(r.summary)}</td>`;
        else html += `<td>${esc(r.group)}</td><td>${esc(r.summary)}</td>`;
        if (showLifecycle) html += `<td class="muted" style="white-space:nowrap">${esc(r.production_end || '—')}</td>`;
        html += '</tr>';
      }
      if (!list.length) html += `<tr><td colspan="${cols.length + 1}" class="muted" style="padding:20px">該当する部品がありません</td></tr>`;
      $('#pp-table', host).innerHTML = html + '</tbody></table>';
    };
    drawFilters();
    drawTable();
    const finish = (value) => { host.close(); resolve(value); };
    host.addEventListener('click', (e) => {
      const row = e.target.closest('tr.row');
      const group = e.target.closest('[data-group]');
      if (row) {
        P.sel = row.dataset.model;
        drawTable();
        if (e.detail === 2) finish(rows.find((r) => r.model === P.sel));
      } else if (group) {
        P.group = group.dataset.group;
        drawFilters();
        drawTable();
      } else if (e.target.closest('[data-ok]')) {
        if (P.sel) finish(rows.find((r) => r.model === P.sel));
      } else if (e.target.closest('[data-close]')) finish(null);
    });
    host.addEventListener('input', (e) => {
      if (e.target.id === 'pp-q') { P.q = e.target.value; drawTable(); }
    });
    host.addEventListener('change', (e) => {
      if (e.target.id === 'pp-maker') { P.maker = e.target.value; P.group = ''; drawFilters(); drawTable(); }
    });
    host.onKey = (e) => {
      if (e.key === 'Escape') finish(null);
      if (e.key === 'Enter' && P.sel) finish(rows.find((r) => r.model === P.sel));
    };
  });
}

// 配線情報ダイアログ
async function editWiring() {
  const data = await run('wiring', S.index);
  if (!data) return;
  const W = { group: 'connections', value: JSON.parse(JSON.stringify(data.value)), current: { connections: null, boundaries: null } };
  const form = { connections: { ...data.defaults.connections }, boundaries: { ...data.defaults.boundaries } };
  const numeric = (group) => data.position_fields[group].map(([k]) => k);
  const summary = (group, row) => group === 'boundaries'
    ? [row.part, row.left, row.right, row.x, `${row.top} - ${row.bottom}`]
    : [row.part, [row.unit_tag, row.unit_terminal].filter(Boolean).join(':'), [row.terminal_block, row.level, row.terminal].filter(Boolean).join(':'),
      row.wire, [row.cable, row.core].filter(Boolean).join(' / '), [row.peer_tag, row.peer_terminal].filter(Boolean).join(':'),
      [row.destination, row.reference, row.link_id].filter(Boolean).join(' / ')];
  const heads = { connections: ['分割頁', '対象機器 / 端子', '端子台', '線番', 'ケーブル', '相手機器', '送り先 / 参照'], boundaries: ['分割頁', '左側', '右側', '横位置', '上端 - 下端'] };
  const host = openDialog(`<div class="dialog-head"><span class="t">配線情報 — ${esc(data.name)}</span>
      <button type="button" class="x" data-close aria-label="閉じる">×</button></div>
    <div class="dialog-body" id="wd-body"></div>
    <div class="dialog-foot"><span class="hint">位置はQETでも移動できます。送り・受けは同じ参照IDの2件で対応します。未入力の項目は表示しません。</span>
      <button type="button" class="btn" data-close>取消</button><button type="button" class="btn solid" data-apply>適用</button></div>`);
  const readForm = () => {
    const row = { ...form[W.group] };
    for (const key of numeric(W.group)) {
      const n = Number(row[key]);
      if (row[key] === '' || !Number.isFinite(n) || (key === 'part' && !Number.isInteger(n))) throw new Error('分割頁は整数、配置位置は数値で入力してください');
      row[key] = n;
    }
    if (W.group === 'connections' && !data.content_fields.connections.some(([k]) => String(row[k] || '').trim())) throw new Error('接続注記の内容を1項目以上入力してください');
    for (const [k] of data.content_fields[W.group]) row[k] = String(row[k] || '').trim();
    return row;
  };
  const draw = () => {
    const g = W.group;
    const rows = W.value[g];
    let html = `<label style="display:flex;gap:8px;align-items:center;margin-bottom:10px"><input type="checkbox" id="wd-plan" ${W.value.terminal_plan ? 'checked' : ''}>端子台接続図を追加</label>
      <div class="tabs"><button type="button" class="tab${g === 'connections' ? ' on' : ''}" data-tab="connections">接続注記・端子台</button>
      <button type="button" class="tab${g === 'boundaries' ? ' on' : ''}" data-tab="boundaries">盤内外境界</button></div>
      <div style="max-height:220px;overflow:auto;border:1px solid var(--line-soft);border-radius:4px"><table class="list"><thead><tr>${heads[g].map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>`;
    rows.forEach((row, i) => {
      html += `<tr class="row${W.current[g] === i ? ' on' : ''}" data-row="${i}">${summary(g, row).map((v) => `<td>${esc(v)}</td>`).join('')}</tr>`;
    });
    if (!rows.length) html += `<tr><td colspan="${heads[g].length}" class="muted" style="padding:14px">まだありません。下の欄に入力して「追加」を押します。</td></tr>`;
    html += `</tbody></table></div>
      <div class="toolbar-row"><button type="button" class="btn solid" data-w="add">追加</button><button type="button" class="btn" data-w="update"${W.current[g] === null ? ' disabled' : ''}>更新</button>
      <button type="button" class="btn danger" data-w="delete"${W.current[g] === null ? ' disabled' : ''}>削除</button><button type="button" class="btn" data-w="clear">入力をクリア / 次行</button></div>
      <div class="sub-head" style="font-size:12px;font-weight:700;margin:6px 0">内容</div><div class="grid2">`;
    for (const [k, label] of data.content_fields[g]) {
      const v = form[g][k] ?? '';
      html += `<label>${esc(label)}${k === 'reference'
        ? `<select data-wf="${k}">${['', '送り', '受け'].map((o) => `<option value="${o}"${o === v ? ' selected' : ''}>${o || '—'}</option>`).join('')}</select>`
        : `<input type="text" data-wf="${k}" value="${esc(v)}">`}</label>`;
    }
    html += '</div><div class="sub-head" style="font-size:12px;font-weight:700;margin:12px 0 6px">配置</div><div class="grid2">';
    for (const [k, label] of data.position_fields[g]) html += `<label>${esc(label)}<input type="text" data-wf="${k}" value="${esc(form[g][k] ?? '')}"></label>`;
    $('#wd-body', host).innerHTML = html + '</div>';
  };
  draw();
  const report = (error) => showMessage('配線情報', error.message || String(error), { error: true });
  host.addEventListener('input', (e) => {
    if (e.target.dataset.wf) form[W.group][e.target.dataset.wf] = e.target.value;
  });
  host.addEventListener('change', (e) => {
    if (e.target.dataset.wf) form[W.group][e.target.dataset.wf] = e.target.value;
    if (e.target.id === 'wd-plan') W.value.terminal_plan = e.target.checked;
  });
  host.addEventListener('click', async (e) => {
    const g = W.group;
    const tab = e.target.closest('[data-tab]');
    const row = e.target.closest('tr.row');
    const act = e.target.closest('[data-w]');
    if (tab) { W.group = tab.dataset.tab; draw(); return; }
    if (row) {
      const i = Number(row.dataset.row);
      W.current[g] = i;
      form[g] = { ...W.value[g][i] };
      draw();
      return;
    }
    if (act) {
      try {
        if (act.dataset.w === 'add') { W.value[g].push(readForm()); W.current[g] = W.value[g].length - 1; }
        if (act.dataset.w === 'update' && W.current[g] !== null) W.value[g][W.current[g]] = readForm();
        if (act.dataset.w === 'delete' && W.current[g] !== null) { W.value[g].splice(W.current[g], 1); W.current[g] = null; form[g] = { ...data.defaults[g] }; }
        if (act.dataset.w === 'clear') {
          const next = { ...data.defaults[g] };
          if (g === 'connections') {
            const part = Number(form[g].part), x = Number(form[g].x);
            if (!Number.isInteger(part) || !Number.isFinite(x)) throw new Error('分割頁は整数、横位置は数値で入力してください');
            next.part = part; next.x = x;
            const ys = W.value[g].filter((r) => r.part === part && r.x === x).map((r) => r.y);
            if (ys.length) next.y = Math.max(...ys) + 100;
          }
          W.current[g] = null;
          form[g] = next;
        }
        draw();
      } catch (error) { report(error); }
      return;
    }
    if (e.target.closest('[data-apply]')) {
      const result = await run('set_wiring', S.index, W.value);
      if (result) { applyPage(result); host.close(); render(); setStatus('配線情報を反映しました'); }
      return;
    }
    if (e.target.closest('[data-close]')) host.close();
  });
  host.onKey = (e) => { if (e.key === 'Escape') host.close(); };
}

// ------------------------------------------------------------ 操作
async function loadPage(index, keepSel = false) {
  const result = await run('page', index);
  if (!result) return;
  S.index = index;
  S.page = result;
  const parent = S.snap.pages[index] && S.snap.pages[index].parent;
  if (parent !== null && parent !== undefined) S.collapsed.delete(parent);
  if (!keepSel) S.sel = null;
  render();
}

async function refreshAll(snap, index = S.index) {
  applySnapshot(snap);
  if (index !== null && index !== undefined && index < S.snap.pages.length) await loadPage(index, true);
  else { S.index = null; S.page = null; render(); }
}

async function updatePage(changed = '') {
  if (S.index === null || !S.page) return;
  const extraEl = $('#extra');
  const extra = extraEl ? extraEl.value : S.page.extra;
  const result = await run('update_page', S.index, S.page.values, extra, changed);
  if (result) {
    applyPage(result);
  } else {
    await loadPage(S.index, true);
    return;
  }
  render();
  return result;
}

async function confirmDiscard() {
  if (!S.snap.dirty) return true;
  return confirmBox('保存していない変更を破棄しますか？', '破棄する');
}

async function saveAs() {
  const path = await pathFor('名前を付けて保存', S.snap.path || '');
  if (path === null) return false;
  let result = await run('save_as', path);
  if (result && result.confirm) {
    if (!(await confirmBox(result.confirm, '保存する'))) return false;
    result = await run('save_as', result.path, true);
  }
  if (!result) return false;
  applySnapshot(result);
  render();
  setStatus('保存しました: ' + result.path);
  return true;
}

async function save() {
  const result = await run('save');
  if (!result) return false;
  if (result.need_save_as) return saveAs();
  applySnapshot(result);
  render();
  setStatus('保存しました: ' + result.path);
  return true;
}

async function generate(includeDetails = null) {
  const vendor = includeDetails !== null;
  if (!vendor && !S.snap.path && !(await saveAs())) return;
  const stem = S.snap.path ? S.snap.path.replace(/\.json$/i, '') : S.snap.pages.find((page) => VENDOR_BODY_KINDS.includes(page.kind))?.model || 'project';
  const out = await pathFor('図面の保存先（.qet）', stem + (includeDetails === false ? '_構成.qet' : '.qet'));
  if (out === null) return;
  setStatus('図面を生成しています…');
  const method = vendor ? ['generate_configuration', includeDetails] : ['generate'];
  let result = await run(...method, out);
  if (result && result.confirm) {
    if (!(await confirmBox(result.confirm, '上書きする'))) { setStatus(''); return; }
    result = await run(...method, result.out, true);
  }
  if (!result) { setStatus(''); return; }
  if (result.need_save_as) return;
  if (vendor) await refreshAll(result, S.index === null ? null : result.index);
  else { applySnapshot(result.snapshot); render(); }
  setStatus('図面を生成しました: ' + result.out);
  const buttons = S.meta.browser_paths ? [['ok', 'OK', true]] : [['close', '閉じる', false], ['open', 'QETで開く', true]];
  if ((await showMessage('生成完了', result.message, { buttons })) === 'open') await run('open_file', result.out);
}

function showMakerModels(prefix) {
  const series = $('#' + prefix + '-series');
  if (series.dataset.task === 'configuration') return;
  const select = $('#' + prefix + '-model');
  const previous = select.value;
  const query = $('#' + prefix + '-search').value.normalize('NFKC').trim().toUpperCase();
  const kv = prefix === 'kv';
  const seriesByModel = kv ? S.meta.kv_models : S.meta.omron_series;
  const functions = kv ? S.meta.kv_functions : S.meta.nx_models;
  const choices = Object.entries(seriesByModel).filter(([model, families]) => {
    const role = functions[model];
    const keywords = role === 'パルス出力' ? 'パルス出力 位置決め' : role;
    return (role === 'タッチパネル') === (series.dataset.task === 'panel')
      && (!series.value || families.includes(series.value))
      && (model + ' ' + keywords).normalize('NFKC').toUpperCase().includes(query);
  }).map(([model]) => new Option(model + '　' + functions[model], model));
  select.replaceChildren(...(choices.length ? choices : [new Option('該当する形名がありません', '')]));
  if (choices.some((option) => option.value === previous)) select.value = previous;
  select.disabled = !choices.length;
  $('[data-action="' + prefix + '-generate"]').disabled = !choices.length;
  if (kv) showKvSettings();
}

function showKvSettings() {
  const model = $('#kv-model').value;
  const role = S.meta.kv_functions[model] || '';
  $('#kv-wiring-note').hidden = !(role.startsWith('デジタル') || role === 'CPU・内蔵I/O');
  const modes = S.meta.kv_modes[model] || [];
  $('#kv-mode-field').hidden = modes.length === 0;
  const select = $('#kv-mode');
  if (select.dataset.model !== model) {
    select.replaceChildren(...modes.map((mode) => new Option(mode, mode)));
    select.dataset.model = model;
  }
  const settings = S.meta.kv_settings[model] || [];
  for (const key of ['ip', 'communication']) {
    $('#kv-' + key + '-field').hidden = !settings.includes(key);
  }
}

// ------------------------------------------------------------ 制御部品の書出し・ユーザーコレクション登録画面
const PV = { rows: null, maker: '', group: '', q: '', sel: null, options: null, choice: {}, registering: false };

async function renderParts() {
  $('#file').textContent = '';
  $('#dirty').textContent = '';
  document.title = '制御部品の書出し・ユーザーコレクション登録 - PLC・GOT 図面生成';
  if (!PV.rows) {
    $('#parts-table').innerHTML = '<div class="empty-state">読み込み中…</div>';
    const result = await run('catalog', 'standard_model', null);
    PV.rows = result ? result.rows : [];
  }
  renderPartsFilters();
  renderPartsTable();
  renderPartsDrawer();
}

function partsFiltered() {
  const q = PV.q.toLowerCase();
  return PV.rows.filter((r) => (!PV.maker || r.maker === PV.maker) && (!PV.group || r.group === PV.group) &&
    (!q || (r.model + ' ' + r.summary + ' ' + r.series).toLowerCase().includes(q)));
}

function renderPartsFilters() {
  const makers = [...new Set(PV.rows.map((r) => r.maker))].sort();
  const counts = new Map();
  for (const r of PV.rows) if (!PV.maker || r.maker === PV.maker) counts.set(r.group, (counts.get(r.group) || 0) + 1);
  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  let html = `<div class="pane-head">絞り込み</div><div class="filters" style="width:auto;border:0">
    <div><div class="fh">検索</div><input type="text" id="pv-q" value="${esc(PV.q)}" placeholder="形名・仕様"></div>
    <div><div class="fh">メーカー</div><select id="pv-maker"><option value="">すべて</option>${makers.map((m) =>
      `<option${m === PV.maker ? ' selected' : ''}>${esc(m)}</option>`).join('')}</select></div>
    <div><div class="fh">種類</div><button type="button" class="pill${PV.group ? '' : ' on'}" data-pv-group="">すべて<span class="n">${total}</span></button>`;
  for (const [g, n] of [...counts.entries()].sort()) html += `<button type="button" class="pill${PV.group === g ? ' on' : ''}" data-pv-group="${esc(g)}">${esc(g)}<span class="n">${n}</span></button>`;
  $('#parts-filters').innerHTML = html + '</div></div>';
}

function renderPartsTable() {
  const list = partsFiltered();
  let html = `<div class="pane-head">部品<span class="count">${list.length} 件</span>
    <button type="button" class="btn solid" data-action="pv-register-all" ${PV.registering ? 'disabled' : ''}>${PV.registering ? '登録中…' : `全部QETに登録（${PV.rows.length}機種）`}</button></div>
    <div class="hint">全メーカーの全部品・選択可能な全構成を登録します。検索・絞り込みに関係なく対象になります。</div>
    <div class="table-wrap"><table class="list"><thead><tr><th style="width:36px"></th>
    <th>形名</th><th>メーカー</th><th>シリーズ</th><th>種類</th><th>仕様</th></tr></thead><tbody>`;
  for (const r of list) {
    const on = PV.sel === r.model;
    html += `<tr class="row${on ? ' on' : ''}" data-pv-model="${esc(r.model)}"><td><input type="radio" name="pv" ${on ? 'checked' : ''} aria-label="${esc(r.model)}"></td>
      <td class="model">${esc(r.model)}</td><td>${esc(r.maker)}</td><td class="muted">${esc(r.series)}</td><td>${esc(r.group)}</td><td>${esc(r.summary)}</td></tr>`;
  }
  if (!list.length) html += '<tr><td colspan="6" class="muted" style="padding:20px">該当する部品がありません</td></tr>';
  $('#parts-table').innerHTML = html + '</tbody></table></div>';
}

function renderPartsDrawer() {
  const el = $('#parts-drawer');
  const row = PV.rows.find((r) => r.model === PV.sel);
  if (!row) {
    el.innerHTML = `<div class="where">制御部品の書出し・ユーザーコレクション登録</div><div class="model" style="font-size:16px;font-family:inherit">部品を選んでください</div>
      <div class="hint">リレー・接触器・スイッチ・センサ等はQET標準の記号に、型式と実端子番号を割り当てます。電源・ハブは端子図の部品です。<br><br>「QETに登録」でユーザーコレクションへ直接保存できます。コイルと接点はQETで関連付けてください。</div>`;
    return;
  }
  const o = PV.options;
  let html = `<div class="where">${esc(row.maker)}・${esc(row.series)}</div><div class="model">${esc(row.model)}</div>
    <div class="desc">${esc(row.group)}${row.summary ? '　' + esc(row.summary) : ''}</div><div class="divider"></div>`;
  if (!o) html += '<div class="hint">読み込み中…</div>';
  else {
    if (o.auxiliary.length) {
      html += `<label class="field">補助接点構成<select id="pv-aux">${o.auxiliary.map(([v, l]) =>
        `<option value="${esc(v)}"${(PV.choice.auxiliary || o.default_auxiliary) === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
    }
    if (o.configuration.length) {
      html += `<label class="field">動作構成<select id="pv-conf">${o.configuration.map(([v, l]) =>
        `<option value="${esc(v)}"${PV.choice.configuration === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
    }
    html += `<button type="button" class="dbtn" data-action="pv-register">QETに登録</button>
      <div class="hint">ユーザーコレクションの「qet-io-builder」へ保存します。同じ形名・構成は更新します。</div>
      <button type="button" class="dbtn" data-action="pv-export">書き出す…</button>
      <div class="hint">別のフォルダへ保存する場合はこちら。定格・設定は実際の構成に合わせて確認してください。</div>`;
  }
  el.innerHTML = html;
}

async function selectPart(model) {
  PV.sel = model;
  PV.options = null;
  PV.choice = {};
  renderPartsTable();
  renderPartsDrawer();
  const options = await run('part_options', model);
  if (PV.sel !== model) return;
  PV.options = options || { auxiliary: [], configuration: [] };
  if (PV.options.auxiliary && PV.options.auxiliary.length) PV.choice.auxiliary = PV.options.default_auxiliary || PV.options.auxiliary[0][0];
  if (PV.options.configuration && PV.options.configuration.length) PV.choice.configuration = PV.options.configuration[0][0];
  renderPartsDrawer();
}

async function exportSelectedPart() {
  if (!PV.sel || !PV.options) return;
  const folder = await pathFor('書出し先のフォルダ（QETのユーザーコレクション等）');
  if (folder === null) return;
  const result = await run('export_part', PV.sel, PV.choice.auxiliary || null, PV.choice.configuration || null, folder);
  if (result) {
    setStatus(`${PV.sel} を書き出しました`);
    await showMessage('部品を書出し', result.message);
  }
}

async function registerSelectedPart() {
  if (!PV.sel || !PV.options) return;
  const result = await run('register_part', PV.sel, PV.choice.auxiliary || null, PV.choice.configuration || null);
  if (result) {
    setStatus(`${PV.sel} をQETに登録しました`);
    await showMessage('QETに登録', result.message);
  }
}

async function registerAllParts() {
  if (PV.registering) return;
  PV.registering = true;
  renderPartsTable();
  setStatus('全部品をQETに登録しています…');
  try {
    const result = await run('register_all_parts');
    if (result) {
      setStatus(result.ok ? '全部品のQET登録が完了しました' : '一部の部品を登録できませんでした');
      await showMessage('全部QETに登録', result.message);
    }
  } finally {
    PV.registering = false;
    renderPartsTable();
  }
}

async function updateXrefs() {
  const source = await pathFor('QETで保存した図面（.qet）');
  if (source === null) return;
  const output = source ? source.replace(/\.qet$/i, '_xref.qet') : undefined;
  const result = await run('update_xrefs', source, output);
  if (result) await showMessage('参照表を更新', result.message);
}

async function makeSample() {
  const path = await pathFor('CSV雛形の保存先（.json）');
  if (path === null) return;
  let result = await run('make_sample', S.index, path);
  if (result && result.confirm) {
    if (!(await confirmBox(result.confirm, '上書きする'))) return;
    result = await run('make_sample', S.index, result.path, true);
  }
  if (result) await showMessage('CSV雛形', result.message);
}

async function pickField(key) {
  const rack = ['qbody', 'iqrbody'].includes(S.page.values.kind);
  if (key === 'model' && rack && !S.page.values.base_model && !await pickField('base_model')) return;
  const titles = { model: rack || isVendorRack() ? 'CPUを選択' : '形名を選択', left_model: '左側の通信ユニットを選択', right_model: '右側の通信ユニットを選択', power_model: '電源ユニットを選択', base_model: 'ベースを選択' };
  const row = await pickPart({ title: titles[key] || '部品を選択', key, index: S.index });
  if (!row) return;
  S.page.values[key] = row.model;
  return await updatePage(key);
}

async function setupRack() {
  if (!['qbody', 'iqrbody'].includes(S.page.values.kind)) return;
  if (!S.page.values.base_model) await pickField('base_model');
}

async function addModule(stage, slot, bus = '') {
  const native = isVendorRack();
  const options = S.page.rack.bus_options || [];
  const existing = S.page.rack.stages.flatMap((s) => s.items).find((i) => i.type === 'module' && i.stage === stage && i.slot === slot);
  if (native && !bus) {
    bus = (existing && existing.bus) || '';
    if (!bus && options.length === 1) bus = options[0][0];
    if (!bus && options.length > 1) {
      const choice = await showMessage('接続位置を選択', 'ユニットを追加する位置を選んでください。',
        { buttons: [['cancel', 'キャンセル', false], ...options.map(([value, label]) => [value, label, false])] });
      if (!choice || choice === 'cancel') return;
      bus = choice;
    }
  }
  const busLabel = options.find(([value]) => value === bus);
  const row = await pickPart({ title: `ユニットを選択（${native ? (busLabel ? busLabel[1] : '接続位置') : isLinearRack() ? '増設' : 'スロット'}）`, key: 'modules', index: S.index, stage, bus,
    hint: native ? '選んだユニットを構成へ追加します。「詳細ページを一括作成」で各ユニットの図面をまとめて作れます。' : '選んだユニットは構成図に入ります。端子図などの図面ページは右側のボタンで作成します。' });
  if (!row) return;
  const extra = native ? [bus] : [];
  const modes = native && S.meta.kv_modes[row.model];
  if (modes?.length) {
    const current = existing?.model === row.model ? existing.communication_mode : modes[0];
    const chosen = await askFields(row.model, [{ key: 'mode', label: '通信方式', value: current, options: modes.map((mode) => [mode, mode]) }],
      existing ? '変更' : '追加');
    if (!chosen) return;
    extra.push(chosen.mode);
  }
  const result = await run('set_module', S.index, stage, slot, row.model, ...extra);
  if (result) {
    applyPage(result);
    if (isLinearRack()) {
      const selected = S.page.rack.stages.flatMap((s) => s.items).find((i) => i.type === 'module' && i.stage === stage && i.slot === slot);
      S.sel = selected ? selected.id : `${stage}:${slot}`;
    }
    render();
    setStatus(`${row.model} を追加しました`);
  }
}

function currentConfigurationSeries(maker) {
  if (maker === 'omron') return 'NX';
  const series = S.page && S.page.values.series;
  const label = S.meta.series[series] || series;
  return KV_CONFIGURATION_SERIES.includes(label) ? label : KV_CONFIGURATION_SERIES.includes($('#kv-series').value) ? $('#kv-series').value : 'KV Nano';
}

async function newConfiguration(maker, series) {
  if (maker === 'keyence' ? !KV_CONFIGURATION_SERIES.includes(series) : series !== 'NX') return;
  const roots = await run('configuration_roots', maker, series);
  if (!roots) return;
  const root = roots.rows.length === 1 ? roots.rows[0]
    : await choosePart(series + ' のCPU・カプラを選択', 'configuration_root', roots.rows);
  if (!root || !(await confirmDiscard())) return;
  const snap = await run('new_configuration', maker, series, root.model);
  if (!snap) return;
  S.index = null; S.page = null; S.sel = null;
  applySnapshot(snap);
  setMode('drawing');
  await refreshAll(snap, snap.index ?? 0);
  S.sel = 'cpu'; renderDrawer();
  setStatus(root.model + ' の構成を作成しました。接続位置の「追加」からユニットを選んでください。');
}

async function openConfiguration(maker) {
  if (!(await confirmDiscard())) return;
  const path = await pathFor('構成プロジェクト（.json）を開く');
  if (path === null) return;
  const snap = await run('open_configuration', maker, path);
  if (!snap) return;
  S.index = null; S.page = null; S.sel = null;
  applySnapshot(snap);
  setMode('drawing');
  await refreshAll(snap, snap.index ?? (snap.pages.length ? 0 : null));
  setStatus('開きました: ' + snap.path);
}

async function addExtension() {
  const base = await pickPart({ title: '増設ベースを選択', key: 'extension_base_model', index: S.index });
  if (!base) return;
  let power = '';
  if (base.power_required !== false) {
    const row = await pickPart({ title: `${base.model} の電源ユニットを選択`, key: 'power_model', index: S.index });
    if (!row) return;
    power = row.model;
  }
  const result = await run('add_extension', S.index, base.model, power);
  if (result) { applyPage(result); render(); setStatus(`増設ベース ${base.model} を追加しました`); }
}

async function stagePick(stage, key) {
  const row = await pickPart({ title: key === 'base_model' ? '増設ベースを選択' : '電源ユニットを選択', key: key === 'base_model' ? 'extension_base_model' : 'power_model', index: S.index });
  if (!row) return;
  const result = await run('set_stage_part', S.index, stage, key, row.model, null);
  if (result) { applyPage(result); render(); }
}

const actions = {
  differences: showDifferences,
  async 'open-csv'(el) {
    const result = await run('open_csv', S.index, el.dataset.key);
    if (result) setStatus('CSVを開きました。編集・保存後に「CSV再チェック」を押してください。');
  },
  async 'csv-recheck'() { await actions.check(); },
  'goto-alarm'(el) {
    S.sel = el.dataset.id;
    render();
    let target;
    if (el.dataset.field === 'start') target = $('#drawer [data-module-start]');
    if (el.dataset.field === 'extra') {
      target = $('#extra');
      if (target) target.closest('details').open = true;
    }
    if (!target) target = document.querySelector(`[data-action="select-item"][data-id="${S.sel}"]`);
    if (target) { target.focus(); target.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
  },
  async undo() { const r = await run('undo'); if (r) { S.sel = null; await refreshAll(r, r.index); setStatus('元に戻しました'); } },
  async redo() { const r = await run('redo'); if (r) { S.sel = null; await refreshAll(r, r.index); setStatus('やり直しました'); } },
  'toggle-group'(el) { const i = Number(el.dataset.index); if (S.collapsed.has(i)) S.collapsed.delete(i); else S.collapsed.add(i); renderPages(); },
  async new() {
    if (projectMaker() !== 'mitsubishi') return newConfiguration(projectMaker(), currentConfigurationSeries(projectMaker()));
    if (!(await confirmDiscard())) return;
    const snap = await run('new_project');
    if (snap) { S.sel = null; await refreshAll(snap, null); setStatus('新しいプロジェクト'); }
  },
  async open() {
    if (!(await confirmDiscard())) return;
    const path = await pathFor('プロジェクト（.json）を開く');
    if (path === null) return;
    const snap = await run('open_project', path);
    if (snap) { S.sel = null; S.mode = 'drawing'; setMode('drawing'); await refreshAll(snap, snap.pages.length ? 0 : null); setStatus('開きました: ' + snap.path); }
  },
  save, 'save-as': saveAs, generate: () => generate(), xrefs: updateXrefs,
  'generate-bundle': () => generate(true), 'generate-overview': () => generate(false),
  async home() { setMode('home'); },
  async 'home-new'() {
    if ((S.snap.pages.length || S.snap.path) && !(await confirmDiscard())) return;
    const snap = await run('new_project');
    if (!snap) return;
    S.index = null; S.page = null; S.sel = null;
    applySnapshot(snap);
    setMode('drawing');
    setStatus('新しいプロジェクト。左の「ページ追加」でページを作ります');
  },
  async 'home-open'() {
    await actions.open();
    if (S.snap.path) setMode('drawing');
  },
  async 'home-continue'() { setMode('drawing'); },
  async 'home-parts'() { setMode('parts'); },
  async 'home-keyence'() { setMode('keyence'); },
  async 'home-omron'() { setMode('omron'); },
  async 'kv-config-new'() { await newConfiguration('keyence', $('#kv-series').value); },
  async 'nx-config-new'() { await newConfiguration('omron', $('#nx-series').value); },
  async 'kv-config-open'() { await openConfiguration('keyence'); },
  async 'nx-config-open'() { await openConfiguration('omron'); },
  async 'nx-generate'() {
    const model = $('#nx-model').value;
    const panel = $('#nx-series').dataset.task === 'panel';
    const path = await pathFor(panel ? 'NAタッチパネル図面の保存先（.qet）' : 'NXユニット図面の保存先（.qet）', model + '.qet');
    if (path === null) return;
    const result = await run('generate_nx', model, $('#nx-unit-no').value, $('#nx-tag').value, path);
    if (result) setStatus('図面を生成しました: ' + result.out);
  },
  async 'kv-generate'() {
    const model = $('#kv-model').value;
    const series = $('#kv-series').value || S.meta.kv_models[model][0];
    const path = await pathFor(series.startsWith('VT') ? 'VTタッチパネル図面の保存先（.qet）' : 'KVユニット図面の保存先（.qet）', model + '.qet');
    if (path === null) return;
    const settings = Object.fromEntries((S.meta.kv_settings[model] || []).map((key) => [key, $('#kv-' + key).value]));
    const result = await run('generate_kv', series, model, $('#kv-unit-no').value, $('#kv-tag').value, path, $('#kv-mode').value, settings);
    if (result) setStatus('図面を生成しました: ' + result.out);
  },
  async 'pv-export'() { await exportSelectedPart(); },
  async 'pv-register'() { await registerSelectedPart(); },
  async 'pv-register-all'() { await registerAllParts(); },
  async check() {
    setStatus('チェックしています…');
    const result = await call('check');
    if (result && result.ok) {
      const warned = result.message.includes('警告');
      setStatus(warned ? '構成チェック: エラーはありません（警告あり）' : '構成チェック: エラーはありません', warned);
      await showMessage('構成チェック', result.message);
    }
    else { setStatus('構成チェック: 直すところがあります', true); await showMessage('構成チェック', (result && result.error) || '', { error: true }); }
  },
  async 'add-page'() {
    const result = await run('add_page', S.index);
    if (result) { await refreshAll(result, result.index); }
  },
  async duplicate() {
    const result = await run('duplicate_page', S.index);
    if (result) await refreshAll(result, result.index);
  },
  async 'delete-page'() {
    const info = S.snap.pages[S.index];
    if (!(await confirmBox(`${S.index + 1}ページ目（${info.kind_name} ${info.tag || info.model}）を削除しますか？`, '削除する'))) return;
    const snap = await run('delete_page', S.index);
    if (snap) await refreshAll(snap, Math.min(S.index, snap.pages.length - 1) >= 0 ? Math.min(S.index, snap.pages.length - 1) : null);
  },
  async 'move-up'() { const r = await run('move_page', S.index, -1); if (r) await refreshAll(r, r.index); },
  async 'move-down'() { const r = await run('move_page', S.index, 1); if (r) await refreshAll(r, r.index); },
  async 'select-project'() { S.index = null; S.page = null; S.sel = null; render(); },
  async 'select-page'(el) { await loadPage(Number(el.dataset.index)); },
  async 'goto-page'(el) { await loadPage(Number(el.dataset.index)); },
  async 'select-item'(el) {
    S.sel = el.dataset.id;
    const found = findItem(S.sel);
    if (found && found.item.type === 'add') { await addModule(found.item.stage, found.item.slot, found.item.bus || ''); return; }
    renderMain();
    renderDrawer();
  },
  async 'pick-field'(el) { await pickField(el.dataset.key); },
  async 'clear-field'(el) { S.page.values[el.dataset.key] = ''; await updatePage(el.dataset.key); },
  async 'pick-csv'(el) {
    const path = await pathFor('CSVを選択');
    if (path === null) return;
    const result = await run('pick_csv', path);
    if (result) { S.page.values[el.dataset.key] = result.path; await updatePage(el.dataset.key); }
  },
  async 'add-module'(el) { await addModule(Number(el.dataset.stage), Number(el.dataset.slot), el.dataset.bus || ''); },
  async 'remove-module'(el) {
    const result = await run('remove_module', S.index, Number(el.dataset.stage), Number(el.dataset.slot));
    if (result) { applyPage(result); render(); setStatus('ユニットを取り外しました'); }
  },
  async 'create-unit-page'(el) {
    const result = await run('create_unit_page', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.dataset.kind);
    if (result) { await refreshAll(result, result.index); setStatus(`${result.index + 1}ページ目に図面ページを作成しました`); }
  },
  async 'create-cpu-io'() {
    const result = await run('create_cpu_io_page', S.index);
    if (result) await refreshAll(result, result.index);
  },
  'add-extension': addExtension,
  async 'remove-extension'(el) {
    if (!(await confirmBox('この増設ベースと、載っているユニットを外しますか？', '外す'))) return;
    const result = await run('remove_extension', S.index, Number(el.dataset.stage));
    if (result) { applyPage(result); S.sel = null; render(); }
  },
  async 'stage-pick'(el) { await stagePick(Number(el.dataset.stage), el.dataset.key); },
  async 'all-pages'() {
    if (isVendorRack()) {
      const choice = await showMessage('詳細ページを一括作成', '構成のCPU・電源・ユニットのうち、まだ詳細ページがないものをまとめて作成します。',
        { buttons: [['cancel', 'キャンセル', false], ['pages', '詳細ページを作成', true]] });
      if (choice !== 'pages') return;
      const result = await run('create_all_unit_pages', S.index, false);
      if (!result) return;
      await refreshAll(result, S.index);
      setStatus(result.message.split('\n')[0]);
      await showMessage('詳細ページを一括作成', result.message);
      return;
    }
    const choice = await showMessage('詳細ページを一括作成',
      '構成のユニットのうち、まだページが無いものに図面ページを作ります（形名・タグ・スロット番号・先頭アドレス入り。通信ユニットは接続図）。\n入出力・アナログのページには、アドレスを入れたCSV（信号名は空欄）も作れます。CSVはプロジェクトと同じフォルダに作り、既にあるファイルは上書きしません。\nCSVが無くても図面は作れます（用途欄が空欄の図面）。',
      { buttons: [['cancel', 'キャンセル', false], ['pages', 'ページだけ作成', false], ['csv', 'ページとCSVを作成', true]] });
    if (choice !== 'pages' && choice !== 'csv') return;
    if (choice === 'csv' && !S.snap.path && !(await saveAs())) return;
    const result = await run('create_all_unit_pages', S.index, choice === 'csv');
    if (!result) return;
    if (result.need_save_as) return;
    await refreshAll(result, S.index);
    setStatus(result.message.split('\n')[0]);
    await showMessage('詳細ページを一括作成', result.message);
  },
  async 'page-csv'() {
    if (!S.snap.path && !(await saveAs())) return;
    const result = await run('make_page_csv', S.index);
    if (!result || result.need_save_as) return;
    applyPage(result);
    render();
    if (result.message) await showMessage('CSVを作成', result.message + '\n\nExcelで信号名などを入力して保存し、「図面生成」で反映します。');
  },
  wiring: editWiring,
  sample: makeSample,
};

// 操作は1つずつ順に処理する(前の結果で画面を描き直してから次へ)
let chain = Promise.resolve();
function serial(task) {
  const next = chain.then(task, task);
  chain = next.catch(() => {});
  return next;
}

document.addEventListener('click', (e) => {
  if (dialogDepth && !e.target.closest('.overlay')) return;
  if (S.mode === 'parts' && !e.target.closest('.overlay')) {
    const group = e.target.closest('[data-pv-group]');
    const row = e.target.closest('tr[data-pv-model]');
    if (group) { PV.group = group.dataset.pvGroup; renderPartsFilters(); renderPartsTable(); return; }
    if (row) { selectPart(row.dataset.pvModel); return; }
  }
  const el = e.target.closest('[data-action]');
  if (!el || el.closest('.overlay')) return;
  const action = actions[el.dataset.action];
  if (action) serial(() => action(el));
});

document.addEventListener('change', (e) => {
  if (e.target.closest('.overlay')) return;
  serial(() => onChange(e.target));
});

document.addEventListener('input', (e) => {
  if (e.target.id === 'pv-q') { PV.q = e.target.value; renderPartsTable(); }
  if (e.target.id === 'nx-search' || e.target.id === 'kv-search') showMakerModels(e.target.id.slice(0, 2));
});

async function onChange(el) {
  if (el.name === 'kv-task' || el.name === 'nx-task') { renderConfigurationMenu(); return; }
  if (el.id === 'nx-series' || el.id === 'kv-series') { showMakerModels(el.id.slice(0, 2)); return; }
  if (el.id === 'kv-model') { showKvSettings(); return; }
  if (el.dataset.settingVisible) {
    const result = await run('set_setting_visibility', S.index, el.dataset.settingVisible, el.checked);
    if (result) { applyPage(result); render(); }
    else await loadPage(S.index, true);
    return;
  }
  if (el.id === 'pv-maker') { PV.maker = el.value; PV.group = ''; renderPartsFilters(); renderPartsTable(); return; }
  if (el.id === 'pv-aux') { PV.choice.auxiliary = el.value; return; }
  if (el.id === 'pv-conf') { PV.choice.configuration = el.value; return; }
  if (el.id === 'pv-q') return;
  if (el.dataset.project || el.dataset.power || el.dataset.projectCheck) {
    const values = { power: {} };
    document.querySelectorAll('[data-project]').forEach((input) => { values[input.dataset.project] = input.value; });
    document.querySelectorAll('[data-power]').forEach((input) => { values.power[input.dataset.power] = input.value; });
    const check = document.querySelector('[data-project-check]');
    if (check) values.front_pages = check.checked;
    const snap = await run('set_project', values);
    if (snap) { applySnapshot(snap); renderHeader(); renderPages(); }
    return;
  }
  if (el.dataset.field) {
    S.page.values[el.dataset.field] = el.value;
    const result = await updatePage(el.dataset.field);
    if (result && el.dataset.field === 'kind') await setupRack();
    return;
  }
  if (el.dataset.extra !== undefined) {
    await updatePage('extra');
    return;
  }
  if (el.dataset.moduleStart !== undefined) {
    const result = await run('set_module_start', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) {
      applyPage(result);
      render();
      const alarms = (result.rack && result.rack.alarms) || [];
      setStatus(alarms.length ? `XY割付の警告が${alarms.length}件あります` : '先頭XYを反映しました', alarms.length > 0);
    } else {
      await loadPage(S.index, true);
    }
    return;
  }
  if (el.dataset.moduleTag !== undefined) {
    const result = await run('set_module_tag', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) { applyPage(result); render(); }
    return;
  }
  if (el.dataset.moduleMode !== undefined) {
    const result = await run('set_module_mode', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) { applyPage(result); render(); setStatus('通信方式を変更しました'); }
    else await loadPage(S.index, true);
    return;
  }
  if (el.dataset.moduleBus !== undefined) {
    const result = await run('set_module_bus', S.index, Number(el.dataset.stage), Number(el.dataset.slot), el.value);
    if (result) { applyPage(result); render(); setStatus('接続位置を変更しました'); }
    else await loadPage(S.index, true);
    return;
  }
  if (el.dataset.stageTag) {
    const result = await run('set_stage_part', S.index, Number(el.dataset.stage), el.dataset.stageTag, null, el.value);
    if (result) { applyPage(result); render(); }
  }
}

document.addEventListener('keydown', async (e) => {
  const top = $('#dialogs').lastElementChild;
  if (top && top.onKey) { top.onKey(e); return; }
  if ((e.ctrlKey || e.metaKey) && ['z', 'y'].includes(e.key.toLowerCase()) && S.mode === 'drawing') {
    if (e.target.matches('input, textarea, [contenteditable=true]')) return;
    e.preventDefault();
    serial(() => actions[e.key.toLowerCase() === 'y' || e.shiftKey ? 'redo' : 'undo']());
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && S.mode === 'drawing') {
    e.preventDefault();
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    setTimeout(() => serial(save), 0);
  }
  if (e.key === 'Enter' && e.target.matches('input[type=text]') && !e.target.closest('.overlay')) e.target.blur();
});

// ページ一覧のドラッグで並べ替え
let dragFrom = null;
function dropPlace(e) {
  const item = e.target.closest('.page-item[data-index]');
  if (!item) return null;
  const box = item.getBoundingClientRect();
  return { item, before: e.clientY < box.top + box.height / 2 };
}
function clearDropMarks() {
  document.querySelectorAll('.page-item.drop-before, .page-item.drop-after').forEach((el) => el.classList.remove('drop-before', 'drop-after'));
}
document.addEventListener('dragstart', (e) => {
  const item = e.target.closest && e.target.closest('.page-item[data-index]');
  if (!item) return;
  dragFrom = Number(item.dataset.index);
  item.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', String(dragFrom));
});
document.addEventListener('dragover', (e) => {
  if (dragFrom === null) return;
  const place = dropPlace(e);
  if (!place) return;
  e.preventDefault();
  clearDropMarks();
  place.item.classList.add(place.before ? 'drop-before' : 'drop-after');
});
document.addEventListener('dragend', () => {
  dragFrom = null;
  clearDropMarks();
  document.querySelectorAll('.page-item.dragging').forEach((el) => el.classList.remove('dragging'));
});
document.addEventListener('drop', (e) => {
  if (dragFrom === null) return;
  const place = dropPlace(e);
  const from = dragFrom;
  dragFrom = null;
  clearDropMarks();
  if (!place) return;
  e.preventDefault();
  let to = Number(place.item.dataset.index) + (place.before ? 0 : 1);
  if (from < to) to -= 1;
  if (to === from) return;
  serial(async () => {
    const result = await run('move_page_to', from, to);
    if (result) {
      const selected = S.index === null ? null : S.index === from ? result.index
        : S.index > from && S.index <= to ? S.index - 1 : S.index < from && S.index >= to ? S.index + 1 : S.index;
      await refreshAll(result, selected);
      setStatus(`${from + 1}ページ目を${to + 1}ページ目へ移しました`);
    }
  });
});

window.addEventListener('beforeunload', (e) => {
  if (window.BROWSER_MODE && S.snap && S.snap.dirty) { e.preventDefault(); e.returnValue = ''; }
});

(async function start() {
  S.meta = await call('meta');
  S.snap = await call('snapshot');
  if (!S.meta || S.meta.error || !S.snap || S.snap.error) {
    document.body.textContent = '起動できませんでした: ' + ((S.meta && S.meta.error) || (S.snap && S.snap.error) || '');
    return;
  }
  setMode('home');
  setStatus(S.meta.browser_paths ? 'ブラウザ確認モード: ファイルはパスを入力して指定します' : '');
})();
