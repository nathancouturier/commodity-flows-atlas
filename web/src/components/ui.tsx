/** Small shared UI primitives: switches, ranked bars, KPI tiles, source lines. */
import type { ComponentChildren } from 'preact';
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import type { Alert, Chokepoint, Fig, HistTable, InfraType, Ranked, StatusNote } from '../types';
import { commodityMeta, countryName, isCountry, load, sourceLabel, sources } from '../lib/data';
import { trendOf } from '../lib/tableYears';
import { atlasKind, fmt, fmtEst, pct, fig as fmtFig } from '../lib/format';
import { GROUP_LABEL, loadChokepoints, loadEvents } from '../lib/freight';
import { select, year } from '../lib/store';
import { statusClassOf, statusText } from '../lib/infra';
import { downloadRanked, rankedSources } from '../lib/rankedCsv';
import { gapLabel, gapTitle } from '../lib/gapRow';
import { CsvAction } from './CsvAction';
import { openAbout } from './AboutHost';
import { checkedLabel } from '../lib/events';
import '../styles/lane-table.css';
import '../styles/tables-by-year.css';
import '../styles/section-fold.css';

export function Switch(props: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string; desc?: string }) {
  return (
    <button
      class="toggle-row"
      role="switch"
      aria-checked={props.checked}
      onClick={() => props.onChange(!props.checked)}
      title={props.hint}
    >
      <span class="toggle-text">
        <span>{props.label}</span>
        {props.desc && <small class="toggle-desc">{props.desc}</small>}
      </span>
      <span class="switch" aria-hidden="true" />
    </button>
  );
}

/**
 * A block of a page. With `fold`, its title is a button that opens and closes it in place, closed at first unless `open`;
 * nothing is remembered. With `latest`, a History year on the timeline adds "latest" to the title: the block does not follow it.
 */
export function Section(props: { title: ComponentChildren; children: ComponentChildren; aside?: ComponentChildren; fold?: boolean; open?: boolean; latest?: boolean }) {
  const [open, setOpen] = useState(!!props.open);
  const tag = props.latest && year.value != null ? <span class="year-tag">latest</span> : null;
  const aside = tag && props.aside ? <span class="sec-aside">{tag}{props.aside}</span> : (tag ?? props.aside);
  if (!props.fold)
    return (
      <section class="section">
        <h3 class="section-title">
          <span>{props.title}</span>
          {aside}
        </h3>
        {props.children}
      </section>
    );
  // the title stays the only text of the first span: a table's CSV file is named after it (rankedCsv tableTitle)
  return (
    <section class={`section sec-fold${open ? '' : ' sec-folded'}`}>
      <h3 class="section-title">
        <span class="sec-fold-t">
          <button class="sec-fold-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
            {props.title}
          </button>
        </span>
        {aside}
      </h3>
      {open && props.children}
    </section>
  );
}

/** The atlas's own figures (source id `atlas`) are explained in the Method tab of the About window, not on an outside page. */
export function MethodLink(props: { label: string }) {
  return (
    <button class="src-method" title="How the atlas computes its own figures: the Method tab of About" onClick={(e) => openAbout('method', e.currentTarget)}>
      {props.label}
    </button>
  );
}

/** "Source: USGS Mineral Commodity Summaries · 2024" with a link to the source page. */
export function SourceLine(props: { s?: string; y?: number | string; n?: string; mark?: ComponentChildren }) {
  if (!props.s) return null;
  const src = sources.value[props.s];
  return (
    <div class="src-line" data-src={props.s} data-y={props.y != null ? String(props.y) : undefined}>
      Source:{' '}
      {props.s === 'atlas' ? (
        <MethodLink label={sourceLabel('atlas')} />
      ) : src ? (
        <a href={src.url} target="_blank" rel="noopener">
          {src.name}
        </a>
      ) : (
        props.s
      )}
      {props.y != null && <> · {props.y}</>}
      {props.n && <> · {props.n}</>}
      {props.mark}
    </div>
  );
}

/** Short publisher label for footnotes ("CEPII BACI", "USGS", "EIA"...). */
const SHORT_SOURCE: Record<string, string> = {
  baci: 'CEPII BACI',
  'usgs-mcs': 'USGS',
  'usda-psd': 'USDA',
  'eia-intl': 'EIA',
  'eia-spot': 'EIA',
  'eia-tie': 'EIA',
  'eia-chokepoints': 'EIA',
  'wb-pink': 'World Bank',
  faostat: 'FAOSTAT',
  wna: 'World Nuclear Association',
  portwatch: 'IMF PortWatch',
  'portwatch-port-traffic': 'IMF PortWatch',
  atlas: 'Atlas estimate',
  'port-authorities': 'port authorities',
  'company-reports': 'company reports',
  'operator-reports': 'operator reports',
  'eia-refinery-capacity': 'EIA',
  'giignl-2026': 'GIIGNL',
  'census-exports': 'US Census Bureau',
  comtrade: 'UN Comtrade',
  'qld-coal-sales': 'Queensland Government',
  'trade-press': 'trade press',
  wikipedia: 'Wikipedia',
};
/** One short label per publisher, so that two sources of one publisher share an entry of a sources line. */
const SHORT_PUBLISHER: Record<string, string> = {
  'U.S. Energy Information Administration': 'EIA',
  'U.S. Geological Survey': 'USGS',
  'U.S. Geological Survey, National Minerals Information Center': 'USGS',
  'US National Geospatial-Intelligence Agency': 'NGA',
};
export function shortSource(id: string): string {
  const pub = sources.value[id]?.publisher;
  return SHORT_SOURCE[id] ?? (pub ? SHORT_PUBLISHER[pub] ?? pub : id);
}

