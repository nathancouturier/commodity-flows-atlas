/**
 * Company rows (commodity pages, country pages) and the shipping companies of a vessel class. The lists are built from
 * pipeline/companies/*.json (schema: pipeline/companies/README.md): each row gives the company's own figure with its
 * year and page, its ownership, a sanction mark with the authority and date, and the infrastructure assets whose
 * operator field names it.
 */
import { Fragment } from 'preact';
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import type { Company, CompanyFig, CompanySanction, InfraType, ShippingCompanies, VesselClass } from '../types';
import { commodityMeta, countryName, loadOptional, sourceLabel } from '../lib/data';
import { fmt } from '../lib/format';
import { operatorMatcher } from '../lib/companyAssets';
import { monthYear } from '../lib/infra';
import { companyFilter, select } from '../lib/store';
import { loadInfra, type InfraFeature } from '../map/modules/infrastructure';
import { Section, SourcesLine, shortSource } from './ui';
import { useLoaded } from './views/shared';

const OWN_LABEL: Record<string, string> = {
  state: 'state-owned',
  'state-listed': 'state-controlled, listed',
  listed: 'listed',
  private: 'private',
  cooperative: 'cooperative',
};

export const sanctionsOf = (c: Company): CompanySanction[] => (c.sanction ? [c.sanction].flat() : []);

/** The bases a fleet is counted on: a fleet owned is not a fleet owned and chartered-in, nor one with ships on order. */
const FLEET_BASIS: [RegExp, string][] = [
  [/\bowned\b/i, 'owned'],
  [/\bleased\b/i, 'leased'],
  [/\bchartered\b/i, 'chartered-in'],
  [/\bmanaged\b/i, 'managed'],
  [/\b(on order|due for delivery|under construction|newbuild)/i, 'with ships on order'],
];

/**
 * Figures are ordered together only when they count the same thing in the same unit ("LNG sold" is not "LNG produced");
 * a fleet, also on the same basis.
 */
function measure(f: CompanyFig): string {
  const head = f.what.replace(/\([^)]*\)/g, ' ').split(',')[0].replace(/\b(consolidated|attributable|equity|own|total|group|gross|net)\b/gi, ' ');
  if (/^\s*fleet\b/i.test(head)) {
    const basis = FLEET_BASIS.filter(([re]) => re.test(f.what)).map(([, w]) => w);
    const onOrder = basis.at(-1) === 'with ships on order' ? basis.pop() : null;
    return [`fleet, ${basis.length ? basis.join(' and ') : 'basis not stated'}`, onOrder].filter(Boolean).join(', ');
  }
  return head.replace(/\s+/g, ' ').trim();
}
const cohort = (f: CompanyFig) => `${f.u}|${measure(f).toLowerCase()}`;

/**
 * Blocks of rows: each set of comparable figures (largest set first) ordered by value, then the rows without a figure in
 * the list's order. A block's label says what its figures count; there is no label when the list is one block.
 */
export function companyBlocks(list: Company[]): { label?: string; rows: Company[] }[] {
  const sets = new Map<string, Company[]>();
  for (const c of list) if (c.fig) sets.set(cohort(c.fig), [...(sets.get(cohort(c.fig)) ?? []), c]);
  const blocks: { label?: string; rows: Company[] }[] = [...sets.values()]
    .sort((a, b) => b.length - a.length)
    .map((s) => ({ label: `${measure(s[0].fig!)} (${s[0].fig!.u})`, rows: [...s].sort((a, b) => b.fig!.v - a.fig!.v) }));
  const rest = list.filter((c) => !c.fig);
  if (rest.length) blocks.push({ label: 'No figure given', rows: rest });
  if (blocks.length === 1) delete blocks[0].label;
  return blocks;
}

const LINK = { color: 'var(--ink-2)' };

/** Short names of the sources of company figures. */
const FIG_SOURCE: Record<string, string> = { 'sec-edgar': 'SEC filing', cochilco: 'Cochilco', 'company-reports': 'company report', wikipedia: 'Wikipedia' };

// ---------------------------------------------------------------- company -> assets

/**
 * Assets whose operator field names the company (as operator or as an owner with a share; a former owner does not count).
 * `others`: every company of the lists, so that "Gazprom Neft" is not counted for Gazprom.
 */
export function assetsOf(name: string, infra: InfraFeature[], others: string[] = []): InfraFeature[] {
  const names = operatorMatcher(name, others);
  return infra.filter((f) => f.p.operator && names(f.p.operator));
}

