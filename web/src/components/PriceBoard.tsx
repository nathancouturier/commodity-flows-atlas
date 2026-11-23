/**
 * Price board: every price series of the atlas on one table, grouped by family, with its last value and date,
 * its change over 1 week (daily series), 1 month, 3 months, since the start of the year and 1 year, and where the
 * last value stands in its 52-week range. The figures are precomputed by pipeline/prices/build_prices.py from the
 * published values (arithmetic, not an estimate), so the board loads nothing but the price index.
 * Opened from the price drawer; a row opens its series on the chart.
 */
import { useEffect, useMemo, useState } from 'preact/hooks';
import { sourceLabel } from '../lib/data';
import { GROUP_LABEL, GROUP_ORDER, FREQ_WORD, fmtPct, fmtPrice, groupOf, isLate, priceIndex, type PriceGroup, type PriceMeta } from '../lib/prices';
import { fmtDate, loadStatus, type Freshness } from '../lib/status';
import { FAMILY_COLOR } from '../lib/format';
import { CloseIcon } from './ui';
import '../styles/price-board.css';

type Key = 'name' | 'w' | 'm' | 'q' | 'ytd' | 'y' | 'pos';
const COLUMNS: { key: Key; label: string; title: string; cls: string }[] = [
  { key: 'w', label: '1 week', title: 'Change over 1 week (daily series only)', cls: 'pb-c-w' },
  { key: 'm', label: '1 month', title: 'Change over 1 month', cls: '' },
  { key: 'q', label: '3 months', title: 'Change over 3 months', cls: 'pb-c-q' },
  { key: 'ytd', label: 'Year to date', title: 'Change since the last observation of the previous year', cls: 'pb-c-ytd' },
  { key: 'y', label: '1 year', title: 'Change over 1 year', cls: '' },
  { key: 'pos', label: '52 weeks', title: 'Where the last value stands between the lowest and the highest of the last 52 weeks (12 months for a monthly series)', cls: 'pb-c-rng' },
];

/** The publisher, and what its published values are, of the sources on the board (which shows no source per row). */
const SOURCE_WORDS: Record<string, { by: string; values: string }> = {
  'wb-pink': { by: 'World Bank', values: 'World Bank monthly averages' },
  'eia-spot': { by: 'EIA', values: 'EIA daily spot prices' },
  bls: { by: 'BLS', values: 'BLS monthly producer price index' },
  dallasfed: { by: 'Dallas Fed', values: 'Dallas Fed monthly index' },
  nyfed: { by: 'New York Fed', values: 'New York Fed monthly index' },
};
const andList = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);

function value(m: PriceMeta, key: Key): number | string | null {
  if (key === 'name') return m.name;
  const st = m.stats;
  if (!st) return null;
  if (key === 'pos') return st.rng?.pos ?? null;
  return st.chg?.[key] ?? null;
}

function Change({ v }: { v: number | null | undefined }) {
  if (v == null) return <span class="pb-none">—</span>;
  return <span class={v > 0 ? 'pb-up' : v < 0 ? 'pb-dn' : ''}>{fmtPct(v)}</span>;
}