/** "Sources: CEPII BACI 2024 · USGS 2024, 2025 · EIA 2023": every distinct source and year of a block. */
export function SourcesLine(props: { items: { s: string; y?: number | string }[]; n?: string }) {
  const by = new Map<string, { s: string; ys: Set<string> }>();
  for (const it of props.items) {
    if (!it.s) continue;
    const key = shortSource(it.s);
    const e = by.get(key) ?? { s: it.s, ys: new Set<string>() };
    if (it.y != null) e.ys.add(String(it.y));
    by.set(key, e);
  }
  if (!by.size) return null;
  const list = [...by.entries()];
  // data-srcs: the sources and years of the line, read by "Copy citation" (lib/cite.ts)
  return (
    <div class="src-line" data-srcs={JSON.stringify(list.map(([, e]) => [e.s, [...e.ys].sort()]))}>
      {list.length > 1 ? 'Sources: ' : 'Source: '}
      {list.map(([label, e], i) => {
        const src = sources.value[e.s];
        const ys = [...e.ys].sort();
        return (
          <>
            {i > 0 && ' · '}
            {e.s === 'atlas' ? (
              <MethodLink label={label} />
            ) : src ? (
              <a href={src.url} target="_blank" rel="noopener" title={src.name}>
                {label}
              </a>
            ) : (
              label
            )}
            {ys.length > 0 && <> {ys.join(', ')}</>}
          </>
        );
      })}
      {props.n && <> · {props.n}</>}
    </div>
  );
}

// ---------------------------------------------------------------- active disruptions

let alertsPromise: Promise<Alert[]> | null = null;
function useAlerts(): Alert[] {
  const [a, setA] = useState<Alert[]>([]);
  useEffect(() => {
    alertsPromise ??= load<Alert[]>('freight/alerts.json').catch(() => []);
    let live = true;
    alertsPromise.then((r) => live && setA(r));
    return () => {
      live = false;
    };
  }, []);
  return a;
}

let chokepointsPromise: Promise<Chokepoint[]> | null = null;
/** The chokepoint records, loaded once (the share of a commodity's seaborne trade through a passage is read from them). */
function useChokepoints(wanted: boolean): Chokepoint[] {
  const [c, setC] = useState<Chokepoint[]>([]);
  useEffect(() => {
    if (!wanted) return;
    chokepointsPromise ??= loadChokepoints().catch(() => []);
    let live = true;
    chokepointsPromise.then((r) => live && setC(r));
    return () => {
      live = false;
    };
  }, [wanted]);
  return c;
}

const MON_S = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function sinceLabel(s: string): string {
  const [y, m] = s.split('-');
  return m ? `${MON_S[Number(m) - 1] ?? m} ${y}` : y;
}

/** "15 Nov 2026" from an ISO date. */
function dayLabel(s: string): string {
  const [y, m, d] = s.split('-');
  return d ? `${Number(d)} ${MON_S[Number(m) - 1] ?? m} ${y}` : sinceLabel(s);
}

const SEVERITY_WORD = { high: 'High', medium: 'Medium', low: 'Low' } as const;

/** "4% of the 2023 average": the 28-day transits as a share of the reference. */
function ofReference(m: Alert['measures'][number]): string | null {
  const { now, avg2023 } = m.transits;
  if (now == null || !avg2023) return null;
  const p = (100 * now) / avg2023;
  return `${p < 1 ? '<1' : Math.round(p)}% of the ${m.refYear} average`;
}

/** "96% below the same days a year earlier", or null without a figure. */
function againstYear(m: Alert['measures'][number]): string | null {
  if (m.gapYear == null) return null;
  const g = Math.round(Math.abs(m.gapYear));
  if (g === 0) return 'level with the same days a year earlier';
  return `${g}% ${m.gapYear < 0 ? 'below' : 'above'} the same days a year earlier`;
}

/** What the Atlas estimates of one commodity's seaborne trade say about one passage, "At least 27%, up to 32% of seaborne crude oil crossed it in 2024". */
function exposureText(k: string, e: NonNullable<Chokepoint['estimates']>[number]): string {
  const name = e.p && e.p !== e.k && GROUP_LABEL[e.p] ? GROUP_LABEL[e.p].replace(/ \(Atlas estimate\)$/, '') : (commodityMeta(k)?.name ?? k);
  const what = /^[A-Z][a-z]/.test(name) ? name[0].toLowerCase() + name.slice(1) : name;
  const lo = fmtEst(e.f.v, true);
  const hi = e.hi && fmtEst(e.hi.v, true) !== lo ? fmtEst(e.hi.v, true) : null;
  // no "at least" in front of a zero: no cargo has to cross, some may
  if (hi && e.mt?.[0] === 0) return `Up to ${hi}% of seaborne ${what}`;
  return `At least ${e.f.v === 0 && e.mt?.[0] ? '<0.1' : lo}%${hi ? `, up to ${hi}%` : ''} of seaborne ${what}`;
}

/** "the Strait of Hormuz", "Bab el-Mandeb": a passage's name inside a sentence (the part in brackets left out). */
function inSentence(name: string): string {
  const short = name.replace(/ \(.*\)$/, '');
  return /^(Bab |Cape Horn)/.test(short) ? short : `the ${short}`;
}

