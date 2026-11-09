// The municipality's page for a coordinator: the parts that depend on "my list". The page is rendered for the
// municipality's leading list; this redoes them for the list the reader picks, and keeps that choice in the
// browser (localStorage 'viewed'.lists[round id]) so the next municipality page opens on the same list. No
// framework; the markup rebuilt here mirrors municipality.html.
(function () {
  'use strict';
  const dataEl = document.getElementById('mun-data');
  const select = document.querySelector('[data-my-list]');
  if (!dataEl || !select) return;
  const data = JSON.parse(dataEl.textContent);
  const L = data.i18n;
  const sr = (document.documentElement.lang || 'sr').indexOf('en') !== 0;
  const mem = {
    read() { try { return JSON.parse(localStorage.getItem('viewed') || '{}'); } catch (e) { return {}; } },
    write(v) { try { localStorage.setItem('viewed', JSON.stringify(v)); } catch (e) { /* private window */ } },
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (x, d) => {
    const s = Math.abs(x).toFixed(d);
    const [a, b] = s.split('.');
    const grouped = a.replace(/\B(?=(\d{3})+(?!\d))/g, sr ? '.' : ',');
    return (x < 0 ? '−' : '') + grouped + (b ? (sr ? ',' : '.') + b : '');
  };
  const pct = (x, d) => num(100 * x, d === undefined ? 1 : d) + '%';
  const signed = (x, d) => (x >= 0 ? '+' : '') + num(x, d);
  const fill = (s, vals) => s.replace(/\{(\w+)\}/g, (m, k) => (k in vals ? vals[k] : m));

  function indexOf(number) {
    return data.lists.findIndex((l) => String(l.n) === String(number));
  }
  function ctrlOf(st, idx) {
    return st.ctrl ? st.ctrl[idx] : null; // 'm', 'd', 'n' or null when no decision was read
  }

  function renderWithout(idx) {
    const box = document.querySelector('[data-mine="without"]');
    if (!box) return;
    const without = data.stations.filter((st) => ctrlOf(st, idx) === 'n');
    const read = data.stations.filter((st) => ctrlOf(st, idx) !== null).length;
    const groups = new Map();
    without.forEach((st) => { const k = st.set || ''; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(st); });
    const ordered = [...groups.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
    const n = box.querySelector('.wk-n');
    n.innerHTML = esc(num(without.length, 0)) + '<small>' + esc(read ? fill(L.ofRead, { n: num(read, 0) }) : L.stations) + '</small>';
    n.classList.toggle('ok', without.length === 0);
    box.querySelector('.wk-rule').textContent = fill(L.rule3, { number: data.lists[idx].n });
    let list = box.querySelector('.wk-list');
    if (!list) { list = document.createElement('ul'); list.className = 'wk-list'; box.querySelector('.wk-rule').after(list); }
    list.innerHTML = ordered.slice(0, 5).map(([set, sts]) =>
      '<li><b>' + esc(set || data.name) + '</b> · ' + esc(L.stationNo) + ' ' + esc(sts.map((s) => s.n).join(', ')) + '</li>').join('');
    list.hidden = ordered.length === 0;
  }

  function renderChart(idx) {
    const box = document.querySelector('[data-mine="chart"]');
    if (!box) return;
    const counted = data.stations.filter((st) => st.valid);
    const totalVotes = counted.reduce((a, st) => a + (st.v[idx] || 0), 0);
    const totalValid = counted.reduce((a, st) => a + st.valid, 0);
    const avg = totalValid ? totalVotes / totalValid : 0;
    // one bar per station, the list's share from zero, strongest first; the line is the municipality's share
    const rows = counted.map((st) => ({ st, share: (st.v[idx] || 0) / st.valid })).sort((a, b) => b.share - a.share);
    const top = rows.length && rows[0].share ? rows[0].share : 0.01;
    const fold = rows.length > 12;
    const html = rows.map((r, k) => {
      const w = (100 * r.share / top).toFixed(1);
      const bar = '<i' + (r.share < avg ? ' class="neg"' : '') + ' style="width: ' + w + '%"></i>';
      const nc = ctrlOf(r.st, idx) === 'n' ? '<span class="nc" style="left: calc(' + w + '% + 4px)" title="' + esc(L.legendNc) + '"></span>' : '';
      const hidden = fold && k >= 6 && k < rows.length - 6;
      const more = fold && k === 5 ? '<button type="button" class="link-button dev-more" data-dev-more>' + esc(fill(L.rest, { n: num(rows.length - 12, 0) })) + '</button>' : '';
      return '<div class="dv' + (hidden ? ' dv-rest' : '') + '"><a class="lab" href="' + esc(r.st.href) + '"><b>' + esc(L.stationNo) + ' ' + esc(r.st.n) + '</b> ' + esc(r.st.set || r.st.name || '') + '</a><span class="ax">' + bar + nc + '</span><span class="val">' + esc(pct(r.share)) + ' <small class="muted">' + esc(signed(100 * (r.share - avg), 1)) + '</small></span></div>' + more;
    }).join('');
    const wrap = box.querySelector('[data-dev-rows]');
    const open = wrap.classList.contains('open');
    wrap.innerHTML = html;
    wrap.style.setProperty('--avg', (100 * avg / top).toFixed(1) + '%');
    wrap.classList.toggle('open', open);
    const note = box.querySelector('[data-dev-note]');
    if (note) note.textContent = fill(L.devNote, { avg: pct(avg) });
  }

  function renderTable(idx) {
    document.querySelectorAll('#station-list tr[data-bm]').forEach((tr) => {
      const st = data.stations.find((s) => String(s.n) === tr.dataset.bm);
      if (!st) return;
      const share = tr.querySelector('[data-cell="share"]');
      if (share) share.textContent = st.valid ? pct((st.v[idx] || 0) / st.valid) : '';
      const cell = tr.querySelector('[data-cell="ctrl"]');
      if (cell) {
        const c = ctrlOf(st, idx);
        cell.textContent = c === 'm' ? L.member : c === 'd' ? L.deputy : c === 'n' ? L.none : L.notRead;
        cell.className = c === 'n' ? 'ctrl-none' : c ? 'ctrl-yes' : 'muted';
      }
    });
  }

  function renderVillages(idx) {
    document.querySelectorAll('#village-list tr[data-set]').forEach((tr) => {
      const cell = tr.querySelector('[data-cell="vshare"]');
      if (!cell) return;
      const sts = data.stations.filter((st) => (st.set || '') === tr.dataset.set && st.valid);
      const valid = sts.reduce((a, st) => a + st.valid, 0);
      cell.textContent = valid ? pct(sts.reduce((a, st) => a + (st.v[idx] || 0), 0) / valid) : '';
    });
  }

  function apply(idx) {
    renderWithout(idx);
    renderChart(idx);
    renderTable(idx);
    renderVillages(idx);
    renderPanel(idx);
  }

  // a click on a settlement of the map: its polling stations under the map (link, turnout, my list, controller)
  const panel = document.querySelector('[data-village-panel]');
  const mainFig = document.querySelector('[data-map-main]');
  const smap = mainFig ? mainFig.querySelector('svg.smap') : null;
  let shownSet = null;
  function renderPanel(idx) {
    if (!panel || shownSet === null) return;
    const sts = data.stations.filter((st) => (st.set || '') === shownSet);
    const row = (st) => {
      const c = ctrlOf(st, idx);
      const ctrl = c === 'm' ? L.member : c === 'd' ? L.deputy : c === 'n' ? L.none : L.notRead;
      return '<tr><td><a href="' + esc(st.href) + '"><b>' + esc(L.stationNo) + ' ' + esc(st.n) + '</b> ' + esc(st.name || '') + '</a></td>'
        + '<td class="num">' + (st.turnout === null ? '' : esc(pct(st.turnout))) + '</td>'
        + '<td class="num">' + (st.valid ? esc(pct((st.v[idx] || 0) / st.valid)) : '') + '</td>'
        + '<td class="' + (c === 'n' ? 'ctrl-none' : c ? 'ctrl-yes' : 'muted') + '">' + esc(ctrl) + '</td></tr>';
    };
    panel.innerHTML = '<div class="vi-panel-head"><strong>' + esc(fill(L.panelTitle, { name: shownSet, n: num(sts.length, 0) })) + '</strong>'
      + '<button type="button" class="link-button" data-panel-close>' + esc(L.panelClose) + '</button></div>'
      + '<table class="compact"><thead><tr><th>' + esc(L.station) + '</th><th class="num">' + esc(L.turnout) + '</th><th class="num">' + esc(L.myList) + '</th><th>' + esc(L.controller) + '</th></tr></thead><tbody>'
      + sts.map(row).join('') + '</tbody></table>';
    panel.hidden = false;
  }
  const clearActive = () => document.querySelectorAll('svg.smap .mp-active').forEach((x) => x.classList.remove('mp-active'));
  const closePanel = () => { shownSet = null; if (panel) panel.hidden = true; clearActive(); };
  function wire(map) {
    map.querySelectorAll('path[data-set]').forEach((p) => { if (p.dataset.set) { p.setAttribute('tabindex', '0'); p.setAttribute('role', 'button'); } });
    const pick = (p) => {
      // the city settlement with a page of its own by quarters (Novi Sad): the click opens that page
      if (mainFig.dataset.city && p.dataset.set === mainFig.dataset.city) { location.href = mainFig.dataset.cityHref; return; }
      clearActive();
      if (shownSet === p.dataset.set) { closePanel(); return; }
      shownSet = p.dataset.set; p.classList.add('mp-active');
      renderPanel(indexOf(select.value));
    };
    map.addEventListener('click', (e) => { const p = e.target.closest('path[data-set]'); if (p && p.dataset.set) pick(p); });
    map.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { const p = e.target.closest('path[data-set]'); if (p && p.dataset.set) { e.preventDefault(); pick(p); } } });
  }
  if (smap && panel) {
    wire(smap);
    panel.addEventListener('click', (e) => { if (e.target.closest('[data-panel-close]')) closePanel(); });
    const hint = document.createElement('p'); hint.className = 'small muted vi-hint'; hint.textContent = L.panelHint; panel.before(hint);
  }

  document.addEventListener('click', (e) => {
    const more = e.target.closest('[data-dev-more]');
    if (!more) return;
    more.closest('[data-dev-rows]').classList.add('open');
    more.remove();
  });

  // the map as a PNG (static/mapimg.js), from the page's own data: per settlement (or quarter) and in all
  const units = new Map();
  const total = { valid: 0, v: data.lists.map(() => 0) };
  data.stations.forEach((st) => {
    if (!st.valid) return;
    total.valid += st.valid; st.v.forEach((x, i) => { total.v[i] += x || 0; });
    if (!st.set) return;
    const g = units.get(st.set) || { name: st.set, reg: 0, valid: 0, v: data.lists.map(() => 0) };
    g.reg += st.reg; g.valid += st.valid; st.v.forEach((x, i) => { g.v[i] += x || 0; }); units.set(st.set, g);
  });
  const heading = document.querySelector('.villages .sec-head h2');
  if (window.mapImage) {
    document.querySelectorAll('figure.smap-wrap').forEach((fig) => window.mapImage(fig, {
      lists: data.lists, total, units: [...units.values()], L, heading: heading ? heading.textContent : '' }));
  }

  // the remembered list, when this election has it
  const remembered = (mem.read().lists || {})[data.rid];
  let idx = remembered !== undefined ? indexOf(remembered) : -1;
  if (idx < 0) idx = data.default;
  if (idx !== data.default) { select.value = String(data.lists[idx].n); apply(idx); }

  select.addEventListener('change', () => {
    const i = indexOf(select.value);
    if (i < 0) return;
    const v = mem.read();
    v.lists = v.lists || {};
    v.lists[data.rid] = data.lists[i].n;
    mem.write(v);
    apply(i);
  });
})();
