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
    const apply = () => {
      const m = mun.value;
      const ty = type.value;
      const q = fold(query.value.trim());
      let shown = 0;
      cards.forEach((c, i) => {
        const ok = (!m || c.dataset.mun === m)
          && (!ty || c.dataset.types.split(' ').includes(ty))
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
    const wanted = decodeURIComponent(location.hash.slice(1));
    if (wanted && [...type.options].some((o) => o.value === wanted)) type.value = wanted;
    apply();
  });

  // The table of stations across elections: minimum elections flagged, kind of flag, same check again, search.
  document.querySelectorAll('form[data-filter-rows]').forEach((form) => {
    const table = document.querySelector(form.dataset.filterRows);
    if (!table) return;
    const rows = [...table.tBodies[0].rows];
    const texts = rows.map((r) => fold(r.dataset.text || ''));
    const f = (n) => form.querySelector(`[data-f="${n}"]`);
    const out = form.querySelector('output');
    const apply = () => {
      const min = Number(f('min').value || 2);
      const ty = f('type').value;
      const same = f('same').checked;
      const q = fold(f('q').value.trim());
      let shown = 0;
      rows.forEach((r, i) => {
        const codes = ((same ? r.dataset.same : r.dataset.types) || '').split(' ').filter(Boolean);
        const ok = Number(r.dataset.k) >= min && (!same || codes.length > 0)
          && (!ty || codes.includes(ty)) && (!q || texts[i].includes(q));
        r.hidden = !ok;
        if (ok) shown += 1;
      });
      if (out) out.textContent = out.dataset.shown.replace('{n}', fmt.format(shown));
    };
    const wanted = decodeURIComponent(location.hash.slice(1));
    if (wanted && [...f('type').options].some((o) => o.value === wanted)) {
      f('type').value = wanted;
      f('min').value = '1';
    }
    document.querySelectorAll('[data-set-same]').forEach((a) => a.addEventListener('click', () => {
      f('type').value = a.dataset.setSame;
      f('same').checked = true;
      f('min').value = '2';
      apply();
    }));
    ['min', 'type', 'same'].forEach((n) => f(n).addEventListener('change', apply));
    f('q').addEventListener('input', apply);
    apply();
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