/** "Prices to 17 Nov 2026 (EIA, daily) and Oct 2026 (World Bank, monthly) · checked 22 Nov 2026", from data/_status/updates.json. */
export function PriceStatusLine() {
  const [rows, setRows] = useState<Freshness[] | null>(null);
  useEffect(() => {
    let live = true;
    loadStatus()
      .then((v) => live && setRows(v.rows))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  if (!rows) return null;
  const eia = rows.find((r) => r.key === 'eia-spot');
  const wb = rows.find((r) => r.key === 'wb-pink');
  const parts = [eia?.dataTo ? `${eia.dataTo} (EIA, daily)` : null, wb?.dataTo ? `${wb.dataTo} (World Bank, monthly)` : null].filter(Boolean);
  if (!parts.length) return null;
  const checked = [eia?.checked, wb?.checked].filter((x): x is string => !!x).sort().pop();
  return (
    <span class="pb-status">
      Prices to {parts.join(' and ')}
      {checked ? ` · checked ${fmtDate(checked)}` : ''}
    </span>
  );
}

export function PriceBoard(props: { onClose: () => void; onOpen: (id: string) => void }) {
  const [group, setGroup] = useState<PriceGroup | 'all'>('all');
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: 'name', dir: 1 });
  const idx = priceIndex.value;
  const listed = useMemo(() => idx.filter((m) => !m.hidden && !m.closed && m.stats && m.freq !== 'A'), [idx]);

  const sections = useMemo(() => {
    const out: { g: PriceGroup; rows: PriceMeta[] }[] = [];
    for (const g of GROUP_ORDER) {
      if (group !== 'all' && group !== g) continue;
      const rows = listed.filter((m) => groupOf(m) === g);
      if (!rows.length) continue;
      if (sort.key !== 'name') {
        // a series without the figure goes last, whatever the direction
        rows.sort((a, b) => {
          const x = value(a, sort.key) as number | null;
          const y = value(b, sort.key) as number | null;
          if (x == null || y == null) return x == null && y == null ? 0 : x == null ? 1 : -1;
          return (x - y) * sort.dir;
        });
      } else if (sort.dir < 0) rows.reverse();
      out.push({ g, rows });
    }
    return out;
  }, [listed, group, sort]);

  const present = GROUP_ORDER.filter((g) => listed.some((m) => groupOf(m) === g));
  const shown = sections.flatMap((x) => x.rows);
  const shownSources = [...new Set(shown.map((m) => m.s))];
  // the freight indicators are not World Bank or EIA prices: on their tab the footer names their own publishers and month
  const freightTo = group === 'freight' ? shown.map((m) => m.stats!.last.t).sort().pop() : undefined;
  const toggle = (key: Key) => setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'name' ? 1 : -1 }));
  const aria = (key: Key) => (sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none');
  const mark = (key: Key) => (sort.key === key ? (sort.dir === 1 ? ' ↑' : ' ↓') : '');

  return (
    <div class="pb" role="region" aria-label="Price board">
      <div class="pb-head">
        <div>
          <b>Price board</b>
          <span class="pb-sub">{listed.length} series · last value and changes</span>
        </div>
        <button class="pb-back tc-btn" onClick={props.onClose}>
          Back to chart
        </button>
        <button class="pd-close" aria-label="Close the price board" onClick={props.onClose}>
          <CloseIcon />
        </button>
      </div>
      <div class="pb-tools">
        <div class="pb-groups" role="group" aria-label="Family">
          <button class="tc-btn" aria-pressed={group === 'all'} onClick={() => setGroup('all')}>
            All
          </button>
          {present.map((g) => (
            <button key={g} class="tc-btn" aria-pressed={group === g} onClick={() => setGroup(g)}>
              {GROUP_LABEL[g]}
            </button>
          ))}
        </div>
        <label class="pb-sort">
          <span>Sort by</span>
          <select
            value={sort.key}
            onChange={(e) => setSort({ key: (e.target as HTMLSelectElement).value as Key, dir: (e.target as HTMLSelectElement).value === 'name' ? 1 : -1 })}
          >
            <option value="name">Name</option>
            {COLUMNS.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
          <button class="tc-btn" onClick={() => setSort({ ...sort, dir: sort.dir === 1 ? -1 : 1 })} aria-label={sort.dir === 1 ? 'Ascending: switch to descending' : 'Descending: switch to ascending'}>
            {sort.dir === 1 ? '↑' : '↓'}
          </button>
        </label>
      </div>
      <div class="pb-scroll">
        {!listed.length ? (
          <div class="pd-empty">Loading the price index…</div>
        ) : (
          <table class="pb-table">
            <thead>
              <tr>
                <th scope="col" aria-sort={aria('name')}>
                  <button class="pb-th" onClick={() => toggle('name')}>
                    Series{mark('name')}
                  </button>
                </th>
                <th scope="col" class="pb-last">
                  Last
                </th>
                {COLUMNS.map((c) => (
                  <th key={c.key} scope="col" class={`pb-num ${c.cls}`} aria-sort={aria(c.key)} title={c.title}>
                    <button class="pb-th" onClick={() => toggle(c.key)}>
                      {c.label}
                      {mark(c.key)}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            {sections.map(({ g, rows }) => (
              <tbody key={g}>
                <tr class="pb-grp">
                  <th colSpan={COLUMNS.length + 2} scope="colgroup" style={{ color: g === 'index' ? undefined : FAMILY_COLOR[g] }}>
                    {GROUP_LABEL[g]}
                  </th>
                </tr>
                {rows.map((m) => {
                  const st = m.stats!;
                  const late = isLate(m);
                  return (
                    <tr key={m.id} class={late ? 'pb-late' : ''}>
                      <th scope="row">
                        <button class="pb-name" onClick={() => props.onOpen(m.id)} title={`Open ${m.name} on the chart · ${sourceLabel(m.s)}${m.basis ? ' · ' + m.basis : ''}`}>
                          {m.name}
                        </button>
                        <small class="pb-unit">
                          {m.unit} · {FREQ_WORD[m.freq]}
                        </small>
                      </th>
                      <td class="pb-last num" title={late ? `No value since ${fmtDate(st.last.t)}: this series is late` : undefined}>
                        {fmtPrice(st.last.v)}
                        <small>
                          {fmtDate(st.last.t)}
                          {late ? ' · late' : ''}
                        </small>
                      </td>
                      {COLUMNS.slice(0, 5).map((c) => (
                        <td key={c.key} class={`pb-num num ${c.cls}`}>
                          <Change v={st.chg?.[c.key as 'w' | 'm' | 'q' | 'ytd' | 'y']} />
                        </td>
                      ))}
                      <td class="pb-num pb-c-rng" title={st.rng ? `52-week range ${fmtPrice(st.rng.lo)} to ${fmtPrice(st.rng.hi)}` : undefined}>
                        {st.rng?.pos == null ? (
                          <span class="pb-none">—</span>
                        ) : (
                          <span class="pb-bar" role="img" aria-label={`${Math.round(st.rng.pos * 100)}% of the way from the 52-week low to the high`}>
                            <i style={{ left: `${st.rng.pos * 100}%` }} />
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            ))}
          </table>
        )}
      </div>
      <div class="pb-foot">
        {freightTo ? (
          <span class="pb-status">
            Freight indicators to {fmtDate(freightTo)} ({andList(shownSources.map((x) => SOURCE_WORDS[x]?.by ?? sourceLabel(x)))}, monthly)
          </span>
        ) : (
          <PriceStatusLine />
        )}{' '}
        · Changes are arithmetic on the published values ({andList(shownSources.map((x) => SOURCE_WORDS[x]?.values ?? sourceLabel(x)))}), each against the last
        observation on or before the same date; no reference, no figure{shown.some((m) => /deviation/i.test(m.unit)) ? ', and none for a deviation from a trend or an average, which crosses zero' : ''}. The 52-week bar is the last 12 months for monthly series.
      </div>
    </div>
  );
}