/** The figure line of one passage: "Bab el-Mandeb: transits 36% of the 2023 average, 28 days to 15 Nov 2026". */
function PassageFigure(props: { m: Alert['measures'][number]; full?: boolean; chip?: { text: string; title: string } | null }) {
  const { m, full, chip } = props;
  const ref = ofReference(m);
  const yr = againstYear(m);
  const short = m.name.replace(/ \(.*\)$/, '');
  const mt = m.mt.now != null ? ` · about ${fmt(m.mt.now)} Mt of cargo` : '';
  // data-src: read by "Copy citation" (lib/cite.ts), like a source line
  return (
    <div class="alert-pass-fig" data-src={m.s} data-y={m.to.slice(0, 4)}>
      {chip && (
        <>
          <span class="alert-sev" title={chip.title}>
            {chip.text}
          </span>{' '}
        </>
      )}
      {ref ? (
        <>
          <b>{short}:</b> transits <b class="num">{ref}</b>
          {full && yr && <> · {yr}</>}
        </>
      ) : (
        <>
          <b>{short}:</b> {yr ?? 'no comparison available'}
        </>
      )}
      <span
        class="alert-pass-sub"
        title="Transits and estimated cargo of the vessels IMF PortWatch counts at the passage, summed over the window. Data adapted from IMF PortWatch."
      >
        {' '}
        · {m.days} days to {dayLabel(m.to)}
        {full && m.transits.now != null && <> · {fmt(m.transits.now)} transits</>}
        {full && mt} · {shortSource(m.s)}
      </span>
    </div>
  );
}

/** What the Atlas estimates say about one commodity and one passage: "At least 27%, up to 32% of seaborne crude oil crossed the Strait of Hormuz in 2024." */
function ExposureLine(props: { k: string; m: Alert['measures'][number]; e: NonNullable<Chokepoint['estimates']>[number] }) {
  const { k, m, e } = props;
  return (
    <div class="alert-expo" data-src={e.f.s} data-y={String(e.f.y)}>
      {exposureText(k, e)} crossed{' '}
      <button class="alert-pass-link" onClick={() => select({ kind: 'chokepoint', id: m.chokepoint })}>
        {inSentence(m.name)}
      </button>{' '}
      in {e.f.y}. <EstMark />
    </div>
  );
}

/** "High: 64% below 2023" (the severity word and the rule that gave it), with the passage when it is not the one shown. */
function severityLine(a: Alert, shownPassage: string): string | null {
  if (!a.severity) return null;
  const word = SEVERITY_WORD[a.severity];
  const d = a.decidedBy;
  if (!d) return word;
  const g = Math.round(Math.abs(d.gap));
  const rule = g === 0 ? `level with ${d.refYear}` : `${g}% ${d.gap < 0 ? 'below' : 'above'} ${d.refYear}`;
  return `${word}: ${rule}${d.chokepoint !== shownPassage ? ` at ${d.name.replace(/ \(.*\)$/, '')}` : ''}`;
}

/**
 * Dated disruption banners. Alerts are matched by commodity, country, or chokepoint ids;
 * `status` are lane/route-specific notes, de-duplicated against the alerts by event id.
 * A banner is compact: the title, the severity with its rule ("High: 64% below 2023"), the worst passage in one line with the
 * date of its last observation (IMF PortWatch) and, on a commodity page, the commodity's exposure to that passage. "Details"
 * unfolds the rest: the text, the other passages and their windows, the date the text was checked against its source, how the
 * commodities and countries of the banner were derived, and the reason of any country added by hand.
 * The events of a commodity, route or country are a section of their own further down the page (EventList).
 */
type AlertProps = { commodity?: string; country?: string; route?: string; chokepoints?: string[]; status?: StatusNote[]; expanded?: boolean };

function CollapsedAlerts(props: AlertProps & { count: number; high: boolean; titles: string[] }) {
  const [open, setOpen] = useState(false);
  if (open) return <AlertList {...props} expanded />;
  return (
    <button class={`alert alert-${props.high ? 'high' : 'medium'} alert-collapsed`} onClick={() => setOpen(true)} aria-expanded="false">
      <b>Active disruptions ({props.count})</b>
      <span>{props.titles.join(' · ')}</span>
      <span class="alert-more">Show</span>
    </button>
  );
}

/** "Open the event" for an alert with one event; "Open the events" with the title of each when it has several (the main one first). */
function AlertEventLinks({ ids }: { ids: string[] }) {
  const [titles, setTitles] = useState<Map<string, string>>(new Map());
  const many = ids.length > 1;
  useEffect(() => {
    if (!many) return;
    let live = true;
    loadEvents().then((l) => live && setTitles(new Map(l.map((e) => [e.id, e.title]))), () => undefined);
    return () => {
      live = false;
    };
  }, [many]);
  if (!many) return <button onClick={() => select({ kind: 'event', id: ids[0] })}>Open the event</button>;
  return (
    <div class="alert-evs">
      <span class="muted">Open the events</span>
      {ids.map((id) => (
        <button key={id} onClick={() => select({ kind: 'event', id })}>{titles.get(id) ?? id}</button>
      ))}
    </div>
  );
}