export type CompanyMap = Record<string, { producers?: Company[]; processors?: Company[]; traders?: Company[] }>;

let allPromise: Promise<{ map: CompanyMap | null; shipping: ShippingCompanies | null; names: string[] }> | null = null;
/** Both company lists (the commodities' and the shipping companies'), and every name in them. */
export function loadAllCompanies() {
  allPromise ??= Promise.all([loadOptional<CompanyMap>('commodities/companies.json'), loadOptional<ShippingCompanies>('freight/shipping-companies.json')]).then(
    ([map, shipping]) => {
      const names = new Set<string>();
      for (const groups of Object.values(map ?? {})) for (const list of Object.values(groups)) for (const c of list ?? []) names.add(c.name);
      for (const list of Object.values(shipping ?? {})) for (const c of list ?? []) names.add(c.name);
      return { map, shipping, names: [...names] };
    },
  );
  return allPromise;
}

/** The id of a company in a link (`co=`): its name in lower case, letters and digits joined by hyphens. */
export const companySlug = (name: string) =>
  name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

function Assets({ list }: { list: InfraFeature[] }) {
  const [open, setOpen] = useState(false);
  if (!list.length) return null;
  return (
    <span class="row-detail">
      <button class="link-btn" style={{ textTransform: 'none', letterSpacing: 0 }} onClick={() => setOpen(!open)} aria-expanded={open}
        title="Assets of the atlas's infrastructure layer whose operator field names this company, as operator or as an owner">
        {list.length} asset{list.length === 1 ? '' : 's'} on the map {open ? '▴' : '▾'}
      </button>
      {open && (
        <span style={{ display: 'block' }}>
          {list.map((f, i) => (
            <span key={`${f.p.type}:${f.p.id}`}>
              {i > 0 && ', '}
              <button class="link-btn" style={{ textTransform: 'none', letterSpacing: 0 }} onClick={() => select({ kind: 'infra', id: f.p.id, layer: f.p.type as InfraType })}>
                {f.p.name}
              </button>
            </span>
          ))}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------- rows

function SanctionMark({ c }: { c: Company }) {
  const list = sanctionsOf(c);
  if (!list.length) return null;
  return (
    <span class="row-detail">
      <span class="badge badge-warn" style={{ padding: '0 6px', marginRight: 4 }}>Sanctioned</span>
      {list.map((s, i) => (
        <span key={s.by}>
          {i > 0 && ' · '}
          <a href={s.url} target="_blank" rel="noopener" style={LINK} title="The date of the designation in the notice or list linked, the one the atlas read: an earlier designation may exist">
            {s.by} designation of {monthYear(s.since)}
          </a>
        </span>
      ))}
    </span>
  );
}

function FigLine({ f, url }: { f: CompanyFig; url?: string }) {
  return (
    <span class="row-detail">
      {f.what}, {f.y} ·{' '}
      <a href={f.url} target="_blank" rel="noopener" title={sourceLabel(f.s)} style={LINK}>
        {FIG_SOURCE[f.s] ?? shortSource(f.s)}
        {f.url === url ? '' : ' ↗'}
      </a>
      {f.n && <> · {f.n}</>}
    </span>
  );
}

/** The parent, with a link to the page that states its share when that is not the row's own page. */
function Parent({ c }: { c: Company }) {
  if (!c.parentUrl || c.parentUrl === c.url) return <>parent: {c.parent}</>;
  return (
    <>
      parent:{' '}
      <a href={c.parentUrl} target="_blank" rel="noopener" style={LINK}>
        {c.parent} ↗
      </a>
    </>
  );
}

function CompanyRow({ c, showK, infra, names }: { c: Company; showK?: boolean; infra: InfraFeature[] | null | undefined; names: string[] }) {
  const assets = useMemo(() => (infra ? assetsOf(c.name, infra, names) : []), [c.name, infra, names]);
  const own = c.own ? OWN_LABEL[c.own] : null;
  const sub = [c.hq ? countryName(c.hq) : null, c.role, own].filter(Boolean).join(' · ');
  const after = [
    c.seg?.length ? `Shipping: ${c.seg.join(', ')}` : null,
    showK && c.k ? [c.k].flat().map((k) => commodityMeta(k)?.name ?? k).join(', ') : null,
  ].filter(Boolean).join(' · ');
  return (
    <div class={`row-btn co-row${companyFilter.value === companySlug(c.name) ? ' co-hit' : ''}`} data-co={companySlug(c.name)} style={{ alignItems: 'flex-start' }}>
      <span class="row-main">
        <span class="row-title">
          {c.url ? (
            <a href={c.url} target="_blank" rel="noopener" title={[c.s ? sourceLabel(c.s) : '', c.y, c.read ? `read in ${monthYear(c.read)}` : ''].filter(Boolean).join(' · ')}
              style={{ color: 'inherit', textDecoration: 'none' }}>
              {c.name}<span class="ext"> ↗</span>
            </a>
          ) : c.name}
        </span>
        <span class="row-sub">
          {sub}
          {c.parent && <>{sub && ' · '}<Parent c={c} /></>}
          {after && <>{(sub || c.parent) && ' · '}{after}</>}
          <SanctionMark c={c} />
          {c.fig && <FigLine f={c.fig} url={c.url} />}
          {c.detail && <span class="row-detail">{c.detail}</span>}
          <Assets list={assets} />
        </span>
      </span>
      {c.fig && (
        <span class="row-meta num">
          {fmt(c.fig.v)} {c.fig.u}
          <small>{c.fig.y}</small>
        </span>
      )}
    </div>
  );
}

/** "read in November 2026": the months the pages of the list were read (the year of a fact is on its row, never here). */
const NO_NAMES: string[] = [];

function readMonths(list: Company[]): string | undefined {
  const ms = [...new Set(list.map((c) => c.read).filter((m): m is string => !!m))].sort();
  return ms.length ? `read in ${ms.map(monthYear).join(', ')}` : undefined;
}

/** The company a link names (`co=`) when one of the lists holds it: its block opens on that row. */
export function linkedCompany(...lists: (Company[] | undefined)[]): string | null {
  const slug = companyFilter.value;
  return slug && lists.some((l) => l?.some((c) => companySlug(c.name) === slug)) ? slug : null;
}

/** The row of the company a link names (`co=`), shown once its rows are drawn (the first one when it is listed twice). */
function useShowCompany(ref: { current: HTMLDivElement | null }, list: Company[]) {
  const slug = companyFilter.value;
  useEffect(() => {
    if (!slug || !list.some((c) => companySlug(c.name) === slug)) return;
    const id = requestAnimationFrame(() => {
      const row = ref.current?.closest('section')?.querySelector<HTMLElement>(`[data-co="${slug}"]`);
      row?.scrollIntoView({ block: 'center' });
    });
    return () => cancelAnimationFrame(id);
  }, [slug, list]);
}

export function CompanyRows(props: { title?: string; list: Company[]; showK?: boolean; keepOrder?: boolean }) {
  const { list } = props;
  const infra = useLoaded<InfraFeature[]>(() => loadInfra(), []);
  const all = useLoaded(() => loadAllCompanies(), []);
  const names = all?.names ?? NO_NAMES;
  const blocks = useMemo(() => (props.keepOrder ? [{ rows: list }] : companyBlocks(list)), [list, props.keepOrder]);
  const ref = useRef<HTMLDivElement>(null);
  useShowCompany(ref, list);
  if (!list.length) return null;
  const items = list.flatMap((c) => [
    ...(c.s ? [{ s: c.s }] : []),
    ...(c.fig ? [{ s: c.fig.s }] : []),
    ...(c.parentUrl?.includes('wikipedia.org') ? [{ s: 'wikipedia' }] : []),
  ]);
  return (
    <div class="co-group" ref={ref}>
      {props.title && <h4 class="route-sub">{props.title}</h4>}
      {blocks.map((b, i) => (
        <Fragment key={b.label ?? i}>
          {b.label && <div class="infra-block">{b.label}</div>}
          {b.rows.map((c) => (
            <CompanyRow key={c.name} c={c} showK={props.showK} infra={infra} names={names} />
          ))}
        </Fragment>
      ))}
      <SourcesLine items={items} n={readMonths(list)} />
    </div>
  );
}

// ---------------------------------------------------------------- companies of a country

/** The shipping segments in the words of a country page. */
const SEGMENT_WORD: Record<string, string> = {
  'dry-bulk': 'dry bulk',
  tankers: 'tankers',
  gas: 'gas carriers',
  charterers: 'charterer',
  brokers: 'shipbroking',
  terminals: 'liquid bulk terminals',
};

/**
 * Companies headquartered in a country, each once with every commodity it is listed for: the most commodities first, then
 * producers, processors, traders, then the shipping companies with their segments ("Shipping: tankers"). Read from the
 * companies files themselves, so the page follows them without a profile rebuild; the commodity-specific figure and the
 * fleet are left out.
 */
export function companiesOf(map: CompanyMap, iso: string, shipping?: ShippingCompanies | null): Company[] {
  const found = new Map<string, { c: Company; rank: number; order: number }>();
  let order = 0;
  Object.entries(map).forEach(([k, groups]) =>
    (['producers', 'processors', 'traders'] as const).forEach((g, rank) =>
      (groups[g] ?? []).forEach((co) => {
        if (co.hq !== iso) return;
        let e = found.get(co.name);
        if (!e) {
          const { fig: _fig, y: _y, ...rest } = co;
          e = { c: { ...rest, k: [] }, rank, order: order++ };
          found.set(co.name, e);
        }
        const ks = e.c.k as string[];
        if (!ks.includes(k)) ks.push(k);
      }),
    ),
  );
  Object.entries(shipping ?? {}).forEach(([seg, list]) =>
    (list ?? []).forEach((co) => {
      if (co.hq !== iso) return;
      let e = found.get(co.name);
      if (!e) {
        const { fig: _fig, y: _y, classes: _classes, ...rest } = co;
        e = { c: { ...rest, k: [] }, rank: 3, order: order++ };
        found.set(co.name, e);
      }
      const word = SEGMENT_WORD[seg] ?? seg;
      e.c.seg = [...(e.c.seg ?? []), ...(e.c.seg?.includes(word) ? [] : [word])];
    }),
  );
  return [...found.values()]
    .sort((a, b) => (b.c.k as string[]).length - (a.c.k as string[]).length || a.rank - b.rank || a.order - b.order)
    .map((e) => e.c);
}

// ---------------------------------------------------------------- shipping companies of a vessel class

const SEGMENT_TITLE: Record<string, string> = {
  'dry-bulk': 'Dry bulk owners and operators',
  tankers: 'Tanker owners and operators',
  gas: 'Gas carrier owners and operators',
  charterers: 'Charterers',
};
const SEGMENT_OF_CLASS: Record<string, keyof ShippingCompanies> = { dry: 'dry-bulk', tanker: 'tankers', gas: 'gas' };

/** Owners, operators and charterers of the class, by segment; brokers and (for liquid cargoes) terminal operators after them. */
export function ShippingCompaniesBlock({ v }: { v: VesselClass }) {
  const all = useLoaded<ShippingCompanies>(() => loadOptional<ShippingCompanies>('freight/shipping-companies.json'), []);
  if (!all) return null;
  const groups = Object.entries(SEGMENT_TITLE)
    .map(([seg, title]) => ({ title, list: (all[seg as keyof ShippingCompanies] ?? []).filter((c) => c.classes?.includes(v.id)) }))
    .filter((g) => g.list.length);
  // the same segment, where the page read does not name the company's classes
  const seg = SEGMENT_OF_CLASS[v.segment];
  const unnamed = seg ? (all[seg] ?? []).filter((c) => !c.classes?.length) : [];
  const brokers = all.brokers ?? [];
  const terminals = v.segment === 'tanker' || v.segment === 'gas' ? all.terminals ?? [] : [];
  const n = groups.reduce((a, g) => a + g.list.length, 0);
  // a class that no owner, operator or charterer of the list names, and whose segment has none (container ships): no block,
  // the brokers of every segment alone would suggest the atlas knows its companies
  if (!n && !unnamed.length) return null;
  const linked = linkedCompany(...groups.map((g) => g.list), unnamed, brokers, terminals);
  return (
    <Section key={linked ?? ''} fold open={!!linked} title="Shipping companies" aside={<span class="muted num">{n}</span>}>
      {groups.map((g) => <CompanyRows key={g.title} title={g.title} list={g.list} />)}
      {!n && <p class="prose small">No shipping company of the atlas's list names this class in its fleet.</p>}
      {unnamed.length > 0 && <CompanyRows title={`Other ${SEGMENT_TITLE[seg!].toLowerCase()} (classes not stated)`} list={unnamed} />}
      {brokers.length > 0 && <CompanyRows title="Shipbrokers (all segments)" list={brokers} keepOrder />}
      {terminals.length > 0 && <CompanyRows title="Liquid bulk terminal operators" list={terminals} />}
      <p class="muted small">
        Fleets as each row's page states them, with their year; fleets counted on different bases (owned, chartered-in, on
        order) are in separate blocks. The classes are those the page names for the company's fleet.
      </p>
    </Section>
  );
}
