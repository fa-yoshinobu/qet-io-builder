'use strict';
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
  'home-terminals'() { setMode('terminals'); },
  async 'generate-terminal-block'() {
    const model = $('#terminal-model').value;
    const path = await pathFor('I/O図・中継端子台図の保存先（.qet）', model + '.qet');
    if (path === null) return;
    const extra = {};
    if (!$('#terminal-start').hidden) extra.start = $('#terminal-start').value.trim();
    if (!$('#terminal-block-tag2').hidden) extra.tag2 = $('#terminal-block-tag2').value.trim();
    if (!$('#terminal-cable2').hidden) {
      extra.cable2 = $('#terminal-cable2').value;
      extra.cable_tag2 = $('#terminal-cable-tag2').value.trim();
    }
    const result = await run('generate_terminal_block', model, $('#terminal-plc').value, $('#terminal-cable').value,
      $('#terminal-plc-tag').value.trim(), $('#terminal-block-tag').value.trim(), $('#terminal-cable-tag').value.trim(), path, extra);
    if (result) setStatus('図面を生成しました: ' + result.out);
  },
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
