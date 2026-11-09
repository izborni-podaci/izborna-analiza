// The city's page: a click on a municipality of the map lists its polling stations under the map, from the page's
// own JSON (#city-data): number, name, turnout, warnings, each a link to the station's page. Nothing is sent anywhere.
(() => {
  const dataEl = document.getElementById('city-data');
  const panel = document.querySelector('[data-city-panel]');
  const smap = document.querySelector('svg.smap');
  if (!dataEl || !panel || !smap) return;
  const data = JSON.parse(dataEl.textContent);
  const L = data.i18n;
  const sr = (document.documentElement.lang || 'sr').indexOf('en') !== 0;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (x, d) => { const s = Math.abs(x).toFixed(d); const [a, b] = s.split('.'); return (x < 0 ? '−' : '') + a.replace(/\B(?=(\d{3})+(?!\d))/g, sr ? '.' : ',') + (b ? (sr ? ',' : '.') + b : ''); };
  const pct = (x) => num(100 * x, 1) + '%';
  const fill = (s, v) => s.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));
  const FIRST = 30;
  let shown = null;
  const render = (label, all) => {
    const m = data.muns[label];
    if (!m) return;
    const rows = all ? m.stations : m.stations.slice(0, FIRST);
    const row = (st) => '<tr><td><a href="' + esc(st[4]) + '"><b>' + esc(L.stationNo) + ' ' + esc(st[0]) + '</b> ' + esc(st[1] || '') + '</a></td>'
      + '<td class="num">' + (st[2] === null ? '' : esc(pct(st[2]))) + '</td><td class="num">' + (st[3] ? esc(num(st[3], 0)) : '—') + '</td></tr>';
    panel.innerHTML = '<div class="vi-panel-head"><strong>' + esc(fill(L.title, { name: m.name, n: num(m.stations.length, 0) })) + '</strong>'
      + '<span><a href="' + esc(m.href) + '">' + esc(L.page) + '</a> · <button type="button" class="link-button" data-panel-close>' + esc(L.close) + '</button></span></div>'
      + '<table class="compact"><thead><tr><th>' + esc(L.station) + '</th><th class="num">' + esc(L.turnout) + '</th><th class="num">' + esc(L.flags) + '</th></tr></thead><tbody>'
      + rows.map(row).join('') + '</tbody></table>'
      + (m.stations.length > rows.length ? '<button type="button" class="link-button dev-more" data-panel-more>' + esc(fill(L.more, { n: num(m.stations.length - rows.length, 0) })) + '</button>' : '');
    panel.hidden = false;
  };
  smap.querySelectorAll('path[data-set]').forEach((p) => { if (p.dataset.set) { p.setAttribute('tabindex', '0'); p.setAttribute('role', 'button'); } });
  const pick = (p) => {
    smap.querySelectorAll('.mp-active').forEach((x) => x.classList.remove('mp-active'));
    if (shown === p.dataset.set) { shown = null; panel.hidden = true; return; }
    shown = p.dataset.set; p.classList.add('mp-active'); render(shown, false);
  };
  smap.addEventListener('click', (e) => { const p = e.target.closest('path[data-set]'); if (p && p.dataset.set) pick(p); });
  smap.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { const p = e.target.closest('path[data-set]'); if (p && p.dataset.set) { e.preventDefault(); pick(p); } } });
  panel.addEventListener('click', (e) => {
    if (e.target.closest('[data-panel-close]')) { shown = null; panel.hidden = true; smap.querySelectorAll('.mp-active').forEach((x) => x.classList.remove('mp-active')); }
    if (e.target.closest('[data-panel-more]') && shown) render(shown, true);
  });
  const hint = document.createElement('p'); hint.className = 'small muted vi-hint'; hint.textContent = L.hint; panel.before(hint);
  // the map as a PNG (static/mapimg.js), the municipalities as its places
  const fig = smap.closest('figure');
  if (window.mapImage && fig) {
    const units = Object.keys(data.muns).map((k) => ({ name: k, reg: data.muns[k].reg, valid: data.muns[k].valid, v: data.muns[k].v }));
    const total = { valid: units.reduce((a, u) => a + u.valid, 0), v: data.lists.map((_, i) => units.reduce((a, u) => a + (u.v[i] || 0), 0)) };
    const h = document.querySelector('#mapa .sec-head h2');
    window.mapImage(fig, { lists: data.lists, total, units, L, heading: h ? h.textContent : '' });
  }
})();