function AlertCard(props: { a: Alert; cps: string[]; commodity?: string; chks: Chokepoint[] }) {
  const { a, cps, commodity: k, chks } = props;
  const [open, setOpen] = useState(false);
  // on a passage page the figures are those of that passage; elsewhere the passage that decided the severity comes first
  const own = a.measures.filter((m) => cps.includes(m.chokepoint));
  const ordered = [...a.measures].sort((x, y) => Number(y.chokepoint === a.decidedBy?.chokepoint) - Number(x.chokepoint === a.decidedBy?.chokepoint));
  const shown = own.length ? own : ordered;
  const first = shown[0];
  const estOf = (m: Alert['measures'][number]) => (k ? (chks.find((c) => c.id === m.chokepoint)?.estimates ?? []).filter((e) => e.k === k) : []);
  const exposures = a.measures.flatMap((m) => estOf(m).map((e) => ({ m, e })));
  // one exposure line in the banner: the passage shown when the commodity has an estimate there, else the passage with the largest share
  const lead = (first && exposures.find((x) => x.m === first)) ?? [...exposures].sort((x, y) => y.e.f.v - x.e.f.v)[0];
  const rest = exposures.filter((x) => x !== lead);
  const sev = severityLine(a, first?.chokepoint ?? '');
  const checked = checkedLabel(a.checked, dayLabel);
  const added = a.override?.addCountries ?? [];
  return (
    <div class={`alert alert-${a.severity ?? 'low'}`} role="note">
      <div class="alert-head">
        <b>{a.title}</b>
        <span class="alert-links">
          <button onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? 'Hide details' : 'Details'}
          </button>
          <a href={a.src} target="_blank" rel="noopener">
            Source ↗
          </a>
        </span>
      </div>
      {first && <PassageFigure m={first} chip={sev ? { text: sev, title: a.severityNote } : null} />}
      {lead && <ExposureLine k={k!} m={lead.m} e={lead.e} />}
      {open && (
        <div class="alert-det">
          <p>{a.text}</p>
          <p class="muted">
            Since {sinceLabel(a.since)}. {a.severityNote}
          </p>
          {a.measures.map((m) => (
            <PassageFigure key={m.chokepoint} m={m} full />
          ))}
          {rest.length > 0 && (
            <>
              {rest.map(({ m, e }) => (
                <ExposureLine key={`${m.chokepoint}-${e.k}-${e.p ?? ''}`} k={k!} m={m} e={e} />
              ))}
              <div class="alert-note muted">These passages are on the same routes: the shares are not additive.</div>
            </>
          )}
          <p class="muted">
            {checked ?? 'The text of this banner has not been checked against its source.'}
            {a.also?.map((x) => (
              <span key={x.url}>
                {' · '}
                <a href={x.url} target="_blank" rel="noopener">
                  {x.label} ↗
                </a>
              </span>
            ))}
          </p>
          <p class="muted">
            {a.derived}
            {added.length > 0 && (
              <>
                {' '}
                Named by hand: {added.map((c) => countryName(c)).join(', ')}. {a.override?.reason}
              </>
            )}
          </p>
          <div class="alert-links">
            <AlertEventLinks ids={a.events ?? [a.event]} />
          </div>
        </div>
      )}
    </div>
  );
}

