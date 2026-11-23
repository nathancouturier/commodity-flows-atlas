/**
 * Company rows (commodity pages, country pages) and the shipping companies of a vessel class. The lists are built from
 * pipeline/companies/*.json (schema: pipeline/companies/README.md): each row gives the company's own figure with its
 * year and page, its ownership, a sanction mark with the authority and date, and the infrastructure assets whose
 * operator field names it.
 */
import { Fragment } from 'preact';
import { useMemo, useState } from 'preact/hooks';
import type { Company, CompanyFig, CompanySanction, InfraType, ShippingCompanies, VesselClass } from '../types';
import { commodityMeta, countryName, loadOptional, sourceLabel } from '../lib/data';
import { fmt } from '../lib/format';
import { monthYear } from '../lib/infra';
import { select } from '../lib/store';
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

/** Figures are ordered together only when they count the same thing in the same unit ("LNG sold" is not "LNG produced"). */
function measure(f: CompanyFig): string {
  const head = f.what.replace(/\([^)]*\)/g, ' ').split(',')[0].replace(/\b(consolidated|attributable|equity|own|total|group|gross|net)\b/gi, ' ');
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

const CORP = /\s+(energy|corporation|corp\.?|group|plc|ltd\.?|limited|inc\.?|holdings|resources|mining|company|co\.|s\.?a\.?|ag|asa|nv|se|international)$/i;
const GENERIC = new Set(['china', 'saudi', 'national', 'united', 'royal', 'golden', 'star', 'pacific', 'general', 'global', 'coal', 'oil', 'gas', 'petroleum', 'the']);

/** The forms of a company's name an operator field may use: the name, the names in brackets, the name without "Energy", "Group"... */
export function nameForms(name: string): string[] {
  const out = new Set<string>();
  const add = (s: string, min: number) => {
    const t = s.trim().replace(/^(formerly|incl\.|ex-)\s*/i, '');
    if (t.length >= min && !t.endsWith('&') && !GENERIC.has(t.toLowerCase())) out.add(t);
  };
  const base = name.replace(/\s*\([^)]*\)\s*/g, ' ').trim();
  add(base, 2);
  for (const m of name.matchAll(/\(([^)]+)\)/g)) m[1].split(/[,;]/).forEach((p) => add(p, 3));
  let s = base;
  while (CORP.test(s)) {
    s = s.replace(CORP, '');
    add(s, 4);
  }
  return [...out];
}

const escRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Assets whose operator field names the company (as operator or as an owner with a share). */
export function assetsOf(name: string, infra: InfraFeature[]): InfraFeature[] {
  // a former owner ("Aster, ex-Shell"; "formerly Adaro Energy"; "which bought Mechel's stake") does not count
  const res = nameForms(name).map((n) => new RegExp(`(^|[^\\p{L}\\p{N}])(?<!ex-)(?<!formerly )(?<!bought )${escRe(n)}($|[^\\p{L}\\p{N}])`, 'iu'));
  return infra.filter((f) => f.p.operator && res.some((r) => r.test(f.p.operator!)));
}

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
          <a href={s.url} target="_blank" rel="noopener" style={LINK}>{s.by}, {monthYear(s.since)}</a>
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

function CompanyRow({ c, showK, infra }: { c: Company; showK?: boolean; infra: InfraFeature[] | null | undefined }) {
  const assets = useMemo(() => (infra ? assetsOf(c.name, infra) : []), [c.name, infra]);
  const own = c.own ? OWN_LABEL[c.own] : null;
  return (
    <div class="row-btn co-row" style={{ alignItems: 'flex-start' }}>
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
          {[c.hq ? countryName(c.hq) : null, c.role, own, c.parent ? `parent: ${c.parent}` : null,
            showK && c.k ? [c.k].flat().map((k) => commodityMeta(k)?.name ?? k).join(', ') : null].filter(Boolean).join(' · ')}
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
function readMonths(list: Company[]): string | undefined {
  const ms = [...new Set(list.map((c) => c.read).filter((m): m is string => !!m))].sort();
  return ms.length ? `read in ${ms.map(monthYear).join(', ')}` : undefined;
}

export function CompanyRows(props: { title?: string; list: Company[]; showK?: boolean; keepOrder?: boolean }) {
  const { list } = props;
  const infra = useLoaded<InfraFeature[]>(() => loadInfra(), []);
  const blocks = useMemo(() => (props.keepOrder ? [{ rows: list }] : companyBlocks(list)), [list, props.keepOrder]);
  if (!list.length) return null;
  const items = list.flatMap((c) => [...(c.s ? [{ s: c.s }] : []), ...(c.fig ? [{ s: c.fig.s }] : [])]);
  return (
    <div class="co-group">
      {props.title && <h4 class="route-sub">{props.title}</h4>}
      {blocks.map((b, i) => (
        <Fragment key={b.label ?? i}>
          {b.label && <div class="infra-block">{b.label}</div>}
          {b.rows.map((c) => (
            <CompanyRow key={c.name} c={c} showK={props.showK} infra={infra} />
          ))}
        </Fragment>
      ))}
      <SourcesLine items={items} n={readMonths(list)} />
    </div>
  );
}

// ---------------------------------------------------------------- companies of a country

export type CompanyMap = Record<string, { producers?: Company[]; processors?: Company[]; traders?: Company[] }>;

/**
 * Companies headquartered in a country, each once with every commodity it is listed for: the most commodities first, then
 * producers, processors, traders. Read from the companies file itself, so the page follows it without a profile rebuild;
 * the commodity-specific figure is left out.
 */
export function companiesOf(map: CompanyMap, iso: string): Company[] {
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
  if (!n && !unnamed.length && !brokers.length && !terminals.length) return null;
  return (
    <Section fold title="Shipping companies" aside={<span class="muted num">{n}</span>}>
      {groups.map((g) => <CompanyRows key={g.title} title={g.title} list={g.list} />)}
      {!n && <p class="prose small">No shipping company of the atlas's list names this class in its fleet.</p>}
      {unnamed.length > 0 && <CompanyRows title={`Other ${SEGMENT_TITLE[seg!].toLowerCase()} (classes not stated)`} list={unnamed} />}
      {brokers.length > 0 && <CompanyRows title="Shipbrokers (all segments)" list={brokers} keepOrder />}
      {terminals.length > 0 && <CompanyRows title="Liquid bulk terminal operators" list={terminals} />}
      <p class="muted small">
        Fleets as each company's last annual report or filing states them, with its year; the classes are those the
        company names in its fleet list.
      </p>
    </Section>
  );
}
