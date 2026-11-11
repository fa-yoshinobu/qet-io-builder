'use strict';
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