function AlertList(props: AlertProps) {
  const all = useAlerts();
  const cps = props.chokepoints ?? [];
  const hit = all.filter(
    (a) =>
      (props.commodity != null && a.commodities.includes(props.commodity)) ||
      (props.country != null && a.countries.includes(props.country)) ||
      cps.some((c) => a.chokepoints.includes(c)),
  );
  const chks = useChokepoints(props.commodity != null && hit.length > 0);
  const seen = new Set(hit.flatMap((a) => a.events ?? [a.event]));
  const notes = (props.status ?? []).filter((n) => {
    const key = n.event ?? n.text;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  // high severity first
  const rank = { high: 0, medium: 1, low: 2 } as const;
  hit.sort((a, b) => (rank[a.severity ?? 'low'] ?? 2) - (rank[b.severity ?? 'low'] ?? 2));
  if (!hit.length && !notes.length) return null;
  const total = hit.length + notes.length;
  if (total > 1 && !props.expanded) {
    // several disruptions: one compact row, expandable, so the tables stay above the fold
    return <CollapsedAlerts {...props} count={total} high={hit.some((a) => a.severity === 'high')} titles={hit.map((a) => a.title)} />;
  }
  return (
    <div class="alerts">
      {hit.map((a) => (
        <AlertCard key={a.id} a={a} cps={cps} commodity={props.commodity} chks={chks} />
      ))}
      {notes.map((n, i) => (
        <div class="alert alert-medium" role="note" key={'n' + i}>
          <p>{n.text}</p>
          {n.event && (
            <div class="alert-links">
              <button onClick={() => select({ kind: 'event', id: n.event! })}>Details</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function AlertBanners(props: AlertProps) {
  return <AlertList {...props} />;
}

/** Smallest size a key figure shrinks to before it is allowed to wrap, px. */
const KPI_MIN_PX = 12;

/**
 * A key figure stays on one line: when it is wider than its card it shrinks to fit, and only below
 * KPI_MIN_PX does it wrap (a figure is never cut). Refits when the card changes width.
 */
function useFitOneLine(text: string) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let lastW = -1;
    const fit = () => {
      lastW = el.clientWidth;
      el.style.fontSize = '';
      el.style.whiteSpace = 'nowrap';
      if (el.scrollWidth <= el.clientWidth) {
        el.style.whiteSpace = '';
        return;
      }
      const full = parseFloat(getComputedStyle(el).fontSize);
      const px = Math.floor(((full * el.clientWidth) / el.scrollWidth) * 10) / 10;
      el.style.fontSize = `${Math.max(px, KPI_MIN_PX)}px`;
      if (px >= KPI_MIN_PX) el.style.whiteSpace = '';
      else el.style.whiteSpace = 'normal';
    };
    fit();
    const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(() => el.clientWidth !== lastW && fit()) : null;
    ro?.observe(el);
    document.fonts?.ready.then(fit);
    return () => ro?.disconnect();
  }, [text]);
  return ref;
}

export function Kpi(props: {
  label: string;
  f?: Fig;
  value?: string;
  sub?: string;
  note?: string;
  title?: string;
  span?: boolean;
  /** source and year of a tile given as a text value (no `f`), so that "Copy citation" reads it as it reads a figure's */
  s?: string;
  y?: number | string;
}) {
  const f = props.f;
  const [open, setOpen] = useState(false);
  const valueText = props.value ?? fmtFig(f);
  const valueRef = useFitOneLine(valueText);
  const title = props.title ?? (f ? `${f.s} · ${f.y}${f.n ? ' · ' + f.n : ''}` : undefined);
  const note = props.note;
  const long = !!note && note.length > 90;
  return (
    <div class={`kpi${props.span ? ' kpi-span' : ''}`} title={title} data-src={f?.s ?? props.s} data-y={f ? String(f.y) : props.y != null ? String(props.y) : undefined}>
      <div class="kpi-label">{props.label}</div>
      <div class="kpi-value" ref={valueRef}>{valueText}</div>
      {(f || props.sub) && (
        <div class="kpi-src">{props.sub ?? `${sources.value[f!.s]?.publisher ?? f!.s} · ${f!.y}`}</div>
      )}
      {note &&
        (long ? (
          <button class={`kpi-note kpi-note-btn${open ? ' open' : ''}`} aria-expanded={open} onClick={() => setOpen(!open)} title={open ? 'Show less' : 'Show the full note'}>
            <span>{note}</span>
          </button>
        ) : (
          <div class="kpi-note">{note}</div>
        ))}
    </div>
  );
}

/**
 * Small trend line of a series (inline SVG): one segment per pair of years that both have a figure, a dot on the year
 * shown. The vertical scale is the series' own range. `breaks`: years (indexes) the line does not join to the year
 * before (the entity of the row changes there).
 */
export function TrendLine(props: { vals: (number | null)[]; at?: number | null; title?: string; w?: number; h?: number; breaks?: number[] }) {
  const w = props.w ?? 44;
  const h = props.h ?? 14;
  const n = props.vals.length;
  const nums = props.vals.filter((v): v is number => v != null);
  if (n < 2 || !nums.length) return <span class="trend" style={{ width: `${w}px` }} />;
  const lo = Math.min(...nums);
  const hi = Math.max(...nums);
  const x = (i: number) => 1 + (i / (n - 1)) * (w - 2);
  const y = (v: number) => (hi === lo ? h / 2 : 1.5 + (1 - (v - lo) / (hi - lo)) * (h - 3));
  const segs: string[] = [];
  let cur = '';
  // a year alone between gaps or breaks is drawn as a dot (a zero-length line with round caps)
  const push = () => cur && segs.push(cur.includes(' L') ? cur : `${cur} h0`);
  props.vals.forEach((v, i) => {
    if (v == null || props.breaks?.includes(i)) {
      push();
      cur = '';
      if (v == null) return;
    }
    cur += `${cur ? ' L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
  });
  push();
  const at = props.at != null ? props.vals[props.at] : null;
  return (
    <span class="trend" title={props.title}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
        {segs.map((d) => <path key={d} d={d} />)}
        {at != null && props.at != null && <circle cx={x(props.at)} cy={y(at)} r="1.8" />}
      </svg>
    </span>
  );
}

/** "2005 12.3 → 2024 18.9": the first and last figures of a series, for the title of its trend line. */
function trendTitle(h: HistTable, vals: (number | null)[], u: string): string {
  const pts = vals.map((v, i) => (v == null ? null : `${h.labels?.[i] ?? h.years[i]} ${fmt(v)}`)).filter(Boolean);
  return pts.length ? `${pts[0]} → ${pts[pts.length - 1]} ${u}` : '';
}

/**
 * Ranked horizontal bars for a country table. Rows are clickable (open the country). The first `limit` rows are drawn,
 * then "Rest of world" (the world total minus the rows drawn and the source's own "Other countries" line, so that the
 * shares add up to 100%) and "Show all". `hist`: the table by year, for a trend line per row and the world by year;
 * `at` is the year of the series shown.
 */
export function RankedBars(props: { data: Ranked; color?: string; limit?: number; unitLabel?: string; hist?: HistTable; at?: number | null }) {
  const { data, hist } = props;
  const limit = props.limit ?? 10;
  const [all, setAll] = useState(false);
  // a new table starts folded
  useEffect(() => setAll(false), [data.rows]);
  // an Atlas estimate (the whole table, or one row) is printed to two significant digits; an Atlas conversion as the file gives it
  const kind = atlasKind(data);
  const val = (v: number, est?: boolean) => fmtEst(v, kind === 'est' || !!est);
  const rows = all ? data.rows : data.rows.slice(0, limit);
  const beyond = data.rows.slice(limit);
  const max = Math.max(...rows.map((r) => r.v), 1e-9);
  const world = data.world;
  // the source's own "Other countries" line, and apart from it the countries the table names beyond the rows shown
  const other = data.other && data.other > 0 ? data.other : 0;
  // what the world total holds beyond the countries listed and that line (places that are not countries of the atlas,
  // regions the source does not split, rounding): its own line when it is 0.05% of the world or more
  const gap = world ? world - data.rows.reduce((a, r) => a + r.v, 0) - other : 0;
  const notBy = world && gap > world * 5e-4 ? gap : 0;
  const further = all ? [] : beyond;
  const furtherSum = further.reduce((a, r) => a + r.v, 0) + notBy;
  const furtherNames = further.map((r) => r.name ?? countryName(r.c));
  const totalWord = data.scope === 'EU' ? 'EU total' : data.shareOf ? 'total' : 'world total'; // the table's own total, not always the world's
  const restTitle =
    data.hidden && data.hidden.k === further.length
      ? data.hidden.n
      : `${furtherNames.slice(0, 12).join(', ')}${furtherNames.length > 12 ? ` and ${furtherNames.length - 12} more` : ''}${notBy ? `; and what the ${totalWord} holds that the source does not give by country` : ''}`;
  const notByTitle = gapTitle(data, totalWord, !!other);
  const trendAt = props.at ?? (hist ? hist.years.length - 1 : null);
  const longNote = !!data.n && data.n.length > 130;
  const published = data.worldPublished != null && data.worldPublished !== world ? data.worldPublished : null;
  // the accessible name of a row reads "China 980 Mt, 53.8% of world", not "China 98053.8%": the unit and the separator are for screen readers
  const value = <span class="sr-only"> {data.u},</span>;
  const share = (p: string) => (
    <>
      <small>{p}</small>
      <span class="sr-only"> of {data.scope === 'EU' ? 'the EU total' : (data.shareOf ?? 'world')}</span>
    </>
  );
  const tr = hist ? ' has-trend' : '';
  const trendSlot = (vals?: (number | null)[], breaks?: number[]) =>
    hist ? vals ? <TrendLine vals={vals} at={trendAt} title={trendTitle(hist, vals, hist.u)} breaks={breaks} /> : <span class="trend" /> : null;
  // a row's line leaves out a value out of line with the years around it, and breaks where the row's entity changes
  const rowTrend = (c: string) => {
    if (!hist?.c[c]) return trendSlot();
    const t = trendOf(hist, c);
    return trendSlot(t.vals, t.breaks);
  };
  const wFirst = hist ? hist.world.findIndex((v) => v != null) : -1;
  return (
    <div>
      {hist && wFirst >= 0 && (
        <div class="bar-world" title={`${data.shareOf ? 'Total' : 'World total'} by year, ${hist.u}: ${hist.world.map((v, i) => `${hist.labels?.[i] ?? hist.years[i]} ${fmt(v)}`).join(', ')}`}>
          <span>{data.shareOf ? data.shareOf[0].toUpperCase() + data.shareOf.slice(1) : 'World'}, {hist.labels?.[wFirst] ?? hist.years[wFirst]} to {hist.labels?.[hist.years.length - 1] ?? hist.years[hist.years.length - 1]}</span>
          <TrendLine vals={trendOf(hist).vals} at={trendAt} w={64} h={16} />
          <span class="num">
            {fmt(hist.world[wFirst])} → {fmt(hist.world[hist.world.length - 1])} {hist.u}
          </span>
        </div>
      )}
      <div class="bars" style={{ '--bar-color': props.color }}>
        {rows.map((r, i) => {
          // a row that is not a country of the index (USDA's European Union) has no page to open: plain text
          const Row = isCountry(r.c) ? 'button' : 'div';
          return (
            <Row class={`bar-row${tr}`} key={r.c} onClick={Row === 'button' ? () => select({ kind: 'country', id: r.c }) : undefined} title={r.n ?? r.name}>
              <span class="bar-rank">{data.norank ? '' : i + 1}</span>
              <span>
                <span class="bar-label">
                  {r.name ?? countryName(r.c)}
                  {r.est && kind !== 'est' && <EstMark />}
                  {r.conv && !r.est && kind !== 'conv' && <EstMark label="Atlas conversion" title={CONV_TITLE} />}
                </span>
                <div class="bar-track">
                  <div class="bar-fill" style={{ width: `${(r.v / max) * 100}%` }} />
                </div>
              </span>
              {rowTrend(r.c)}
              <span class="bar-value">
                {val(r.v, r.est)}
                {value}
                {world ? share(pct(r.v / world)) : null}
              </span>
            </Row>
          );
        })}
        {further.length > 0 ? (
          <button class={`bar-row bar-other bar-further${tr}`} onClick={() => setAll(true)} title={restTitle}>
            <span class="bar-rank" />
            <span>
              <span class="bar-label">{data.scope === 'EU' ? 'Rest of the EU' : data.norank ? 'Further and unlisted countries' : 'Rest of world'}</span>
              <span class="bar-names">
                {further.length} more countr{further.length === 1 ? 'y' : 'ies'}
                {notBy ? ' and amounts not given by country' : ''}
              </span>
            </span>
            {trendSlot()}
            <span class="bar-value">
              {val(furtherSum)}
              {value}
              {world ? share(pct(furtherSum / world)) : null}
            </span>
          </button>
        ) : (
          notBy > 0 && (
            <div class={`bar-row bar-other${tr}`} title={notByTitle}>
              <span class="bar-rank" />
              <span class="bar-label">{gapLabel(data)}</span>
              {trendSlot()}
              <span class="bar-value">
                {val(notBy)}
                {value}
                {world ? share(pct(notBy / world)) : null}
              </span>
            </div>
          )
        )}
        {other > 0 && (
          <div class={`bar-row bar-other${tr}`}>
            <span class="bar-rank" />
            <span class="bar-label">Other countries (as published)</span>
            {trendSlot(hist?.other)}
            <span class="bar-value">
              {val(other)}
              {value}
              {world ? share(pct(other / world)) : null}
            </span>
          </div>
        )}
      </div>
      <div class="lt-foot" style={{ marginTop: '10px' }}>
        {beyond.length > 0 && (
          <button class="act-btn" onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? 'Show fewer' : `Show all (${data.rows.length})`}
          </button>
        )}
        <CsvAction sources={rankedSources(data)} onClick={(e) => downloadRanked(data, e.currentTarget)} title="Every row of this table with its year, source and licence, as a CSV file" />
      </div>
      {data.srcs ? <SourcesLine items={data.srcs.map((s) => ({ s, y: data.y }))} n={`${props.unitLabel ?? data.u}${data.n && !longNote ? ' · ' + data.n : ''}`} /> : <SourceLine
        s={data.s}
        y={data.y}
        n={`${props.unitLabel ?? data.u}${world ? ` · ${data.scope === 'EU' ? 'EU total' : (data.shareOf ?? 'world')} ${val(world)} ${data.u}` : ''}${published != null ? ` (the source publishes ${fmt(published)} ${data.u}; shares are of the sum of its lines)` : ''}${data.n && !longNote ? ' · ' + data.n : ''}`}
        mark={kind === 'est' ? <EstMark /> : kind === 'conv' ? <EstMark label="Atlas conversion" title={CONV_TITLE} /> : data.conv ? <EstMark label="Atlas conversion" title={`${data.conv}: ${CONV_TITLE}`} /> : undefined}
      />}
      {/* a long note folds to three lines and opens on a tap, as the estimate notes do */}
      {longNote && <FoldNote class="src-line" style={{ marginTop: '2px' }} text={data.n} />}
    </div>
  );
}

export function Placeholder(props: { children: ComponentChildren }) {
  return <div class="placeholder">{props.children}</div>;
}

/** The way back from a page that no longer exists, inside its "not in the atlas" line. */
export function WayBack(props: { onClick: () => void; children: string }) {
  return (
    <div>
      <button class="act-btn" onClick={props.onClick}>{props.children}</button>
    </div>
  );
}

export function Skeleton(props: { lines?: number }) {
  return (
    <div style={{ display: 'grid', gap: '8px' }}>
      {Array.from({ length: props.lines ?? 4 }, (_, i) => (
        <div class="skeleton" key={i} style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
    </svg>
  );
}

export function BrandMark() {
  return (
    <svg class="brand-mark" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="22" fill="none" stroke="#2a3a4f" stroke-width="3" />
      <path d="M12 39 C 23 15, 42 15, 53 27" fill="none" stroke="#3ee6ff" stroke-width="4" stroke-linecap="round" />
      <circle cx="53" cy="27" r="5" fill="#ffb547" />
    </svg>
  );
}

// ---------------------------------------------------------------- infrastructure icons

export interface InfraTypeMeta {
  label: string;
  /** plural label used by the side-panel chips */
  plural: string;
  /** glyph strokes in a 24x24 box (stroke = currentColor) */
  glyph: string;
  /** extra decoration in the 28x28 icon box (LNG direction arrow) */
  extra?: string;
}

const SNOWFLAKE =
  '<path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/><path d="M9.5 4.8L12 7l2.5-2.2M9.5 19.2L12 17l2.5 2.2"/>';

export const INFRA_META: Record<InfraType, InfraTypeMeta> = {
  field: {
    label: 'Oil & gas field',
    plural: 'Fields',
    glyph:
      '<path d="M12 3.5C12 3.5 6 10 6 14.5a6 6 0 0 0 12 0C18 10 12 3.5 12 3.5z"/><path d="M9.3 15a3 3 0 0 0 2.3 2.8"/>',
  },
  refinery: {
    label: 'Refinery',
    plural: 'Refineries',
    glyph:
      '<path d="M3 21h18"/><path d="M6 21V10h5v11"/><path d="M8.5 10V5"/><path d="M6 14h5M6 17.5h5"/><path d="M16 21V11"/><path d="M16 11c-2.2-2-2.2-4 0-6.5 2.2 2.5 2.2 4.5 0 6.5z"/>',
  },
  'lng-export': {
    label: 'LNG export terminal',
    plural: 'LNG export',
    glyph: SNOWFLAKE,
    extra: '<path d="M19.5 9.5L25.5 3.5M20.8 3.2h4.9v4.9" />',
  },
  'lng-import': {
    label: 'LNG import terminal',
    plural: 'LNG import',
    glyph: SNOWFLAKE,
    extra: '<path d="M25.5 3.5L19.5 9.5M19.2 4.8v4.9h4.9" />',
  },
  pipeline: {
    label: 'Pipeline',
    plural: 'Pipelines',
    glyph: '<path d="M3 15h5.5l3-6h1l3 6H21"/><path d="M3 19h18"/>',
  },
  mine: {
    label: 'Mine',
    plural: 'Mines',
    glyph:
      '<path d="M4.5 19.5L16.5 7.5"/><path d="M9 4.5C14.5 3.5 19.5 6 20 13"/><path d="M19.5 19.5L8 8"/><path d="M4.5 10l5-5" stroke-width="3.4"/>',
  },
  smelter: {
    label: 'Smelter / refinery',
    plural: 'Smelters',
    glyph:
      '<path d="M5 10h14l-1.8 8.4a2 2 0 0 1-2 1.6H8.8a2 2 0 0 1-2-1.6z"/><path d="M7.4 13.6c1.5-1 3-1 4.6 0s3 1 4.6 0"/><path d="M9 7c-1-1.2 1-1.8 0-3.2M15 7c-1-1.2 1-1.8 0-3.2"/>',
  },
  port: {
    label: 'Port',
    plural: 'Ports',
    glyph:
      '<circle cx="12" cy="5.5" r="2"/><path d="M12 7.5V20M8.5 11h7"/><path d="M5 13.5c.3 3.8 3.3 6.5 7 6.5s6.7-2.7 7-6.5"/><path d="M3.8 12l1.2 2 2.2-1.2M20.2 12L19 14l-2.2-1.2"/>',
  },
  storage: {
    label: 'Storage hub',
    plural: 'Storage hubs',
    glyph:
      '<ellipse cx="12" cy="6.5" rx="7" ry="2.5"/><path d="M5 6.5v11c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-11"/><path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
  },
};

/** Display order of the infrastructure types in filters. */
export const INFRA_ORDER: InfraType[] = ['field', 'refinery', 'lng-export', 'lng-import', 'pipeline', 'storage', 'mine', 'smelter', 'port'];

/** SVG markup of an infrastructure badge icon (also rasterised for the map). */
export function infraSvg(type: InfraType, color: string, size = 28): string {
  const m = INFRA_META[type];
  const scale = type === 'lng-export' || type === 'lng-import' ? 0.56 : 0.6;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="${size}" height="${size}">` +
    `<circle cx="14" cy="14" r="10.5" fill="#0a1019" fill-opacity="0.94" stroke="${color}" stroke-width="1.8"/>` +
    `<g transform="translate(14 14) scale(${scale}) translate(-12 -12)" fill="none" stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${m.glyph}</g>` +
    (m.extra ? `<g fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${m.extra}</g>` : '') +
    `</svg>`
  );
}

export function InfraIcon(props: { type: InfraType; color?: string; size?: number }) {
  return (
    <span
      class="infra-ic"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: infraSvg(props.type, props.color ?? '#b9c4d0', props.size ?? 20) }}
    />
  );
}

/**
 * Status pill of an infrastructure asset: green when operating, grey when the status is not stated, amber otherwise.
 * `asOf` ("2026-03") is when the status was true: "Damaged as of March 2026".
 */
export function StatusBadge(props: { status?: string; asOf?: string }) {
  if (!props.status) return null;
  const cls = props.status === 'not-stated' ? 'badge-plain' : statusClassOf(props.status) === 'ok' ? 'badge-ok' : 'badge-warn';
  return <span class={`badge ${cls}`}>{statusText(props.status, props.asOf)}</span>;
}

const MODE_LABEL: Record<string, string> = { sea: 'sea', land: 'land', mixed: 'sea + land', pipeline: 'pipeline' };
const MODE_TITLE: Record<string, string> = {
  sea: 'Seaborne',
  land: 'Overland',
  mixed: 'By sea and overland; the split is not known',
  pipeline: 'Pipeline',
};

/**
 * How a flow moves: SEA, LAND, SEA + LAND (both, split not known) or PIPELINE. `via` is the transit port of a
 * landlocked country's sea cargo ("sea via Dar es Salaam"): the badge stays SEA and its title names the port.
 */
export function ModeBadge(props: { mode?: string; via?: string }) {
  const m = props.mode;
  if (!m) return null;
  const title = m === 'sea' && props.via ? `Sea via ${props.via}` : (MODE_TITLE[m] ?? m);
  return (
    <span class={`badge badge-mode mode-${m}`} title={title}>
      {MODE_LABEL[m] ?? m}
    </span>
  );
}

/** A note that folds to three lines when it is long and opens on a tap: a hover title cannot be read on a touch screen. */
export function FoldNote(props: { text?: string | null; class?: string; style?: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const text = props.text;
  if (!text) return null;
  const cls = props.class ?? 'kpi-note';
  if (text.length <= 130) return <div class={cls} style={props.style}>{text}</div>;
  return (
    <button class={`${cls} kpi-note-btn${open ? ' open' : ''}`} style={props.style} aria-expanded={open} onClick={() => setOpen(!open)} title={open ? 'Show less' : 'Show the full note'}>
      <span>{text}</span>
    </button>
  );
}

/** What the "Atlas conversion" mark says: the published figure changed to another unit with a stated factor. */
export const CONV_TITLE = 'Published figure converted by the atlas to another unit with the factor stated in the note, shown to three significant digits';

/** Mark on a figure that the atlas computed itself (a tonnage estimated from the declared value): shown to two significant digits. */
export function EstMark(props: { title?: string; label?: string }) {
  return (
    <span class="est-mark" title={props.title ?? 'Computed by the atlas, not published by a source; the method is in the note. Shown to two significant digits'}>
      {props.label ?? 'Atlas estimate'}
    </span>
  );
}

/** Compact clickable row: leading node, title, optional sub line, right-aligned meta. */
export function RowBtn(props: {
  onClick?: () => void;
  lead?: ComponentChildren;
  title: ComponentChildren;
  sub?: ComponentChildren;
  meta?: ComponentChildren;
  tip?: string;
  href?: string;
  /** the meta text may be long (a unit with a sentence in it): it wraps in its own column instead of widening the row */
  wrapMeta?: boolean;
}) {
  const body = (
    <>
      {props.lead}
      <span class="row-main">
        <span class="row-title">{props.title}</span>
        {props.sub != null && <span class="row-sub">{props.sub}</span>}
      </span>
      {props.meta != null && <span class={`row-meta num${props.wrapMeta ? ' row-meta-wrap' : ''}`}>{props.meta}</span>}
    </>
  );
  if (props.href)
    return (
      <a class="row-btn" href={props.href} target="_blank" rel="noopener" title={props.tip}>
        {body}
      </a>
    );
  return (
    <button class="row-btn" onClick={props.onClick} title={props.tip} disabled={!props.onClick} style={!props.onClick ? { cursor: 'default' } : undefined}>
      {body}
    </button>
  );
}
