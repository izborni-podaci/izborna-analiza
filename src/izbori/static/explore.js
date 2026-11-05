/* Istraži (Explore): the reader's own analyses, computed in the browser from the numbers RIK published, polling
   station by polling station. The same measures for every list, and no list is chosen for the reader. No libraries
   and nothing from third parties: the stations come from api/r/<id>/stations.json and the municipal boundaries from
   api/geo/municipalities.json, both on this site. Every analysis lives in the address (#v=…&r=…), so a link opens it
   again; the strings come with the page, in its language. */
(() => {
  'use strict';

  const box = document.querySelector('[data-explore]');
  const metaEl = document.getElementById('ex-meta');
  if (!box || !metaEl) return;
  let META;
  try { META = JSON.parse(metaEl.textContent); } catch (e) { return; }
  if (!META.rounds || !META.rounds.length) return;
  box.hidden = false;

  const T = META.t || {};
  const LOC = META.loc;
  const ROOT = box.dataset.root || '';
  const SITE = box.dataset.site || '';
  const ROUNDS = META.rounds; // newest first
  const BY_ID = Object.fromEntries(ROUNDS.map((r) => [r.id, r]));
  const GROUPS = META.groups || [];
  const VIEWS = ['map', 'density', 'compare', 'hist', 'table', 'matrix'];
  const TOP = 200; // rows shown before "show all"
  const form = box.querySelector('[data-form]');
  const out = box.querySelector('[data-out]');
  const msg = box.querySelector('[data-msg]');
  const sum = box.querySelector('[data-sum]');
  const listEl = box.querySelector('[data-list]');
  const copied = box.querySelector('[data-copied]');
  const btnCsv = box.querySelector('[data-csv]');
  const btnSvg = box.querySelector('[data-svg]');
  const filtersEl = box.querySelector('[data-filters]');
  const presetsEl = box.querySelector('[data-presets]');
  const moreEl = box.querySelector('[data-more]');

  // --- words and numbers ------------------------------------------------------------------------------------------
  const t = (k, vars) => String(T[k] ?? k).replace(/\{(\w+)\}/g, (m, v) => (vars && vars[v] != null ? vars[v] : m));
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const SEP = LOC === 'en' ? [',', '.'] : ['.', ','];
  const num = (x, d = 0) => {
    if (x == null || !Number.isFinite(x)) return '—';
    const s = Math.abs(x).toFixed(d);
    const neg = x < 0 && Number(s) !== 0;
    const [i, f] = s.split('.');
    return (neg ? '−' : '') + i.replace(/\B(?=(\d{3})+(?!\d))/g, SEP[0]) + (f ? SEP[1] + f : '');
  };
  const signed = (x, d = 1) => (x > 0 && Number(x.toFixed(d)) !== 0 ? '+' : '') + num(x, d);
  const coll = new Intl.Collator(LOC === 'cyr' ? 'sr-Cyrl' : 'sr-Latn');
  const cut = (s, n = 64) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

  // Serbian Cyrillic to Latin, as the site's own pages do it: api/ keeps the stations' names as RIK wrote them.
  const CYR = {
    А: 'A', Б: 'B', В: 'V', Г: 'G', Д: 'D', Ђ: 'Đ', Е: 'E', Ж: 'Ž', З: 'Z', И: 'I', Ј: 'J', К: 'K', Л: 'L',
    Љ: 'Lj', М: 'M', Н: 'N', Њ: 'Nj', О: 'O', П: 'P', Р: 'R', С: 'S', Т: 'T', Ћ: 'Ć', У: 'U', Ф: 'F', Х: 'H',
    Ц: 'C', Ч: 'Č', Џ: 'Dž', Ш: 'Š', І: 'I', Ї: 'I', Є: 'E', Ґ: 'G', Й: 'J', Ы: 'Y', Э: 'E', Ё: 'E', Ў: 'U',
    Ю: 'Ju', Я: 'Ja', Щ: 'Šč', Ъ: '', Ь: '',
  };
  const isUp = (c) => !!c && c !== c.toLowerCase() && c === c.toUpperCase();
  const isLetter = (c) => !!c && c.toLowerCase() !== c.toUpperCase();
  const latin = (s) => {
    const ch = [...String(s || '')];
    return ch.map((c, i) => {
      const up = c.toUpperCase();
      const m = CYR[up];
      if (m === undefined) return c;
      if (c !== up) return m.toLowerCase();
      if (m.length < 2) return m;
      // Lj, Nj, Dž: all capitals inside a word in capitals
      const caps = isLetter(ch[i + 1]) ? isUp(ch[i + 1]) : isUp(ch[i - 1]);
      return caps ? m.toUpperCase() : m;
    }).join('');
  };
  const own = LOC === 'cyr' ? (s) => s || '' : latin;

  // --- measures ---------------------------------------------------------------------------------------------------
  // pct: a share, shown in per cent; for a municipality its stations' numerators over their denominators. count: a
  // number, added up. yes: a station has it or hasn't; for a municipality, the per cent of its stations that have it.
  // list: the measure needs a list, which the reader chooses.
  const M = {
    turnout: { kind: 'pct' },
    invalid: { kind: 'pct' },
    share: { kind: 'pct', list: true },
    top: { kind: 'pct' },
    reg: { kind: 'count' },
    voted: { kind: 'count' },
    gap: { kind: 'count' },
    flagged: { kind: 'yes' },
    ctrl: { kind: 'yes', list: true },
    obs: { kind: 'yes' },
  };
  const MKEYS = Object.keys(M);
  const unit = (key, lv) => (M[key].kind === 'yes' && lv === 'm' ? 'pct' : M[key].kind);
  const listIx = (d, n) => (n === '' || n == null || !d ? -1 : d.contestants.findIndex((c) => String(c.n) === String(n)));

  // a station's measure as [numerator, denominator] (0 for a count); null where RIK's numbers don't give it
  const parts = (key, d, i, li) => {
    const s = d.stations;
    switch (key) {
      case 'turnout': return s.reg[i] ? [s.voted[i] ?? 0, s.reg[i]] : null;
      case 'invalid': {
        const base = s.box[i] || s.voted[i];
        return base && s.invalid[i] != null ? [s.invalid[i], base] : null;
      }
      case 'share': return li >= 0 && s.valid[i] ? [d.votes[li][i] ?? 0, s.valid[i]] : null;
      case 'top': {
        if (!s.valid[i]) return null;
        let most = 0;
        for (const col of d.votes) if ((col[i] ?? 0) > most) most = col[i];
        return [most, s.valid[i]];
      }
      case 'reg': return s.reg[i] == null ? null : [s.reg[i], 0];
      case 'voted': return s.voted[i] == null ? null : [s.voted[i], 0];
      case 'gap': return s.voted[i] == null || s.box[i] == null ? null : [s.voted[i] - s.box[i], 0];
      case 'flagged': return [s.flags[i] > 0 ? 1 : 0, 1];
      case 'ctrl': {
        const c = s.ctrl[i];
        const n = li >= 0 ? d.contestants[li].n : 0;
        return c == null || !(n > 0 && n <= 31) ? null : [(c >>> (n - 1)) & 1, 1];
      }
      case 'obs': return [s.obs[i] ? 1 : 0, 1];
      default: return null;
    }
  };
  const sval = (key, d, i, li) => {
    const p = parts(key, d, i, li);
    if (!p) return null;
    if (M[key].kind !== 'pct') return p[0];
    return p[1] ? (100 * p[0]) / p[1] : null;
  };
  const gval = (key, d, idx, li) => {
    if (key === 'top') { // the list with most votes in the whole municipality, whichever it is
      let valid = 0;
      const tot = d.votes.map(() => 0);
      for (const i of idx) {
        if (!d.stations.valid[i]) continue;
        valid += d.stations.valid[i];
        d.votes.forEach((col, j) => { tot[j] += col[i] ?? 0; });
      }
      return valid ? (100 * Math.max(...tot)) / valid : null;
    }
    let a = 0;
    let b = 0;
    let any = false;
    for (const i of idx) {
      const p = parts(key, d, i, li);
      if (!p) continue;
      any = true;
      a += p[0];
      b += p[1];
    }
    if (!any) return null;
    if (M[key].kind === 'count') return a;
    return b ? (100 * a) / b : null;
  };
  const fmt = (u, v) => {
    if (v == null) return '—';
    if (u === 'pct') return `${num(v, 1)}%`;
    if (u === 'yes') return t(v ? 'ex_true' : 'ex_false');
    return num(v, 0);
  };
  const csvNum = (u, v) => (v == null ? '' : u === 'pct' ? Number(v.toFixed(2)) : v);
  const listName = (rid, n) => {
    const l = ((BY_ID[rid] || {}).lists || []).find((x) => String(x.n) === String(n));
    return l ? `${l.n}. ${l.name}` : '';
  };
  const mlabel = (key, rid, n) => (M[key].list && n ? `${t(`m_${key}`)}: ${listName(rid, n)}` : t(`m_${key}`));
  const withUnit = (label, u) => (u === 'pct' ? `${label} (%)` : label);

  // --- numbers for scales -----------------------------------------------------------------------------------------
  const quantile = (sorted, q) => {
    if (!sorted.length) return null;
    const pos = (sorted.length - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  };
  const sorted = (vals) => vals.filter((v) => v != null && Number.isFinite(v)).sort((a, b) => a - b);
  const median = (vals) => quantile(sorted(vals), 0.5);
  const niceStep = (raw) => {
    if (!(raw > 0)) return 1;
    const p = 10 ** Math.floor(Math.log10(raw));
    const f = raw / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  };
  const niceDomain = (lo, hi, n = 5) => {
    if (!(hi - lo > 1e-9)) { lo -= 1; hi += 1; }
    const s = niceStep((hi - lo) / n);
    return [Math.floor(lo / s + 1e-9) * s, Math.ceil(hi / s - 1e-9) * s];
  };
  const ticks = (lo, hi, n = 5) => {
    const s = niceStep((hi - lo) / n);
    const out = [];
    for (let v = Math.ceil(lo / s - 1e-9) * s; v <= hi + s * 1e-6; v += s) out.push(Number(v.toFixed(10)));
    return { list: out, step: s };
  };
  const digits = (step) => { // as many decimals as the step has, so 2.5 isn't shown as 3
    for (let d = 0; d < 3; d += 1) if (Math.abs(step * 10 ** d - Math.round(step * 10 ** d)) < 1e-6) return d;
    return 3;
  };
  const extent = (vals) => {
    let lo = Infinity;
    let hi = -Infinity;
    for (const v of vals) { if (v < lo) lo = v; if (v > hi) hi = v; }
    return [lo, hi];
  };
  const pearson = (pairs) => {
    const n = pairs.length;
    if (n < 3) return null;
    let sx = 0; let sy = 0;
    for (const [x, y] of pairs) { sx += x; sy += y; }
    const mx = sx / n; const my = sy / n;
    let cxy = 0; let cxx = 0; let cyy = 0;
    for (const [x, y] of pairs) { cxy += (x - mx) * (y - my); cxx += (x - mx) ** 2; cyy += (y - my) ** 2; }
    return cxx && cyy ? cxy / Math.sqrt(cxx * cyy) : null;
  };

  // --- colours, from the theme, so a downloaded picture looks as the page does --------------------------------------
  let C = {};
  const colors = () => {
    const cs = getComputedStyle(document.documentElement);
    const get = (n, f) => { const v = cs.getPropertyValue(n).trim(); return /^#[0-9a-f]{6}$/i.test(v) ? v : f; };
    C = {
      page: get('--page', '#ffffff'), ink: get('--ink', '#161616'), ink2: get('--ink-2', '#555555'),
      grid: get('--grid', '#e4e4e0'), axis: get('--axis', '#c8c8c2'), accent: get('--accent', '#c2410c'),
    };
  };
  const rgb = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
  const mix = (f) => { // from the page's colour (0) to the accent (1)
    const a = rgb(C.page);
    const b = rgb(C.accent);
    return `#${a.map((x, i) => Math.round(x + (b[i] - x) * Math.max(0, Math.min(1, f))).toString(16).padStart(2, '0')).join('')}`;
  };
  // a heat scale between the 2nd and 98th percentiles, so that one outlier doesn't wash out the rest
  const heat = (vals, strength = 0.55) => {
    const s = sorted(vals);
    if (!s.length) return () => '';
    let lo = quantile(s, 0.02);
    let hi = quantile(s, 0.98);
    if (!(hi - lo > 1e-9)) { lo = s[0]; hi = s[s.length - 1]; }
    return (v) => {
      if (v == null) return '';
      const f = hi - lo > 1e-9 ? (v - lo) / (hi - lo) : 0.5;
      return mix(0.06 + strength * Math.max(0, Math.min(1, f)));
    };
  };
  // classes for the map: equal steps at round numbers across the 2nd to 98th percentile of the municipalities drawn,
  // five to eight of them; the end ones are open
  const classes = (vals) => {
    const s = sorted(vals);
    if (!s.length) return { breaks: [], step: 1, color: (v) => (v == null ? C.grid : mix(0.6)) };
    let lo = quantile(s, 0.02);
    let hi = quantile(s, 0.98);
    if (!(hi - lo > 1e-9)) { lo = s[0]; hi = s[s.length - 1]; }
    if (!(hi - lo > 1e-9)) return { breaks: [], step: 1, color: (v) => (v == null ? C.grid : mix(0.6)) };
    const step = niceStep((hi - lo) / 7);
    const start = Math.floor(lo / step + 1e-9) * step;
    const n = Math.max(5, Math.min(8, Math.ceil((hi - start) / step - 1e-9)));
    const breaks = [];
    for (let k = 1; k < n; k++) breaks.push(Number((start + k * step).toFixed(10)));
    const color = (v) => {
      if (v == null) return C.grid;
      let c = 0;
      while (c < breaks.length && v >= breaks[c]) c += 1;
      return mix(0.14 + (0.86 * c) / breaks.length);
    };
    return { breaks, step, color };
  };

  // --- the state, in the address ----------------------------------------------------------------------------------
  const DEF = {
    v: 'map', r: ROUNDS[0].id, r2: '', lv: 's', x: 'turnout', lx: '', y: 'top', ly: '', mun: '', k: 'd', min: '',
    fl: '', cl: '', cv: 'yes', ob: '', x0: '', x1: '', o: '',
  };
  const KEYS = Object.keys(DEF);
  const ALWAYS = ['v', 'r', 'x'];
  const clean = (s) => {
    if (!VIEWS.includes(s.v)) s.v = DEF.v;
    if (!BY_ID[s.r]) s.r = DEF.r;
    if (s.r2 && (!BY_ID[s.r2] || s.r2 === s.r)) s.r2 = '';
    if (!['s', 'm'].includes(s.lv)) s.lv = DEF.lv;
    if (!M[s.x]) s.x = DEF.x;
    if (!M[s.y]) s.y = DEF.y;
    if (!['d', 'a', 'p', 'all'].includes(s.k)) s.k = DEF.k;
    if (!['', 'any', 'none', ...GROUPS.map((g) => `g:${g}`)].includes(s.fl)) s.fl = '';
    if (!['yes', 'no'].includes(s.cv)) s.cv = DEF.cv;
    if (!['', 'yes', 'no'].includes(s.ob)) s.ob = '';
    ['min', 'x0', 'x1'].forEach((k) => { if (s[k] !== '' && !Number.isFinite(Number(s[k]))) s[k] = ''; });
    return s;
  };
  const fromHash = () => {
    const p = new URLSearchParams(location.hash.replace(/^#/, ''));
    const s = { ...DEF };
    KEYS.forEach((k) => { if (p.has(k)) s[k] = p.get(k).trim(); });
    return clean(s);
  };
  const toHash = (s) => {
    const p = new URLSearchParams();
    KEYS.forEach((k) => { if (ALWAYS.includes(k) || (s[k] !== '' && s[k] !== DEF[k])) p.set(k, s[k]); });
    return `#${p.toString()}`;
  };
  let st = fromHash();
  const level = () => (st.v === 'map' || st.v === 'matrix' ? 'm' : st.lv);
  const later = (a, b) => { // is election a after election b? On the same day, the one RIK listed later
    const da = BY_ID[a].date || '';
    const db = BY_ID[b].date || '';
    return da !== db ? da > db : ROUNDS.indexOf(BY_ID[a]) < ROUNDS.indexOf(BY_ID[b]);
  };
  const previous = (rid) => { // the election before this one, of the same kind if there is one
    const older = ROUNDS.filter((r) => r.id !== rid && later(rid, r.id));
    return (older.find((r) => r.kind === BY_ID[rid].kind) || older[0] || ROUNDS.find((r) => r.id !== rid) || {}).id || '';
  };

  // --- the form ---------------------------------------------------------------------------------------------------
  const field = (n) => form.querySelector(`[name="${n}"]`);
  const show = (n, on) => box.querySelectorAll(`[data-for="${n}"]`).forEach((el) => { el.hidden = !on; });
  const fill = (n, items, value) => {
    const sel = field(n);
    sel.textContent = '';
    for (const [v, label, title] of items) {
      const o = document.createElement('option');
      o.value = v;
      o.textContent = label;
      if (title) o.title = title;
      sel.append(o);
    }
    sel.value = items.some(([v]) => v === value) ? value : (items[0] || [''])[0];
    return sel.value;
  };
  const listItems = (rid) => [['', t('ex_pick_list')],
    ...((BY_ID[rid] || {}).lists || []).map((l) => [String(l.n), cut(`${l.n}. ${l.name}`), `${l.n}. ${l.name}`])];
  const allowed = (v, lv) => MKEYS.filter((k) => {
    if (v === 'matrix') return !M[k].list; // lists change from one election to the next
    if (v === 'map' || v === 'table' || lv === 'm') return true;
    return M[k].kind !== 'yes'; // a station has it or hasn't: nothing to spread along an axis
  });
  let munItems = null; // the municipalities of the loaded elections, once known
  const syncForm = () => {
    const v = st.v;
    const lv = level();
    fill('v', VIEWS.map((k) => [k, t(`view_${k}`)]), v);
    show('r', v !== 'matrix');
    st.r = fill('r', ROUNDS.map((r) => [r.id, r.short]), st.r);
    show('r2', v === 'compare');
    if (v === 'compare') {
      st.r2 = fill('r2', [['', t('ex_none')], ...ROUNDS.filter((r) => r.id !== st.r).map((r) => [r.id, r.short])], st.r2);
    }
    show('lv', v !== 'map' && v !== 'matrix');
    fill('lv', [['s', t('level_s')], ['m', t('level_m')]], st.lv);
    const ms = allowed(v, lv);
    if (!ms.includes(st.x)) st.x = ms[0];
    if (!ms.includes(st.y)) st.y = ms.includes('top') ? 'top' : ms[0];
    st.x = fill('x', ms.map((k) => [k, t(`m_${k}`)]), st.x);
    show('lx', M[st.x].list && v !== 'matrix');
    if (M[st.x].list) st.lx = fill('lx', listItems(st.r), st.lx);
    show('y', v === 'density');
    if (v === 'density') st.y = fill('y', ms.map((k) => [k, t(`m_${k}`)]), st.y);
    const yList = v === 'density' ? M[st.y].list : v === 'compare' && M[st.x].list;
    show('ly', yList);
    if (yList) {
      const rid = v === 'compare' ? st.r2 : st.r;
      st.ly = fill('ly', rid ? listItems(rid) : [['', t('ex_pick_list')]], st.ly);
      const lab = form.querySelector('[data-for="ly"]');
      lab.firstChild.textContent = v === 'compare' && rid ? `${t('ex_list')} · ${BY_ID[rid].short}` : t('ex_list');
    }
    const lxLab = form.querySelector('[data-for="lx"]');
    lxLab.firstChild.textContent = v === 'compare' ? `${t('ex_list')} · ${BY_ID[st.r].short}` : t('ex_list');
    // which stations
    const mi = munItems || (st.mun ? [[st.mun, META.muns[st.mun] || st.mun]] : []);
    fill('mun', [['', t('ex_all')], ...mi], st.mun);
    fill('k', ['d', 'a', 'p', 'all'].map((k) => [k, t(`ex_kind_${k}`)]), st.k);
    st.fl = fill('fl', [['', t('ex_all')], ['any', t('ex_flags_any')], ['none', t('ex_flags_none')],
      ...GROUPS.map((g) => [`g:${g}`, t(`group_${g}`)])], st.fl);
    st.cl = fill('cl', [['', t('ex_all')], ...listItems(st.r).slice(1)], st.cl);
    show('cl', v !== 'matrix'); // the lists are one election's
    show('cv', !!st.cl && v !== 'matrix');
    fill('cv', [['yes', t('ex_ctrl_yes')], ['no', t('ex_ctrl_no')]], st.cv);
    fill('ob', [['', t('ex_all')], ['yes', t('ex_yes')], ['no', t('ex_no')]], st.ob);
    field('min').value = st.min;
    show('x0', v !== 'compare' && v !== 'matrix' && unit(st.x, lv) !== 'yes');
    field('x0').value = st.x0;
    field('x1').value = st.x1;
    if (st.mun || st.k !== 'd' || st.min || st.fl || st.cl || st.ob || st.x0 || st.x1) filtersEl.open = true;
  };

  // --- the data ---------------------------------------------------------------------------------------------------
  const DATA = {};
  const loading = {};
  const load = (rid) => {
    if (DATA[rid]) return Promise.resolve(DATA[rid]);
    if (!loading[rid]) {
      loading[rid] = fetch(`${ROOT}api/r/${encodeURIComponent(rid)}/stations.json`)
        .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
        .then((d) => { DATA[rid] = d; return d; })
        .finally(() => { delete loading[rid]; });
    }
    return loading[rid];
  };
  let GEO;
  let geoLoading = null;
  const loadGeo = () => {
    if (GEO !== undefined) return Promise.resolve(GEO);
    geoLoading = geoLoading || fetch(`${ROOT}api/geo/municipalities.json`)
      .then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((g) => { GEO = g; return g; });
    return geoLoading;
  };
  const munName = (code, d) => META.muns[code] || (d && d.municipalities[code] ? own(d.municipalities[code]) : code);
  const munHref = (code) => `${SITE}m/${encodeURIComponent(code)}.html`;
  const stHref = (d, i) => {
    const p = d.stations.place[i];
    return p ? `${SITE}s/${encodeURIComponent(p)}.html` : `${SITE}r/${d.id}/m/${encodeURIComponent(d.stations.mc[i])}.html`;
  };
  const stName = (d, i) => own(d.stations.name[i]) || `${t('ex_col_no')} ${d.stations.no[i]}`;

  // Which stations: the filters apply to each election's own stations; the controller filter only to the chosen
  // election, whose lists it names.
  const keeper = (d, rid) => {
    const s = d.stations;
    const minReg = Number(st.min) || 0;
    const gi = st.fl.startsWith('g:') ? GROUPS.indexOf(st.fl.slice(2)) : -1;
    const gbit = gi >= 0 ? 1 << gi : 0;
    const cn = st.v !== 'matrix' && rid === st.r && st.cl ? Number(st.cl) : 0;
    return (i) => {
      const mc = s.mc[i];
      if (st.k === 'd' && (mc === META.abroad || mc === META.prisons)) return false;
      if (st.k === 'a' && mc !== META.abroad) return false;
      if (st.k === 'p' && mc !== META.prisons) return false;
      if (st.mun && mc !== st.mun) return false;
      if (minReg && !(s.reg[i] >= minReg)) return false;
      if (st.fl === 'any' && !s.flags[i]) return false;
      if (st.fl === 'none' && s.flags[i]) return false;
      if (gbit && !(s.groups[i] & gbit)) return false;
      if (cn) {
        const c = s.ctrl[i];
        if (c == null || !(cn > 0 && cn <= 31)) return false;
        const has = (c >>> (cn - 1)) & 1;
        if (st.cv === 'no' ? has : !has) return false;
      }
      if (st.ob === 'yes' && !s.obs[i]) return false;
      if (st.ob === 'no' && s.obs[i]) return false;
      return true;
    };
  };
  const kept = (d, rid) => {
    const keep = keeper(d, rid);
    const idx = [];
    for (let i = 0; i < d.stations.mc.length; i += 1) if (keep(i)) idx.push(i);
    return idx;
  };
  const byMun = (d, idx) => {
    const g = new Map();
    for (const i of idx) {
      const c = d.stations.mc[i];
      if (!g.has(c)) g.set(c, []);
      g.get(c).push(i);
    }
    return g;
  };
  const rowsOf = (d, idx, lv, key, li) => (lv === 's'
    ? idx.map((i) => ({ id: `s${i}`, d, i, code: d.stations.mc[i], value: sval(key, d, i, li) }))
    : [...byMun(d, idx)].map(([code, ix]) => ({ id: `m${code}`, d, code, idx: ix, value: gval(key, d, ix, li) })));
  const ranged = (u) => {
    if (u === 'yes' || (st.x0 === '' && st.x1 === '')) return () => true;
    const a = st.x0 === '' ? -Infinity : Number(st.x0);
    const b = st.x1 === '' ? Infinity : Number(st.x1);
    return (r) => r.value != null && r.value >= a && r.value <= b;
  };
  const byValue = (asc) => (p, q) => {
    if (p.value == null || q.value == null) return (p.value == null) - (q.value == null);
    return asc ? p.value - q.value : q.value - p.value;
  };

  // --- tables -----------------------------------------------------------------------------------------------------
  // cols: [{h, num, sort, get(row) -> text or {t, href, bg}}]
  const tableEl = (cols, rows, { limit = TOP, sortCol = -1, asc = false, onSort = null, cls = '' } = {}) => {
    const wrap = document.createElement('div');
    const cell = (c, r) => {
      const v = c.get(r);
      const o = v && typeof v === 'object' ? v : { t: v };
      const inner = o.href ? `<a href="${esc(o.href)}">${esc(o.t)}</a>` : esc(o.t);
      return `<td${c.num ? ' class="num"' : ''}${o.bg ? ` style="background:${o.bg}"` : ''}>${inner}</td>`;
    };
    const draw = (n) => {
      const head = cols.map((c, j) => {
        const sort = j === sortCol ? ` aria-sort="${asc ? 'ascending' : 'descending'}"` : '';
        const label = c.sort ? `<button type="button" class="sort" data-col="${j}">${esc(c.h)}</button>` : esc(c.h);
        return `<th scope="col"${c.num ? ' class="num"' : ''}${sort}>${label}</th>`;
      }).join('');
      const body = rows.slice(0, n).map((r) => `<tr>${cols.map((c) => cell(c, r)).join('')}</tr>`).join('');
      wrap.innerHTML = `<div class="table-wrap"><table class="compact ex-table ${cls}"><thead><tr>${head}</tr></thead>`
        + `<tbody>${body}</tbody></table></div>`
        + (rows.length > n ? `<p class="ex-all small muted">${esc(t('ex_top', { n: num(n) }))} <button type="button" `
          + `class="link-button" data-all>${esc(t('ex_show_all'))} (${num(rows.length)})</button></p>` : '');
    };
    draw(Math.min(limit, rows.length));
    wrap.addEventListener('click', (e) => {
      if (e.target.closest('[data-all]')) draw(rows.length);
      const b = e.target.closest('[data-col]');
      if (b && onSort) onSort(Number(b.dataset.col));
    });
    return wrap;
  };
  const stCols = () => [
    { h: t('ex_col_mun'), get: (r) => munName(r.d.stations.mc[r.i], r.d) },
    { h: t('ex_col_no'), num: true, get: (r) => r.d.stations.no[r.i] },
    { h: t('ex_col_name'), get: (r) => ({ t: stName(r.d, r.i), href: stHref(r.d, r.i) }) },
  ];
  const munCols = () => [
    { h: t('ex_col_mun'), get: (r) => ({ t: munName(r.code, r.d), href: munHref(r.code) }) },
    { h: t('ex_col_n'), num: true, get: (r) => num(r.idx.length) },
  ];
  const valCol = (h, u, get = (r) => r.value, bg = null) => ({ h, num: true, get: (r) => ({ t: fmt(u, get(r)), bg: bg ? bg(get(r)) : '' }) });
  const regCol = () => ({ h: t('m_reg'), num: true, get: (r) => num(r.i != null ? r.d.stations.reg[r.i] : gval('reg', r.d, r.idx, -1)) });

  // the stations behind a cell, a bar, a point or a municipality, listed under the chart
  let SEL = new Map();
  let lastSel = null;
  // SEL: id -> {title, cols, rows()}; the rows are built only when the reader asks for them
  const select = (id) => {
    const s = SEL.get(id);
    if (!s) return;
    lastSel = id;
    out.querySelectorAll('.ex-on').forEach((n) => n.classList.remove('ex-on'));
    out.querySelectorAll('[data-sel]').forEach((n) => { if (n.dataset.sel === id) n.classList.add('ex-on'); });
    const rows = s.rows();
    listEl.textContent = '';
    const h = document.createElement('h2');
    h.className = 'ex-h';
    h.textContent = `${s.title} · ${countText(s.munList ? 'm' : 's', rows.length)}`;
    listEl.append(h, tableEl(s.cols, rows));
  };

  // --- charts -----------------------------------------------------------------------------------------------------
  const FONT = 'IBM Plex Sans, system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
  const svgOpen = (W, H, label) => `<svg class="ex-chart" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" `
    + `width="${W}" height="${H}" role="img" aria-label="${esc(label)}" font-family="${FONT}" font-size="12">`;
  const text = (x, y, s, attrs = '') => `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" ${attrs}>${esc(s)}</text>`;
  const halo = () => `paint-order="stroke" stroke="${C.page}" stroke-width="3" stroke-linejoin="round"`;
  const width = (max) => Math.max(280, Math.min(max, Math.floor(out.clientWidth || max)));
  const tickText = (u, step) => (v) => num(v, digits(step));

  // A frame with grid lines; returns its scales and the SVG of the grid and axes.
  const frame = ({ W, H, x: [x0, x1], y: [y0, y1], xlab, ylab, ux, uy, square = false }) => {
    const yt = ticks(y0, y1, 5);
    const ylabW = Math.max(...yt.list.map((v) => tickText(uy, yt.step)(v).length)) * 7 + 10;
    const L = 22 + ylabW;
    const R = 14;
    const Tp = 12;
    const B = 46;
    let PW = W - L - R;
    let PH = H - Tp - B;
    if (square) { PW = Math.min(PW, PH); PH = PW; }
    const xs = (v) => L + ((v - x0) / (x1 - x0 || 1)) * PW;
    const ys = (v) => Tp + PH - ((v - y0) / (y1 - y0 || 1)) * PH;
    const xt = ticks(x0, x1, Math.max(3, Math.min(10, Math.round(PW / 70))));
    let grid = '';
    for (const v of yt.list) {
      grid += `<line x1="${L}" x2="${L + PW}" y1="${ys(v).toFixed(1)}" y2="${ys(v).toFixed(1)}" stroke="${C.grid}"/>`;
      grid += text(L - 6, ys(v) + 4, tickText(uy, yt.step)(v), `text-anchor="end" fill="${C.ink2}"`);
    }
    for (const v of xt.list) {
      grid += `<line x1="${xs(v).toFixed(1)}" x2="${xs(v).toFixed(1)}" y1="${Tp}" y2="${Tp + PH}" stroke="${C.grid}"/>`;
      grid += text(xs(v), Tp + PH + 16, tickText(ux, xt.step)(v), `text-anchor="middle" fill="${C.ink2}"`);
    }
    const maxX = Math.floor(PW / 6.6);
    const maxY = Math.floor(PH / 6.6);
    const axes = `<line x1="${L}" x2="${L + PW}" y1="${Tp + PH}" y2="${Tp + PH}" stroke="${C.axis}"/>`
      + `<line x1="${L}" x2="${L}" y1="${Tp}" y2="${Tp + PH}" stroke="${C.axis}"/>`
      + text(L + PW / 2, Tp + PH + 36, cut(withUnit(xlab, ux), maxX), `text-anchor="middle" fill="${C.ink}" font-weight="600"`)
      + `<text transform="translate(14 ${(Tp + PH / 2).toFixed(1)}) rotate(-90)" text-anchor="middle" fill="${C.ink}" `
      + `font-weight="600">${esc(cut(withUnit(ylab, uy), maxY))}</text>`;
    return { L, Tp, PW, PH, xs, ys, grid, axes, H: Tp + PH + B, W: square ? L + PW + R : W };
  };
  const rangeText = (u, a, b, step) => {
    const d = digits(step);
    return u === 'pct' ? `${num(a, d)}–${num(b, d)}%` : `${num(a, d)}–${num(b, d)}`;
  };

  // Two values per row: a heat grid of counts for many stations' shares, otherwise points.
  const plot2 = ({ rows, xlab, ylab, ux, uy, grid2, diagonal, same, title, cols, dot, expand }) => {
    const xv = rows.map((r) => r.value);
    const yv = rows.map((r) => r.y);
    let dx;
    let dy;
    if (grid2) { // shares from 0, to where the stations end
      const top = (vals) => Math.min(100, niceDomain(0, quantile(sorted(vals), 0.995) || 1)[1]);
      dx = [0, top(xv)];
      dy = [0, top(yv)];
    } else {
      dx = niceDomain(...extent(xv));
      dy = niceDomain(...extent(yv));
    }
    if (same) { dx = [Math.min(dx[0], dy[0]), Math.max(dx[1], dy[1])]; dy = dx; }
    const W0 = width(620);
    const f = frame({ W: W0, H: Math.min(W0, 560), x: dx, y: dy, xlab, ylab, ux, uy, square: true });
    let marks = '';
    let legend = '';
    if (grid2) {
      const nb = 50;
      const sx = (dx[1] - dx[0]) / nb;
      const sy = (dy[1] - dy[0]) / nb;
      const bin = (v, lo, s) => Math.max(0, Math.min(nb - 1, Math.floor((v - lo) / s + 1e-9)));
      const cells = new Map();
      for (const r of rows) {
        const k = `${bin(r.value, dx[0], sx)}_${bin(r.y, dy[0], sy)}`;
        if (!cells.has(k)) cells.set(k, []);
        cells.get(k).push(r);
      }
      let most = 1;
      cells.forEach((v) => { most = Math.max(most, v.length); });
      const cw = f.PW / nb;
      const ch = f.PH / nb;
      cells.forEach((list, k) => {
        const [cx, cy] = k.split('_').map(Number);
        const xr = rangeText(ux, dx[0] + cx * sx, dx[0] + (cx + 1) * sx, sx);
        const yr = rangeText(uy, dy[0] + cy * sy, dy[0] + (cy + 1) * sy, sy);
        const tip = t('ex_cell', { x: xr, y: yr, n: num(list.length) });
        const id = `c${k}`;
        SEL.set(id, { title: `${xr}, ${yr}`, rows: () => expand(list), cols });
        marks += `<rect x="${(f.L + cx * cw).toFixed(1)}" y="${(f.Tp + f.PH - (cy + 1) * ch).toFixed(1)}" `
          + `width="${(cw + 0.3).toFixed(1)}" height="${(ch + 0.3).toFixed(1)}" `
          + `fill="${mix(0.16 + (0.84 * Math.log1p(list.length)) / Math.log1p(most))}" data-sel="${id}" data-tip="${esc(tip)}"/>`;
      });
      // how many stations a colour means: the scale is logarithmic, so a lone station still shows
      const y = f.H + 4;
      legend = text(f.L, y + 10, t('ex_count'), `fill="${C.ink2}" font-size="11"`);
      for (let k = 0; k < 6; k += 1) {
        legend += `<rect x="${f.L + k * 30}" y="${y + 16}" width="28" height="10" fill="${mix(0.16 + (0.84 * k) / 5)}"/>`;
      }
      legend += text(f.L, y + 40, '1', `fill="${C.ink2}" font-size="11"`)
        + text(f.L + 178, y + 40, num(most), `text-anchor="end" fill="${C.ink2}" font-size="11"`);
    } else {
      const big = Math.max(1, ...rows.map((r) => r.size || 0));
      for (const r of rows) {
        const rad = r.size != null ? 3 + 9 * Math.sqrt(r.size / big) : 2.6;
        SEL.set(r.id, { title: r.label, rows: () => expand([r]), cols });
        marks += `<circle cx="${f.xs(r.value).toFixed(1)}" cy="${f.ys(r.y).toFixed(1)}" r="${rad.toFixed(1)}" `
          + `fill="${C.accent}" fill-opacity="${r.size != null ? 0.5 : 0.4}" stroke="${r.size != null ? C.page : 'none'}" `
          + `data-sel="${esc(r.id)}" data-tip="${esc(dot(r))}"/>`;
      }
    }
    let diag = '';
    if (diagonal) {
      const a = Math.max(dx[0], dy[0]);
      const b = Math.min(dx[1], dy[1]);
      diag = `<line x1="${f.xs(a).toFixed(1)}" y1="${f.ys(a).toFixed(1)}" x2="${f.xs(b).toFixed(1)}" y2="${f.ys(b).toFixed(1)}" `
        + `stroke="${C.ink}" stroke-dasharray="5 4" stroke-width="1"/>`
        + text(f.xs(b) - 4, f.ys(b) + 14, t('ex_diagonal'), `text-anchor="end" fill="${C.ink}" font-size="11" ${halo()}`);
    }
    return `${svgOpen(f.W, f.H + (legend ? 48 : 0), title)}${f.grid}${marks}${diag}${f.axes}${legend}</svg>`;
  };

  // --- views ------------------------------------------------------------------------------------------------------
  const summary = (bits) => {
    const line = bits.filter(Boolean).join(' · ');
    sum.textContent = line.charAt(0).toUpperCase() + line.slice(1);
  };
  const countText = (lv, n) => t(lv === 's' ? 'ex_n_s' : 'ex_n_m', { n: num(n) });
  const shareYes = (rows) => {
    const known = rows.filter((r) => r.value != null);
    return known.length ? `${num((100 * known.filter((r) => r.value).length) / known.length, 1)}%` : '—';
  };
  const stCsv = (d, i) => [d.stations.mc[i], munName(d.stations.mc[i], d), d.stations.no[i], own(d.stations.name[i]),
    d.stations.reg[i], d.stations.voted[i]];
  const stHead = () => [t('ex_col_code'), t('ex_col_mun'), t('ex_col_no'), t('ex_col_name'), t('m_reg'), t('m_voted')];
  const munCsv = (r) => [r.code, munName(r.code, r.d), r.idx.length, gval('reg', r.d, r.idx, -1), gval('voted', r.d, r.idx, -1)];
  const munHead = () => [t('ex_col_code'), t('ex_col_mun'), t('ex_col_n'), t('m_reg'), t('m_voted')];
  const absUrl = (href) => new URL(href, location.href).href;

  const drawTable = ([d]) => {
    const lv = st.lv;
    const key = st.x;
    const u = unit(key, lv);
    const rows = rowsOf(d, kept(d, st.r), lv, key, listIx(d, st.lx)).filter(ranged(u));
    const asc = st.o === 'a';
    rows.sort(byValue(asc));
    const label = mlabel(key, st.r, st.lx);
    summary([countText(lv, rows.length),
      u === 'yes' ? `${t(`m_${key}`)}: ${shareYes(rows)}` : t('ex_median', { v: fmt(u, median(rows.map((r) => r.value))) })]);
    if (!rows.length) return { empty: true };
    const bg = heat(rows.map((r) => r.value));
    const vc = { ...valCol(label, u, (r) => r.value, u === 'yes' ? null : bg), sort: true };
    const cols = lv === 's' ? [...stCols(), vc] : [...munCols(), vc];
    if (key !== 'reg') cols.push(regCol());
    const onSort = () => { st.o = asc ? '' : 'a'; commit(); };
    out.append(tableEl(cols, rows, { sortCol: cols.indexOf(vc), asc, onSort }));
    const head = lv === 's' ? [...stHead(), withUnit(label, u), t('ex_col_link')] : [...munHead(), withUnit(label, u), t('ex_col_link')];
    const body = rows.map((r) => (lv === 's'
      ? [...stCsv(d, r.i), csvNum(u, r.value), absUrl(stHref(d, r.i))]
      : [...munCsv(r), csvNum(u, r.value), absUrl(munHref(r.code))]));
    return { title: `${BY_ID[st.r].short} · ${label}`, csv: [head, ...body] };
  };

  const drawHist = ([d]) => {
    const lv = st.lv;
    const key = st.x;
    const u = unit(key, lv);
    const rows = rowsOf(d, kept(d, st.r), lv, key, listIx(d, st.lx)).filter(ranged(u)).filter((r) => r.value != null);
    const label = mlabel(key, st.r, st.lx);
    const med = median(rows.map((r) => r.value));
    summary([countText(lv, rows.length), t('ex_median', { v: fmt(u, med) })]);
    if (!rows.length) return { empty: true };
    const vals = sorted(rows.map((r) => r.value));
    let lo;
    let hi;
    if (u === 'pct') {
      hi = Math.min(100, niceDomain(0, quantile(vals, 0.995) || 1)[1]);
      lo = Math.max(0, vals[0]);
    } else {
      lo = vals[0];
      hi = quantile(vals, 0.99);
      if (!(hi > lo)) hi = vals[vals.length - 1];
      if (!(hi > lo)) hi = lo + 1;
    }
    const step = niceStep((hi - lo) / (lv === 's' ? 80 : 30));
    lo = Math.floor(lo / step + 1e-9) * step;
    hi = Math.max(lo + step, Math.ceil(hi / step - 1e-9) * step);
    const nb = Math.max(1, Math.round((hi - lo) / step));
    const bins = Array.from({ length: nb }, () => []);
    let over = false;
    for (const r of rows) {
      let b = Math.floor((r.value - lo) / step + 1e-9);
      if (b >= nb) { b = nb - 1; if (r.value > hi) over = true; }
      bins[Math.max(0, b)].push(r);
    }
    const most = Math.max(...bins.map((b) => b.length));
    const f = frame({ W: width(860), H: 320, x: [lo, hi], y: niceDomain(0, most), xlab: label,
      ylab: lv === 's' ? t('ex_count') : t('level_m'), ux: u, uy: 'count' });
    const bw = f.PW / nb;
    const cols = lv === 's' ? [...stCols(), valCol(label, u), regCol()] : [...munCols(), valCol(label, u), regCol()];
    let marks = '';
    bins.forEach((list, b) => {
      if (!list.length) return;
      const a = lo + b * step;
      const rt = b === nb - 1 && over ? `≥ ${fmt(u, a)}` : rangeText(u, a, a + step, step);
      const id = `b${b}`;
      SEL.set(id, { title: rt, rows: () => [...list].sort(byValue(false)), cols, munList: lv === 'm' });
      const y = f.ys(list.length);
      marks += `<rect x="${(f.L + b * bw + 0.5).toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, bw - 1).toFixed(1)}" `
        + `height="${(f.Tp + f.PH - y).toFixed(1)}" fill="${C.accent}" data-sel="${id}" `
        + `data-tip="${esc(`${rt} · ${countText(lv, list.length)}`)}"/>`;
    });
    const mx = f.xs(Math.min(hi, med));
    marks += `<line x1="${mx.toFixed(1)}" x2="${mx.toFixed(1)}" y1="${f.Tp}" y2="${f.Tp + f.PH}" stroke="${C.ink}" `
      + 'stroke-dasharray="4 3"/>'
      + text(mx + (mx > f.L + f.PW * 0.7 ? -5 : 5), f.Tp + 12, t('ex_median', { v: fmt(u, med) }),
        `text-anchor="${mx > f.L + f.PW * 0.7 ? 'end' : 'start'}" fill="${C.ink}" font-size="11" ${halo()}`);
    const title = `${BY_ID[st.r].short} · ${label}`;
    out.insertAdjacentHTML('beforeend', `${svgOpen(f.W, f.H, title)}${f.grid}${marks}${f.axes}</svg>`);
    const head = lv === 's' ? [...stHead(), withUnit(label, u), t('ex_col_link')] : [...munHead(), withUnit(label, u), t('ex_col_link')];
    const body = rows.map((r) => (lv === 's'
      ? [...stCsv(d, r.i), csvNum(u, r.value), absUrl(stHref(d, r.i))]
      : [...munCsv(r), csvNum(u, r.value), absUrl(munHref(r.code))]));
    return { title, csv: [head, ...body], svg: true, pick: 'ex_bar_pick' };
  };

  const drawDensity = ([d]) => {
    const lv = st.lv;
    const lix = listIx(d, st.lx);
    const liy = listIx(d, st.ly);
    const ux = unit(st.x, lv);
    const uy = unit(st.y, lv);
    const idx = kept(d, st.r);
    const rows = (lv === 's'
      ? idx.map((i) => ({ id: `s${i}`, d, i, code: d.stations.mc[i], value: sval(st.x, d, i, lix), y: sval(st.y, d, i, liy) }))
      : [...byMun(d, idx)].map(([code, ix]) => ({ id: `m${code}`, d, code, idx: ix, value: gval(st.x, d, ix, lix),
        y: gval(st.y, d, ix, liy), size: gval('reg', d, ix, -1) })))
      .filter(ranged(ux)).filter((r) => r.value != null && r.y != null);
    const xl = mlabel(st.x, st.r, st.lx);
    const yl = mlabel(st.y, st.r, st.ly);
    const rr = pearson(rows.map((r) => [r.value, r.y]));
    summary([countText(lv, rows.length), rr == null ? '' : t('ex_r', { v: num(rr, 2) })]);
    if (!rows.length) return { empty: true };
    rows.forEach((r) => { r.label = lv === 's' ? `${munName(r.code, d)} · ${stName(d, r.i)}` : munName(r.code, d); });
    // listed: the stations, each with its own two values
    const kx = st.x;
    const ky = st.y;
    const cols = [...stCols(), valCol(xl, unit(kx, 's')), valCol(yl, unit(ky, 's'), (r) => r.y), regCol()];
    const expand = (list) => list.flatMap((r) => (r.i != null ? [r]
      : r.idx.map((i) => ({ d, i, value: sval(kx, d, i, lix), y: sval(ky, d, i, liy) })))).sort(byValue(false));
    const title = `${BY_ID[st.r].short} · ${xl} × ${yl}`;
    const dot = (r) => `${r.label}: ${fmt(ux, r.value)}, ${fmt(uy, r.y)}`;
    out.insertAdjacentHTML('beforeend', plot2({ rows, xlab: xl, ylab: yl, ux, uy, grid2: lv === 's' && ux === 'pct' && uy === 'pct',
      title, cols, dot, expand }));
    const head = lv === 's' ? [...stHead(), withUnit(xl, ux), withUnit(yl, uy), t('ex_col_link')]
      : [...munHead(), withUnit(xl, ux), withUnit(yl, uy), t('ex_col_link')];
    const body = rows.map((r) => (lv === 's'
      ? [...stCsv(d, r.i), csvNum(ux, r.value), csvNum(uy, r.y), absUrl(stHref(d, r.i))]
      : [...munCsv(r), csvNum(ux, r.value), csvNum(uy, r.y), absUrl(munHref(r.code))]));
    return { title, csv: [head, ...body], svg: true, pick: lv === 's' && ux === 'pct' && uy === 'pct' ? 'ex_cell_pick' : 'ex_dot_pick' };
  };

  const drawCompare = () => {
    const lv = st.lv;
    const key = st.x;
    const u = unit(key, lv);
    const [ra, rb] = later(st.r, st.r2) ? [st.r2, st.r] : [st.r, st.r2]; // earlier on the left, later up
    const da = DATA[ra];
    const db = DATA[rb];
    const lia = listIx(da, ra === st.r ? st.lx : st.ly);
    const lib = listIx(db, rb === st.r ? st.lx : st.ly);
    const la = mlabel(key, ra, ra === st.r ? st.lx : st.ly);
    const lb = mlabel(key, rb, rb === st.r ? st.lx : st.ly);
    const xa = `${BY_ID[ra].short}: ${la}`;
    const yb = `${BY_ID[rb].short}: ${lb}`;
    let rows = [];
    if (lv === 's') { // the same polling place in both elections
      const places = (d, rid) => {
        const m = new Map();
        for (const i of kept(d, rid)) if (d.stations.place[i] && !m.has(d.stations.place[i])) m.set(d.stations.place[i], i);
        return m;
      };
      const pa = places(da, ra);
      places(db, rb).forEach((ib, p) => {
        const ia = pa.get(p);
        if (ia == null) return;
        const va = sval(key, da, ia, lia);
        const vb = sval(key, db, ib, lib);
        if (va == null || vb == null) return;
        rows.push({ id: `p${p}`, d: db, i: ib, ia, code: db.stations.mc[ib], value: va, y: vb });
      });
    } else { // the same municipality, by its code
      const ga = byMun(da, kept(da, ra));
      byMun(db, kept(db, rb)).forEach((ib, code) => {
        if (!ga.has(code)) return;
        const va = gval(key, da, ga.get(code), lia);
        const vb = gval(key, db, ib, lib);
        if (va == null || vb == null) return;
        rows.push({ id: `m${code}`, d: db, code, idx: ib, value: va, y: vb, size: gval('reg', db, ib, -1) });
      });
    }
    const change = (r) => (u === 'count' ? (r.value ? (100 * (r.y - r.value)) / Math.abs(r.value) : null) : r.y - r.value);
    const chText = (v) => (v == null ? '—' : u === 'count' ? `${signed(v, 1)}%` : `${signed(v, 1)} ${t('ex_pp')}`);
    rows.forEach((r) => {
      r.a = r.value;
      r.ch = change(r);
      r.label = lv === 's' ? `${munName(r.code, db)} · ${stName(db, r.i)}` : munName(r.code, db);
    });
    const rr = pearson(rows.map((r) => [r.value, r.y]));
    summary([t('ex_matched', { n: num(rows.length) }), t('ex_median_change', { v: chText(median(rows.map((r) => r.ch))) }),
      rr == null ? '' : t('ex_r', { v: num(rr, 2) })]);
    if (!rows.length) return { empty: true };
    const bigFirst = (p, q) => (p.ch == null || q.ch == null ? (p.ch == null) - (q.ch == null) : Math.abs(q.ch) - Math.abs(p.ch));
    const chCol = { h: t('ex_change'), num: true, get: (r) => chText(r.ch) };
    const pairCols = (us) => [valCol(BY_ID[ra].short, us, (r) => r.a), valCol(BY_ID[rb].short, us, (r) => r.y),
      { h: t('ex_change'), num: true, get: (r) => (us === 'yes' ? '' : chText(r.ch)) }];
    // listed: a municipality's stations in the later election, each beside the same place in the earlier one
    const us = unit(key, 's');
    const stPairs = (code) => {
      const pa = new Map();
      for (const i of kept(da, ra)) if (da.stations.mc[i] === code && da.stations.place[i] && !pa.has(da.stations.place[i])) pa.set(da.stations.place[i], i);
      return kept(db, rb).filter((ib) => db.stations.mc[ib] === code).map((ib) => {
        const ia = db.stations.place[ib] ? pa.get(db.stations.place[ib]) : undefined;
        const r = { d: db, i: ib, a: ia == null ? null : sval(key, da, ia, lia), y: sval(key, db, ib, lib) };
        r.value = r.a;
        r.ch = r.a == null || r.y == null ? null : us === 'count' ? (r.a ? (100 * (r.y - r.a)) / Math.abs(r.a) : null) : r.y - r.a;
        return r;
      }).sort(bigFirst);
    };
    const expand = (list) => list.flatMap((r) => (r.i != null ? [r] : stPairs(r.code))).sort(bigFirst);
    const title = `${BY_ID[ra].short} → ${BY_ID[rb].short} · ${la === lb ? la : `${la} / ${lb}`}`;
    const dot = (r) => `${r.label}: ${fmt(u, r.value)} → ${fmt(u, r.y)}`;
    out.insertAdjacentHTML('beforeend', plot2({ rows, xlab: xa, ylab: yb, ux: u, uy: u, grid2: lv === 's' && u === 'pct',
      diagonal: true, same: true, title, cols: [...stCols(), ...pairCols(us)], dot, expand }));
    const big = [...rows].filter((r) => r.ch != null).sort(bigFirst);
    const h = document.createElement('h2');
    h.className = 'ex-h';
    h.textContent = t('ex_biggest');
    moreEl.append(h, tableEl([...(lv === 's' ? stCols() : munCols()), valCol(BY_ID[ra].short, u, (r) => r.a),
      valCol(BY_ID[rb].short, u, (r) => r.y), chCol], big, { limit: 25 }));
    const head = lv === 's'
      ? [...stHead(), withUnit(`${BY_ID[ra].short}: ${la}`, u), withUnit(`${BY_ID[rb].short}: ${lb}`, u), t('ex_change'), t('ex_col_link')]
      : [...munHead(), withUnit(`${BY_ID[ra].short}: ${la}`, u), withUnit(`${BY_ID[rb].short}: ${lb}`, u), t('ex_change'), t('ex_col_link')];
    const body = rows.map((r) => [...(lv === 's' ? stCsv(db, r.i) : munCsv(r)), csvNum(u, r.a), csvNum(u, r.y),
      r.ch == null ? '' : Number(r.ch.toFixed(2)), absUrl(lv === 's' ? stHref(db, r.i) : munHref(r.code))]);
    return { title, csv: [head, ...body], svg: true, pick: lv === 's' && u === 'pct' ? 'ex_cell_pick' : 'ex_dot_pick', file: `${ra}-${rb}` };
  };

  const drawMatrix = () => {
    const key = st.x;
    const u = unit(key, 'm');
    const order = [...ROUNDS].reverse(); // oldest first, as on the pages across elections
    const colsData = order.map((r) => ({ r, d: DATA[r.id], g: byMun(DATA[r.id], kept(DATA[r.id], r.id)) }));
    const codes = new Set();
    colsData.forEach((c) => c.g.forEach((_, code) => codes.add(code)));
    // an election whose observers' records weren't read has no value for them, not zero
    const known = (r) => key !== 'obs' || r.obs;
    const rows = [...codes].map((code) => ({
      code,
      name: munName(code, colsData.find((c) => c.g.has(code)).d),
      vals: colsData.map((c) => (c.g.has(code) && known(c.r) ? gval(key, c.d, c.g.get(code), -1) : null)),
    }));
    const sortBy = order.findIndex((r) => r.id === st.o);
    if (sortBy >= 0) rows.sort((p, q) => byValue(false)({ value: p.vals[sortBy] }, { value: q.vals[sortBy] }) || coll.compare(p.name, q.name));
    else rows.sort((p, q) => coll.compare(p.name, q.name));
    summary([countText('m', rows.length)]);
    if (!rows.length) return { empty: true };
    const bg = heat(rows.flatMap((r) => r.vals));
    const cols = [{ h: t('ex_col_mun'), sort: true, get: (r) => ({ t: r.name, href: munHref(r.code) }) },
      ...order.map((r, j) => ({ h: r.short, num: true, sort: true, get: (row) => ({ t: row.vals[j] == null ? '' : fmt(u, row.vals[j]), bg: bg(row.vals[j]) }) }))];
    const onSort = (j) => { st.o = j === 0 ? '' : order[j - 1].id; commit(); };
    out.append(tableEl(cols, rows, { limit: Infinity, sortCol: sortBy >= 0 ? sortBy + 1 : 0, asc: sortBy < 0, onSort,
      cls: 'ex-matrix' }));
    const label = t(`m_${key}`);
    const head = [t('ex_col_code'), t('ex_col_mun'), ...order.map((r) => withUnit(`${r.short}: ${label}`, u))];
    const body = rows.map((r) => [r.code, r.name, ...r.vals.map((v) => csvNum(u, v))]);
    return { title: label, csv: [head, ...body], file: 'all' };
  };

  // the map: equirectangular, squeezed by the cosine of the middle latitude, which is close enough for one country
  const project = (feats, W) => {
    let x0 = Infinity; let x1 = -Infinity; let y0 = Infinity; let y1 = -Infinity;
    const each = (g, fn) => {
      for (const poly of g.type === 'Polygon' ? [g.coordinates] : g.coordinates) for (const ring of poly) for (const p of ring) fn(p);
    };
    feats.forEach((f) => each(f.geometry, ([lon, lat]) => {
      if (lon < x0) x0 = lon; if (lon > x1) x1 = lon; if (lat < y0) y0 = lat; if (lat > y1) y1 = lat;
    }));
    const padX = (x1 - x0) * 0.03 || 0.01;
    const padY = (y1 - y0) * 0.03 || 0.01;
    x0 -= padX; x1 += padX; y0 -= padY; y1 += padY;
    const k = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
    const s = W / ((x1 - x0) * k);
    const P = ([lon, lat]) => [(lon - x0) * k * s, (y1 - lat) * s];
    const path = (g) => {
      let dd = '';
      for (const poly of g.type === 'Polygon' ? [g.coordinates] : g.coordinates) {
        for (const ring of poly) {
          ring.forEach((p, j) => { const [x, y] = P(p); dd += `${j ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`; });
          dd += 'Z';
        }
      }
      return dd;
    };
    return { H: Math.round((y1 - y0) * s), path };
  };
  const drawMap = ([d]) => {
    const key = st.x;
    const u = unit(key, 'm');
    const rows = rowsOf(d, kept(d, st.r), 'm', key, listIx(d, st.lx)).filter(ranged(u));
    const label = mlabel(key, st.r, st.lx);
    const sorted2 = [...rows].sort(byValue(false));
    summary([countText('m', rows.length), t('ex_median', { v: fmt(u, median(rows.map((r) => r.value))) }), t('ex_map_sums')]);
    if (!rows.length) return { empty: true };
    const stc = [...stCols(), valCol(label, unit(key, 's')), regCol()];
    const li = listIx(d, st.lx);
    rows.forEach((r) => {
      SEL.set(r.id, { title: munName(r.code, d), cols: stc,
        rows: () => r.idx.map((i) => ({ d, i, value: sval(key, d, i, li) })).sort(byValue(false)) });
    });
    const title = `${BY_ID[st.r].short} · ${label}`;
    const wrap = document.createElement('div');
    wrap.className = 'ex-map-wrap';
    const fig = document.createElement('div');
    fig.className = 'ex-fig';
    const feats = (GEO && GEO.features) || [];
    const byCode = new Map(rows.map((r) => [r.code, r]));
    const shown = feats.filter((f) => byCode.has(f.properties.code));
    let svg = false;
    if (!shown.length) {
      fig.innerHTML = `<p class="muted">${esc(t('ex_no_geo'))}</p>`;
    } else {
      const W = Math.min(width(600), 600);
      const pr = project(shown, W);
      const onMap = new Set(shown.map((f) => f.properties.code));
      const sc = classes(rows.filter((r) => onMap.has(r.code)).map((r) => r.value)); // the colours fit what is drawn
      let paths = '';
      feats.forEach((f) => {
        const r = byCode.get(f.properties.code);
        const dd = pr.path(f.geometry);
        if (!r) {
          paths += `<path d="${dd}" fill="${C.grid}" stroke="${C.page}" stroke-width="0.7" fill-rule="evenodd"/>`;
          return;
        }
        const tip = `${munName(r.code, d)}: ${fmt(u, r.value)} · ${countText('s', r.idx.length)}`;
        paths += `<path d="${dd}" fill="${sc.color(r.value)}" stroke="${C.page}" stroke-width="0.7" fill-rule="evenodd" `
          + `data-sel="${esc(r.id)}" data-tip="${esc(tip)}"/>`;
      });
      // the legend and the source, under the map, so a downloaded map carries both
      const y0 = pr.H + 14;
      let leg = text(0, y0 + 10, cut(withUnit(label, u), Math.floor(W / 6.6)), `fill="${C.ink}" font-weight="600"`);
      const nb = sc.breaks.length + 1;
      const bw = Math.min(46, Math.floor((W - 110) / (nb + 1))); // the classes and "no data" fit a phone
      for (let c = 0; c < nb; c += 1) {
        const v = c === 0 ? -Infinity : sc.breaks[c - 1];
        leg += `<rect x="${c * bw}" y="${y0 + 18}" width="${bw - 2}" height="12" fill="${sc.color(v === -Infinity ? (sc.breaks[0] ?? 0) - 1 : v)}"/>`;
        if (c > 0) leg += text(c * bw - 1, y0 + 44, num(sc.breaks[c - 1], digits(sc.step)), `text-anchor="middle" fill="${C.ink2}" font-size="11"`);
      }
      leg += `<rect x="${nb * bw + 14}" y="${y0 + 18}" width="${bw - 2}" height="12" fill="${C.grid}"/>`
        + text(nb * bw + 14, y0 + 44, t('ex_nodata'), `fill="${C.ink2}" font-size="11"`);
      // the sources of what is drawn, so a downloaded map credits them; the second only when it draws from it
      const kim = shown.some((f) => f.properties.kim);
      const attr = text(W, y0 + 66, t('ex_attribution'), `text-anchor="end" fill="${C.ink2}" font-size="10"`)
        + (kim ? text(W, y0 + 80, t('ex_attribution_kim'), `text-anchor="end" fill="${C.ink2}" font-size="10"`) : '');
      fig.innerHTML = `${svgOpen(W, y0 + (kim ? 86 : 72), title)}<g>${paths}</g>${leg}${attr}</svg>`;
      svg = true;
      const off = rows.filter((r) => !shown.some((f) => f.properties.code === r.code)).map((r) => munName(r.code, d));
      if (off.length) {
        const p = document.createElement('p');
        p.className = 'small muted ex-off';
        p.textContent = t('ex_not_on_map', { names: off.sort(coll.compare).join(', ') });
        fig.append(p);
      }
    }
    const side = document.createElement('div');
    side.className = 'ex-side';
    const bg = heat(rows.map((r) => r.value));
    side.append(tableEl([...munCols(), valCol(label, u, (r) => r.value, bg)], sorted2, { limit: Infinity }));
    wrap.append(fig, side);
    out.append(wrap);
    const head = [...munHead(), withUnit(label, u), t('ex_col_link')];
    const body = sorted2.map((r) => [...munCsv(r), csvNum(u, r.value), absUrl(munHref(r.code))]);
    return { title, csv: [head, ...body], svg, pick: 'ex_map_pick' };
  };

  // --- drawing it all ---------------------------------------------------------------------------------------------
  const say = (k, vars) => { msg.textContent = k ? t(k, vars) : ''; };
  let current = null;
  const setActions = (res) => {
    current = res && !res.empty ? res : null;
    btnCsv.hidden = !(current && current.csv);
    btnSvg.hidden = !(current && current.svg);
  };
  const problem = () => {
    const v = st.v;
    if (v === 'compare' && !st.r2) return 'ex_msg_round2';
    if (v === 'matrix') return M[st.x].list ? 'ex_msg_matrix' : null;
    const used = [[st.x, st.r, st.lx]];
    if (v === 'density') used.push([st.y, st.r, st.ly]);
    if (v === 'compare') used.push([st.x, st.r2, st.ly]);
    for (const [key, rid, n] of used) {
      if (key === 'ctrl' && !BY_ID[rid].ctrl) return 'ex_msg_ctrl';
      if (key === 'obs' && !BY_ID[rid].obs) return 'ex_msg_obs';
      if (M[key].list && listIx(DATA[rid], n) < 0) return 'ex_msg_list';
    }
    if (st.cl && !BY_ID[st.r].ctrl) return 'ex_msg_ctrl';
    if (st.ob && !BY_ID[st.r].obs) return 'ex_msg_obs';
    return null;
  };
  const fillMun = (ds) => {
    const codes = new Map();
    ds.forEach((d) => Object.keys(d.municipalities).forEach((c) => { if (!codes.has(c)) codes.set(c, munName(c, d)); }));
    munItems = [...codes].sort((a, b) => coll.compare(a[1], b[1]));
    const had = st.mun;
    st.mun = fill('mun', [['', t('ex_all')], ...munItems], st.mun);
    if (had !== st.mun) history.replaceState(null, '', toHash(st));
  };
  const markPreset = () => {
    const h = toHash(st);
    presetsEl.querySelectorAll('a').forEach((a) => {
      if (a.getAttribute('href') === h) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
  };
  let token = 0;
  let drawnWidth = 0;
  const render = async () => {
    const my = ++token;
    colors();
    SEL = new Map();
    tip.hidden = true;
    markPreset();
    const v = st.v;
    const need = v === 'matrix' ? ROUNDS.map((r) => r.id) : v === 'compare' && st.r2 ? [st.r, st.r2] : [st.r];
    if (need.some((id) => !DATA[id]) || (v === 'map' && GEO === undefined)) say('ex_msg_loading');
    let ds;
    try {
      ds = await Promise.all(need.map(load));
      if (v === 'map') await loadGeo();
    } catch (e) {
      if (my !== token) return;
      out.textContent = '';
      sum.textContent = '';
      listEl.textContent = '';
      moreEl.textContent = '';
      setActions(null);
      say('ex_msg_error');
      return;
    }
    if (my !== token) return;
    say('');
    fillMun(ds);
    out.textContent = '';
    sum.textContent = '';
    listEl.textContent = '';
    moreEl.textContent = '';
    drawnWidth = out.clientWidth;
    const p = problem();
    if (p) { setActions(null); say(p); return; }
    const res = { map: drawMap, density: drawDensity, compare: drawCompare, hist: drawHist, table: drawTable, matrix: drawMatrix }[v](ds);
    setActions(res);
    if (res && res.empty) { say('ex_msg_nodata'); return; }
    if (lastSel && SEL.has(lastSel)) select(lastSel);
    else if (res && res.pick) listEl.innerHTML = `<p class="small muted">${esc(t(res.pick))}</p>`;
  };
  const commit = () => {
    st = clean(st);
    syncForm();
    history.replaceState(null, '', toHash(st));
    lastSel = null;
    render();
  };

  // --- what the reader does ---------------------------------------------------------------------------------------
  form.addEventListener('change', (e) => {
    const n = e.target.name;
    if (!n || !(n in st)) return;
    const before = toHash(st);
    st[n] = e.target.value.trim();
    if (n === 'r') { // another election, other lists: the reader chooses again
      st.lx = '';
      st.cl = '';
      if (st.v !== 'compare') st.ly = '';
      if (st.r2 === st.r) { st.r2 = ''; st.ly = ''; }
    }
    if (n === 'r2') st.ly = '';
    if (n === 'v') {
      st.o = '';
      if (st.v === 'compare' && !st.r2) st.r2 = previous(st.r);
    }
    if (n === 'x' || n === 'lv') { st.x0 = ''; st.x1 = ''; st.o = ''; }
    if (toHash(clean({ ...st })) !== before) commit();
  });
  let typing = null;
  form.addEventListener('input', (e) => {
    if (e.target.type !== 'number') return;
    clearTimeout(typing);
    typing = setTimeout(() => { // after a pause in typing, not at every key
      const before = toHash(st);
      st[e.target.name] = e.target.value.trim();
      if (toHash(clean({ ...st })) !== before) commit();
    }, 500);
  });
  window.addEventListener('hashchange', () => {
    st = fromHash();
    syncForm();
    lastSel = null;
    render();
  });

  // the tooltip, for a pointer; a click or a tap lists the stations
  const tip = document.createElement('div');
  tip.className = 'ex-tip';
  tip.hidden = true;
  box.append(tip);
  const place = (x, y) => {
    const b = box.getBoundingClientRect();
    let left = x - b.left + 14;
    if (left + tip.offsetWidth > b.width) left = Math.max(0, x - b.left - tip.offsetWidth - 14);
    tip.style.left = `${left}px`;
    tip.style.top = `${y - b.top + 16}px`;
  };
  out.addEventListener('pointermove', (e) => {
    const n = e.target.closest && e.target.closest('[data-tip]');
    if (!n) { tip.hidden = true; return; }
    tip.textContent = n.dataset.tip;
    tip.hidden = false;
    place(e.clientX, e.clientY);
  });
  out.addEventListener('pointerleave', () => { tip.hidden = true; });
  out.addEventListener('click', (e) => {
    const n = e.target.closest && e.target.closest('[data-sel]');
    if (n) select(n.dataset.sel);
  });

  btnCsv.addEventListener('click', () => {
    if (!current || !current.csv) return;
    const cell = (v) => {
      if (v == null) return '';
      let s = String(v);
      if (typeof v !== 'number' && /^[=+\-@\t\r]/.test(s)) s = `'${s}`; // a name is never a formula
      return /[",\r\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csv = `﻿${current.csv.map((r) => r.map(cell).join(',')).join('\r\n')}\r\n`;
    save(csv, 'text/csv;charset=utf-8', `${fileName()}.csv`);
  });
  btnSvg.addEventListener('click', () => {
    const svg = out.querySelector('svg.ex-chart');
    if (!svg || !current) return;
    const c = svg.cloneNode(true);
    const W = Number(c.getAttribute('width'));
    const H = Number(c.getAttribute('height'));
    const top = 46;
    c.setAttribute('viewBox', `0 ${-top} ${W} ${H + top + 8}`);
    c.setAttribute('height', String(H + top + 8));
    c.removeAttribute('class');
    c.querySelectorAll('[data-sel], [data-tip], .ex-on').forEach((n) => {
      n.removeAttribute('data-sel');
      n.removeAttribute('data-tip');
      n.removeAttribute('class');
    });
    const head = `<rect x="0" y="${-top}" width="${W}" height="${H + top + 8}" fill="${C.page}"/>`
      + text(0, -top + 16, cut(current.title, Math.floor(W / 7.2)), `fill="${C.ink}" font-weight="600" font-size="14"`)
      + text(0, -top + 34, cut(`${t('ex_source')} · ${location.origin}${location.pathname}`, Math.floor(W / 6)), `fill="${C.ink2}" font-size="11"`);
    c.insertAdjacentHTML('afterbegin', head);
    const xml = `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(c)}`;
    save(xml, 'image/svg+xml;charset=utf-8', `${fileName()}.svg`);
  });
  const fileName = () => {
    const what = st.v === 'matrix' ? 'all' : current && current.file ? current.file : st.r;
    return `izbori-${what}-${st.v}-${st.x}${M[st.x].list && st.lx ? `-${st.lx}` : ''}`;
  };
  const save = (body, type, name) => {
    const url = URL.createObjectURL(new Blob([body], { type }));
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };
  let copiedT = null;
  box.querySelector('[data-copy]').addEventListener('click', async () => {
    const url = `${location.href.split('#')[0]}${toHash(st)}`;
    clearTimeout(copiedT);
    try {
      await navigator.clipboard.writeText(url);
      copied.textContent = t('ex_copied');
      copiedT = setTimeout(() => { copied.textContent = ''; }, 4000);
    } catch (e) {
      copied.textContent = url; // no clipboard here: the link, to copy by hand
    }
  });

  // presets: links, so each opens like any shared analysis
  const presets = () => {
    const newest = ROUNDS[0];
    const prev = previous(newest.id);
    const withCtrl = ROUNDS.find((r) => r.ctrl);
    return [
      ['fingerprint', { v: 'density', r: newest.id, lv: 's', x: 'turnout', y: 'top' }],
      ['turnout_map', { v: 'map', r: newest.id, x: 'turnout' }],
      ['invalid_map', { v: 'map', r: newest.id, x: 'invalid' }],
      prev && ['turnout_change', { v: 'compare', r: newest.id, r2: prev, lv: 's', x: 'turnout' }],
      prev && ['register_change', { v: 'compare', r: newest.id, r2: prev, lv: 'm', x: 'reg' }],
      ROUNDS.length > 1 && ['matrix', { v: 'matrix', r: newest.id, x: 'turnout' }],
      withCtrl && ['ctrl_map', { v: 'map', r: withCtrl.id, x: 'ctrl' }],
      ['high', { v: 'table', r: newest.id, lv: 's', x: 'turnout', x0: '90' }],
    ].filter(Boolean);
  };
  presetsEl.innerHTML = presets().map(([k, s]) => `<a class="chip" href="${esc(toHash({ ...DEF, ...s }))}">${esc(t(`preset_${k}`))}</a>`).join('');

  // a new theme or a much wider or narrower window: draw again, keeping what was chosen
  new MutationObserver(() => render()).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  const dark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  if (dark && dark.addEventListener) dark.addEventListener('change', () => render());
  let resizing = null;
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      if (!drawnWidth || Math.abs(out.clientWidth - drawnWidth) < 40) return;
      clearTimeout(resizing);
      resizing = setTimeout(() => render(), 200);
    }).observe(out);
  }

  syncForm();
  render();
})();
