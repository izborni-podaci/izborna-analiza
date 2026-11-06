/* Filters for the tables and the list of stations to check. The pages work without it. */
(() => {
  const CYR = {
    а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', ђ: 'dj', е: 'e', ж: 'z', з: 'z', и: 'i', ј: 'j', к: 'k', л: 'l',
    љ: 'lj', м: 'm', н: 'n', њ: 'nj', о: 'o', п: 'p', р: 'r', с: 's', т: 't', ћ: 'c', у: 'u', ф: 'f', х: 'h',
    ц: 'c', ч: 'c', џ: 'dz', ш: 's',
  };
  const fold = (s) => {
    let out = '';
    for (const ch of String(s).toLowerCase()) out += CYR[ch] ?? ch;
    return out.replace(/đ/g, 'dj').normalize('NFD').replace(/[̀-ͯ]/g, '');
  };
  const lang = document.documentElement.lang || 'en';

  // On a phone the navigation rows scroll sideways: start with the current page's link in view.
  document.querySelectorAll('.round-nav, .main-nav').forEach((nav) => {
    const here = nav.querySelector('[aria-current]');
    if (here && nav.scrollWidth > nav.clientWidth) {
      nav.scrollLeft = Math.max(0, here.offsetLeft - nav.offsetLeft - (nav.clientWidth - here.offsetWidth) / 2);
    }
  });

  // Light or dark, remembered on this device; until chosen, the system's setting decides.
  const toggle = document.querySelector('[data-theme-toggle]');
  if (toggle) {
    const root = document.documentElement;
    const isDark = () => (root.dataset.theme
      ? root.dataset.theme === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches);
    const label = () => { toggle.textContent = isDark() ? toggle.dataset.light : toggle.dataset.dark; };
    toggle.hidden = false;
    label();
    toggle.addEventListener('click', () => {
      root.dataset.theme = isDark() ? 'light' : 'dark';
      try { localStorage.setItem('theme', root.dataset.theme); } catch (e) { /* private window: this page only */ }
      label();
    });
  }
  const fmt = new Intl.NumberFormat(lang.startsWith('sr') ? 'sr-Latn' : 'en');

  // A station's page on paper, for election day; without scripts the browser's own print does the same.
  document.querySelectorAll('[data-print]').forEach((b) => {
    b.hidden = false;
    b.addEventListener('click', () => window.print());
  });

  // Search on the home page: municipalities and polling places from search.json, loaded on first use. Every result
  // opens its page across all elections.
  const search = document.querySelector('form[data-search]');
  if (search) {
    const input = search.querySelector('input');
    const out = search.querySelector('[data-search-results]');
    const base = search.dataset.base || '';
    let items = null;
    let loading = null;
    let hits = [];
    const load = () => {
      if (!loading) {
        loading = fetch(search.dataset.index)
          .then((r) => r.json())
          .then((j) => {
            const d = search.dataset;
            // [folded label, folded label with former numbers, [label, url, sub-line]]
            const mun = j.m.map((m) => {
              const f = fold(m[0]);
              return [f, f, [m[0], `m/${m[1]}.html`, d.munSub.replace('{n}', m[2])]];
            });
            const st = j.s.map((s) => {
              const m = j.m[s[0]];
              const label = `${m[0]} · ${d.bm} ${s[1]}${s[2] ? ` · ${s[2]}` : ''}`;
              let sub = (s[4] ? d.flagged.replace('{k}', s[4]) : d.clean).replace('{n}', s[5]);
              if (s[6]) sub += ` · ${d.former.replace('{n}', s[6])}`;
              const page = s[3] || `${m[1]}-${s[1].replace(/[^0-9A-Za-z_-]/g, '_')}`;
              const f = fold(label);
              return [f, s[6] ? `${f} ${fold(`${d.bm} ${s[6]}`)}` : f, [label, `s/${page}.html`, sub]];
            });
            items = mun.concat(st);
          })
          .catch(() => { items = []; });
      }
      return loading;
    };
    const render = () => {
      out.textContent = '';
      const q = fold(input.value.trim());
      if (!q || !items) return;
      const words = q.split(/\s+/);
      const numbers = words.filter((w) => /^\d+$/.test(w));
      hits = items.filter(([, f]) => words.every((w) => f.includes(w)));
      if (numbers.length) {  // "zemun 25": station 25 before 125 and 250, and before a place that used to be 25
        const exact = (f) => numbers.every((n) => new RegExp(`(^|\\D)${n}(\\D|$)`).test(f));
        const rank = ([now, all]) => (exact(now) ? 0 : exact(all) ? 1 : 2);
        hits = hits.map((h, i) => [rank(h), i, h]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((x) => x[2]);
      }
      hits = hits.slice(0, 12);
      if (!hits.length) {
        const p = document.createElement('p');
        p.textContent = out.dataset.none;
        out.append(p);
        return;
      }
      const ul = document.createElement('ul');
      hits.forEach(([, , it]) => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = base + it[1];
        a.textContent = it[0];
        li.append(a);
        if (it[2]) {
          const s = document.createElement('span');
          s.className = 'small muted';
          s.textContent = it[2];
          li.append(s);
        }
        ul.append(li);
      });
      out.append(ul);
    };
    input.addEventListener('focus', load, { once: true });
    input.addEventListener('input', () => { load().then(render); });
    search.addEventListener('submit', (e) => {
      e.preventDefault();
      load().then(() => {
        render();
        if (hits.length) location.href = base + hits[0][2][1];
      });
    });
    if (location.hash === '#pretraga') input.focus();
  }

  // The next election on the home page: how many days are left, by the reader's calendar; gone once it has passed.
  document.querySelectorAll('[data-days-until]').forEach((el) => {
    const [y, m, d] = el.dataset.daysUntil.split('-').map(Number);
    const now = new Date();
    const days = Math.round((Date.UTC(y, m - 1, d) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()))
      / 86400000);
    if (days < 0) {
      const box = el.closest('[data-next]');
      if (box) box.hidden = true;
      return;
    }
    const one = lang === 'en' ? days === 1 : days % 10 === 1 && days % 100 !== 11;
    el.textContent = days === 0 ? el.dataset.today : days === 1 ? el.dataset.tomorrow
      : el.dataset.in.replace('{n}', days).replace('{unit}', one ? el.dataset.one : el.dataset.many);
  });

  document.querySelectorAll('input[data-filter]').forEach((input) => {
    const table = document.querySelector(input.dataset.filter);
    if (!table) return;
    const rows = [...table.tBodies[0].rows];
    const texts = rows.map((r) => fold(r.dataset.text || r.textContent));
    input.addEventListener('input', () => {
      const q = fold(input.value.trim());
      rows.forEach((r, i) => { r.hidden = Boolean(q) && !texts[i].includes(q); });
    });
  });

  document.querySelectorAll('form[data-filter-cards]').forEach((form) => {
    const box = document.querySelector(form.dataset.filterCards);
    if (!box) return;
    const cards = [...box.querySelectorAll('.card')];
    const texts = cards.map((c) => fold(c.dataset.text || ''));
    const mun = form.querySelector('[data-f="mun"]');
    const type = form.querySelector('[data-f="type"]');
    const query = form.querySelector('[data-f="q"]');
    const out = form.querySelector('output');
    // "g-paper" and the like pick every kind of flag in a group: the options listed under it
    const inGroup = {};
    type.querySelectorAll('optgroup[data-g]').forEach((og) => {
      inGroup[`g-${og.dataset.g}`] = [...og.querySelectorAll('option')].map((o) => o.value)
        .filter((v) => !v.startsWith('g-'));
    });
    const has = (card, ty) => {
      const types = card.dataset.types.split(' ');
      return inGroup[ty] ? types.some((x) => inGroup[ty].includes(x)) : types.includes(ty);
    };
    const apply = () => {
      const m = mun.value;
      const ty = type.value;
      const q = fold(query.value.trim());
      let shown = 0;
      cards.forEach((c, i) => {
        const ok = (!m || c.dataset.mun === m)
          && (!ty || has(c, ty))
          && (!q || texts[i].includes(q));
        c.hidden = !ok;
        if (ok) shown += 1;
      });
      if (out) out.textContent = out.dataset.shown.replace('{n}', fmt.format(shown));
    };
    const order = form.querySelector('[data-f="order"]');
    if (order) {
      order.addEventListener('change', () => {
        const sorted = [...cards].sort((a, b) => (order.value === 'place'
          ? (a.dataset.place || '').localeCompare(b.dataset.place || '', lang)
          : cards.indexOf(a) - cards.indexOf(b)));
        box.append(...sorted);
      });
    }
    mun.addEventListener('change', apply);
    type.addEventListener('change', apply);
    query.addEventListener('input', apply);
    // #invalid_spike picks a kind of flag; #m-70092 a municipality (links from the pages across elections)
    const wanted = decodeURIComponent(location.hash.slice(1));
    if (wanted && [...type.options].some((o) => o.value === wanted)) type.value = wanted;
    else if (wanted.startsWith('m-') && [...mun.options].some((o) => o.value === wanted.slice(2))) {
      mun.value = wanted.slice(2);
    }
    apply();
  });

  // The table of stations across elections: minimum elections flagged, kind of flag, same check again, search.
  document.querySelectorAll('form[data-filter-rows]').forEach((form) => {
    const box = document.querySelector(form.dataset.filterRows);
    if (!box) return;
    const rows = [...box.querySelectorAll('[data-k]')];
    const texts = rows.map((r) => fold(r.dataset.text || ''));
    const groups = [...box.querySelectorAll('[data-group]')];
    const f = (n) => form.querySelector(`[data-f="${n}"]`);
    const out = form.querySelector('output');
    const apply = () => {
      const ty = f('type').value;
      const same = f('same').checked;
      const q = fold(f('q').value.trim());
      let shown = 0;
      rows.forEach((r, i) => {
        const codes = ((same ? r.dataset.same : r.dataset.types) || '').split(' ').filter(Boolean);
        const ok = (!same || codes.length > 0) && (!ty || codes.includes(ty)) && (!q || texts[i].includes(q));
        r.hidden = !ok;
        if (ok) shown += 1;
      });
      groups.forEach((g) => {
        const visible = g.querySelectorAll('[data-k]:not([hidden])').length;
        g.hidden = visible === 0;
        const c = g.querySelector('[data-count]');
        if (c) c.textContent = c.textContent.replace(/[\d.,]+/, fmt.format(visible));
        if (ty || same || q) g.open = visible > 0 && visible <= 400;
      });
      if (out) out.textContent = out.dataset.shown.replace('{n}', fmt.format(shown));
    };
    const wanted = decodeURIComponent(location.hash.slice(1));
    if (wanted && [...f('type').options].some((o) => o.value === wanted)) f('type').value = wanted;
    document.querySelectorAll('[data-set-same]').forEach((a) => a.addEventListener('click', () => {
      f('type').value = a.dataset.setSame;
      f('same').checked = true;
      apply();
    }));
    ['type', 'same'].forEach((n) => f(n).addEventListener('change', apply));
    f('q').addEventListener('input', apply);
    apply();
  });

  // A long list of polling stations: the first rows, and a button under them for the rest. A link to a station
  // further down (#bm-23) opens the whole list.
  document.querySelectorAll('table[data-first]').forEach((table) => {
    const first = Number(table.dataset.first);
    const rows = [...table.tBodies[0].rows];
    if (rows.length <= first + 5) return;  // a button for a handful of rows is more work than the rows
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button secondary more';
    if (table.id) button.setAttribute('aria-controls', table.id);
    let open = false;
    const show = (all) => {
      open = all;
      rows.forEach((r, i) => { r.hidden = !all && i >= first; });
      button.textContent = all ? table.dataset.less : table.dataset.more;
      button.setAttribute('aria-expanded', String(all));
    };
    button.addEventListener('click', () => {
      show(!open);
      if (!open) button.scrollIntoView({ block: 'nearest' });
    });
    (table.closest('.table-wrap') || table).after(button);
    const target = () => {
      const id = decodeURIComponent(location.hash.slice(1));
      return id ? rows.find((r) => r.id === id) : undefined;
    };
    const start = target();
    show(Boolean(start) && rows.indexOf(start) >= first);
    window.addEventListener('beforeprint', () => show(true));  // on paper, every station
    window.addEventListener('hashchange', () => {
      const row = target();
      if (row && row.hidden) {
        show(true);
        row.scrollIntoView();
      }
    });
  });

  // The whole table of votes as a CSV file, made here from the table on the page: plain numbers, the lists' names
  // in the header, and each station's name from the list of stations.
  document.querySelectorAll('button[data-csv]').forEach((button) => {
    const table = document.querySelector(button.dataset.csv);
    if (!table || typeof Blob === 'undefined') return;
    const names = document.querySelector(button.dataset.names);
    button.hidden = false;
    const quote = (v) => (/[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
    const number = (v) => v.replace(/[^\d-]/g, '');
    button.addEventListener('click', () => {
      const lines = [...table.rows].map((row, n) => {
        const cells = [...row.cells];
        if (n === 0) {
          return [cells[0].textContent.trim(), button.dataset.station,
            ...cells.slice(1).map((c) => `${c.textContent.trim()}. ${c.title}`)];
        }
        const no = cells[0].textContent.trim();
        const place = names && names.querySelector(`tr[id="bm-${no}"] td:nth-child(2) a`);
        return [no, place ? place.textContent.trim() : '', ...cells.slice(1).map((c) => number(c.textContent))];
      });
      const blob = new Blob([`﻿${lines.map((l) => l.map(quote).join(',')).join('\r\n')}\r\n`],
        { type: 'text/csv;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = button.dataset.file;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  });

  // Click a column header marked data-sort: largest first, click again for smallest first.
  document.querySelectorAll('table').forEach((table) => {
    const heads = [...table.querySelectorAll('thead th')];
    heads.forEach((th, col) => {
      if (!th.hasAttribute('data-sort')) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sort';
      button.append(...th.childNodes);
      th.append(button);
      button.addEventListener('click', () => {
        const desc = th.getAttribute('aria-sort') !== 'descending';
        heads.forEach((h) => h.removeAttribute('aria-sort'));
        th.setAttribute('aria-sort', desc ? 'descending' : 'ascending');
        const body = table.tBodies[0];
        const value = (r) => {
          const v = parseFloat(r.cells[col]?.dataset.v);
          return Number.isNaN(v) ? null : v;
        };
        const rows = [...body.rows];
        rows.sort((a, b) => {
          const x = value(a);
          const y = value(b);
          if (x === null || y === null) return (x === null) - (y === null);  // empty values last
          return desc ? y - x : x - y;
        });
        body.append(...rows);
      });
    });
  });
})();
