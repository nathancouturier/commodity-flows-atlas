/**
 * Blocks of the country page built from the full data (pipeline/commodities/build_profiles.py): the value of a line in the
 * History year, trade balance and partners, freight (mode, typical ports, passages), the basket of all goods at HS4, the
 * notes of the customs data, asset operators and the EU link.
 */
import { useEffect, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import type { BasketRow, CountryProfile, FreightProduct, ProfileBalance, ProfileEntry, ProfilePartners } from '../../types';
import { commodityMeta, countryName, isCountry } from '../../lib/data';
import { fmt, fmtEst, pct } from '../../lib/format';
import { GROUP_LABEL, SOURCED_BASES, chokepointName } from '../../lib/freight';
import { commodity, select } from '../../lib/store';
import { EstMark, Section, SourceLine, SourcesLine, shortSource } from '../ui';
import { useFreightCatalogue } from './shared';
import '../../styles/country.css';

const PHONE = '(max-width: 600px)';

/** A block whose title folds it. On a phone the long blocks start folded; on a wider screen they start open. */
export function FoldSection(props: { title: string; aside?: ComponentChildren; children: ComponentChildren; foldOnPhone?: boolean }) {
  const phone = typeof matchMedia === 'function' && matchMedia(PHONE).matches;
  const [open, setOpen] = useState(!(props.foldOnPhone && phone));
  return (
    <Section
      title={
        <button class="fold-title" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span class="fold-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
          {props.title}
        </button>
      }
      aside={props.aside}
    >
      {open ? props.children : null}
    </Section>
  );
}

/** A list that shows its first rows and the rest behind "Show all (N)". */
function ShowAll<T>(props: { rows: T[]; first: number; render: (r: T, i: number) => ComponentChildren }) {
  const [all, setAll] = useState(false);
  useEffect(() => setAll(false), [props.rows]);
  const shown = all ? props.rows : props.rows.slice(0, props.first);
  return (
    <>
      {shown.map(props.render)}
      {props.rows.length > props.first && (
        <button class="act-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? 'Show fewer' : `Show all (${props.rows.length})`}
        </button>
      )}
    </>
  );
}

const productName = (k: string, label?: string) => label ?? commodityMeta(k)?.name ?? k;
const groupName = (g: string, k: string) => GROUP_LABEL[g] ?? commodityMeta(k)?.name ?? g;
function openCommodity(k: string) {
  if (!commodityMeta(k)) return;
  commodity.value = k;
  select({ kind: 'commodity', id: k });
}

// ---------------------------------------------------------------- a line in the History year

/** What a profile line shows in the History year `yr`: that year's value, share and rank where its series has the year. */
export interface EntryShown {
  v: number | null;
  share: number | null;
  rank: number | null;
  y: number | string;
  est: boolean;
  /** the figure is of a past year (no USD value then: the customs value is of the latest year) */
  past: boolean;
  /** words next to the line: no series for that year, or no figure that year */
  note: string | null;
  /** index of the year shown in the series (the dot on the trend line) */
  i: number | null;
  name: string | null;
}

export function entryAt(e: ProfileEntry, p: CountryProfile, yr: number | null): EntryShown {
  const ys = e.hk ? p.years?.[e.hk] : undefined;
  const last = ys ? ys.y.length - 1 : null;
  const latest: EntryShown = { v: e.v, share: e.share ?? null, rank: e.rank ?? null, y: e.y, est: !!e.est, past: false, note: null, i: last, name: null };
  if (yr == null) return latest;
  const i = ys ? ys.y.indexOf(yr) : -1;
  if (!ys || i < 0) {
    const same = String(e.y) === String(yr) || String(e.y).startsWith(`${yr}/`);
    return { ...latest, note: same ? null : `${e.y}: no series for ${yr}` };
  }
  if (i === last) return latest;
  const label = ys.l?.[i] ?? String(ys.y[i]);
  const v = e.hv?.[i] ?? null;
  const out = !!e.hout?.includes(i);
  if (v == null || v <= 0 || out) {
    return { v: null, share: null, rank: null, y: label, est: false, past: true, i, name: null,
      note: out ? `${label}: the source's figure is far out of line with the years around it, not ranked` : `no figure for ${label}` };
  }
  const w = ys.w[i];
  return {
    v,
    share: w ? v / w : null,
    rank: e.rank != null ? (e.hr?.[i] ?? null) : null,
    y: label,
    est: !!e.hest?.includes(i) || (e.s === 'atlas' && !!e.est),
    past: true,
    note: e.hsrc?.includes(i) ? 'estimated by the source' : null,
    i,
    name: e.hcl?.[i] ?? null,
  };
}

/** The values a line's trend draws: a value out of line is left out, and the line breaks where the row's entity changes. */
export function entryTrend(e: ProfileEntry): { vals: (number | null)[]; breaks: number[] } | null {
  if (!e.hv || e.hv.length < 2) return null;
  return { vals: e.hv.map((v, i) => (e.hout?.includes(i) ? null : v)), breaks: e.hbrk ?? [] };
}

/** "2005 3.7 → 2024 202 Mt" for the title of a line's trend. */
export function entryTrendTitle(e: ProfileEntry, p: CountryProfile): string {
  const ys = e.hk ? p.years?.[e.hk] : undefined;
  if (!ys || !e.hv) return '';
  const pts = e.hv.map((v, i) => (v == null || e.hout?.includes(i) ? null : `${ys.l?.[i] ?? ys.y[i]} ${fmt(v)}`)).filter(Boolean);
  return pts.length ? `${pts[0]} → ${pts[pts.length - 1]} ${e.u}` : '';
}

// ---------------------------------------------------------------- customs gaps, EU, no code

/** What customs data miss or blur for this origin (exports not recorded, recorded above production, hubs): the engine's caveats. */
export function GapNotes({ p }: { p: CountryProfile }) {
  if (!p.gaps?.length) return null;
  return (
    <div class="cp-gaps">
      {p.gaps.map((g) => (
        <div class="cp-gap" key={g.id}>
          <b>{groupName(g.g, g.k)}</b>: {g.text}
        </div>
      ))}
    </div>
  );
}

export function EuLink({ p }: { p: CountryProfile }) {
  if (p.eu) {
    return (
      <div class="cp-eu">
        Member of the European Union. USDA gives one figure for the Union in its crop tables:{' '}
        <button class="link-btn" onClick={() => select({ kind: 'country', id: p.eu! })}>
          {countryName(p.eu)}
        </button>
        .
      </div>
    );
  }
  if (p.members?.length) {
    return (
      <div class="cp-eu">
        One figure for the Union, as USDA publishes it. Member states:{' '}
        {p.members.map((c, i) => (
          <>
            {i > 0 && ', '}
            <button class="link-btn" key={c} onClick={() => select({ kind: 'country', id: c })}>
              {countryName(c)}
            </button>
          </>
        ))}
        .
      </div>
    );
  }
  return null;
}

// ---------------------------------------------------------------- balance and partners

/** "3,849 of 10,000, like 2.6 equal suppliers": the Herfindahl index in plain words. */
function hhiText(x: ProfilePartners, who: string): string {
  const eq = x.hhi > 0 ? 10000 / x.hhi : 0;
  return `concentration ${fmt(x.hhi)} on a scale of 0 to 10,000 (Herfindahl index; 10,000 = one ${who.replace(/s$/, '')}), as if ${fmt(eq)} ${who} had equal shares`;
}

function PartnerLine({ x, title, who }: { x: ProfilePartners; title: string; who: string }) {
  return (
    <div class="cp-partners">
      <span class="cp-k">{title}</span>
      <span>
        {x.rows.map((r, i) => (
          <span key={r.c}>
            {i > 0 && ', '}
            {isCountry(r.c) ? (
              <button class="link-btn" onClick={() => select({ kind: 'country', id: r.c })}>{countryName(r.c)}</button>
            ) : (
              countryName(r.c)
            )}{' '}
            <span class="num">{pct(r.share, true)}</span>
            {r.est && <EstMark />}
          </span>
        ))}
        {x.n > x.rows.length && <span class="muted"> · {x.n} in all</span>}
        <span class="cp-hhi muted"> · {hhiText(x, who)}{x.basis ? `; shares of ${x.basis}` : ''}</span>
        {x.est && x.estShare != null && <span class="muted"> · {pct(x.estShare, true)} of it is an Atlas estimate from the declared value</span>}
      </span>
    </div>
  );
}

function BalanceRow({ b }: { b: ProfileBalance }) {
  const name = productName(b.k, b.label);
  const net = b.net;
  const word = net ? (net.v > 0 ? 'Net exporter' : net.v < 0 ? 'Net importer' : 'Exports equal imports') : null;
  return (
    <div class="cp-bal">
      <div class="cp-bal-head">
        <button class="link-btn cp-bal-name" onClick={() => openCommodity(b.k)} disabled={!commodityMeta(b.k)}>{name}</button>
        {word && net && (
          <span class="cp-net num">
            {word} {net.v !== 0 && <>{fmtEst(Math.abs(net.v), net.est)} {net.u}</>}
            {net.est && <EstMark />}
          </span>
        )}
      </div>
      {net && (
        <div class="cp-sub muted">
          exports {net.exp != null ? `${fmtEst(net.exp, net.est)} ${net.u}` : 'none recorded'}, imports {net.imp != null ? `${fmtEst(net.imp, net.est)} ${net.u}` : 'none recorded'} · {net.y}
        </div>
      )}
      {b.dep && (
        <div class="cp-sub">
          Imports equal <b class="num">{pct(b.dep.v, true)}</b> of consumption ({fmt(b.dep.imp)} against {fmt(b.dep.cons)} {b.dep.u}, {b.dep.y}): imports over
          consumption in the same unit and year, not the share of consumption that is imported (imports can be re-exported or stocked)
        </div>
      )}
      {b.hub && (
        <div class="cp-hub">
          Trading or refining hub (derived): exports {pct(b.hub.exp, true)} and imports {pct(b.hub.imp, true)} of the world total, and no
          production line in the {shortSource(b.hub.prodS)} table of {b.hub.prodY}, which lists every producing country
        </div>
      )}
      {b.customers && <PartnerLine x={b.customers} title="Customers" who="customers" />}
      {b.suppliers && <PartnerLine x={b.suppliers} title="Suppliers" who="suppliers" />}
    </div>
  );
}

export function BalanceBlock({ p }: { p: CountryProfile }) {
  const rows = p.balance ?? [];
  if (!rows.length) return null;
  // the products the country trades most come first: the order of its export and import lines, by value
  const order = new Map<string, number>();
  [...p.exports, ...p.imports].forEach((e, i) => {
    const key = e.k + (e.label ?? '');
    if (!order.has(key)) order.set(key, i);
  });
  const sorted = [...rows].sort((a, b) => (order.get(a.k + (a.label ?? '')) ?? 999) - (order.get(b.k + (b.label ?? '')) ?? 999));
  const srcs: { s: string; y: number | string }[] = rows.flatMap((b) => [b.net, b.customers, b.suppliers, b.dep].flatMap((x) => (x ? [{ s: x.s, y: x.y }] : [])));
  return (
    <FoldSection title="Trade balance and partners" aside={<span class="muted num">{rows.length}</span>} foldOnPhone>
      <div class="cp-list">
        <ShowAll rows={sorted} first={6} render={(b) => <BalanceRow key={b.k + b.t} b={b} />} />
      </div>
      <SourcesLine
        items={srcs}
        n="net position from the export and import tables of the same unit and year; partners are the recorded pairs of the latest customs year, all transport modes, shares of tonnes unless stated; arithmetic on the published figures"
      />
    </FoldSection>
  );
}

// ---------------------------------------------------------------- freight

function modeText(x: { modes: FreightProduct['modes'] }): string {
  const m = x.modes;
  const sea = (m.sea ?? 0) + (m.transit ?? 0);
  return [
    sea ? `${pct(sea, true)} by sea${m.transit ? ` (${pct(m.transit, true)} through a port of another country)` : ''}` : null,
    m.mixed ? `${pct(m.mixed, true)} by sea and overland, split not known` : null,
    m.land ? `${pct(m.land, true)} overland` : null,
  ]
    .filter(Boolean)
    .join(', ');
}

function Passages({ via }: { via: { id: string; low: number; high: number }[] }) {
  if (!via.length) return <span class="muted">no tracked passage reaches 2% of the seaborne tonnes</span>;
  return (
    <>
      {via.map((v, i) => (
        <span key={v.id} class="cp-pass">
          {i > 0 && ' · '}
          <button class="link-btn" onClick={() => select({ kind: 'chokepoint', id: v.id })}>{chokepointName(v.id)}</button>{' '}
          <span class="num">{v.low > 0 ? `at least ${pct(v.low, true)}` : 'at least 0%'}{v.high > v.low ? `, up to ${pct(v.high, true)}` : ''}</span>
        </span>
      ))}
      <EstMark />
    </>
  );
}

function portBasis(b?: string): string {
  if (!b) return '';
  return SOURCED_BASES.includes(b) ? b : 'no source page yet';
}

function FreightRow({ x, side }: { x: FreightProduct; side: 'exports' | 'imports' }) {
  const via = (x.via ?? []).slice(0, 4);
  return (
    <div class="cp-fr">
      <div class="cp-bal-head">
        <button class="link-btn cp-bal-name" onClick={() => openCommodity(x.k)} disabled={!commodityMeta(x.k)}>{groupName(x.g, x.k)}</button>
        <span class="num cp-net">{fmtEst(x.kt / 1000, x.est)} Mt{x.est && <EstMark />}</span>
      </div>
      <div class="cp-sub">{modeText(x)}</div>
      {x.ports && x.ports.length > 0 && (
        <div class="cp-sub">
          <span class="cp-k">{side === 'exports' ? 'Load' : 'Discharge'}</span>{' '}
          {x.ports.map((pt, i) => (
            <span key={pt.name}>
              {i > 0 && ', '}
              {pt.name}
              {pt.c !== '' && <span class="muted">, {countryName(pt.c)}</span>} <span class="num">{pct(pt.share, true)}</span>
              {pt.basis && <span class="muted"> ({portBasis(pt.basis)})</span>}
            </span>
          ))}
        </div>
      )}
      {x.seaKt != null && x.seaKt > 0 && (
        <div class="cp-sub">
          <span class="cp-k">Passages</span> <Passages via={via} />
        </div>
      )}
      {x.unrouted != null && <div class="cp-sub muted">{pct(x.unrouted, true)} of the seaborne tonnes could not be routed</div>}
    </div>
  );
}

function FreightSide({ p, side }: { p: CountryProfile; side: 'exports' | 'imports' }) {
  const fr = p.freight!;
  const rows = fr[side];
  const tot = fr[side === 'exports' ? 'exportsTotal' : 'importsTotal'];
  if (!rows.length || !tot) return null;
  return (
    <div class="cp-fr-side">
      <h4 class="route-sub">{side === 'exports' ? 'Exports' : 'Imports'}</h4>
      <div class="cp-sub">
        {fmt(tot.kt / 1000)} Mt over the atlas's customs groups: <b>{pct(tot.sea, true)}</b> by sea{tot.mixed ? `, ${pct(tot.mixed, true)} by sea and overland` : ''}
      </div>
      {tot.via && tot.via.length > 0 && (
        <div class="cp-sub">
          <span class="cp-k">Passages</span> <Passages via={tot.via.slice(0, 6)} />
          <span class="muted"> · share of the seaborne tonnes of all these groups</span>
        </div>
      )}
      <div class="cp-list">
        <ShowAll rows={rows} first={5} render={(x) => <FreightRow key={x.g} x={x} side={side} />} />
      </div>
    </div>
  );
}

export function FreightBlock({ p }: { p: CountryProfile }) {
  useFreightCatalogue();
  if (!p.freight || (!p.freight.exports.length && !p.freight.imports.length)) return null;
  return (
    <FoldSection title="Freight" aside={<span class="muted num">{p.freight.y}</span>} foldOnPhone>
      <FreightSide p={p} side="exports" />
      <FreightSide p={p} side="imports" />
      <div class="muted small cp-fr-note">
        Typical ports (Atlas assumption): the port of each recorded pair, with the basis of the port. Passages: the share of the seaborne tonnes whose assumed route has
        to cross the passage ("at least") or may cross it ("up to"), from the routes of the trade-flow engine. Mode by cargo family (Atlas rule).
      </div>
      <SourceLine s={p.freight.s} y={p.freight.y} n="recorded pairs, all transport modes; ports, modes and routes: Atlas assumptions" />
    </FoldSection>
  );
}

// ---------------------------------------------------------------- basket

function BasketList({ side, x }: { side: string; x: { total: number; rows: BasketRow[] } }) {
  return (
    <div class="cp-basket">
      <h4 class="route-sub">
        {side} <span class="muted num">· {fmt(x.total)} bn USD in all</span>
      </h4>
      {x.rows.map((r, i) => (
        <button key={r.hs4} class="bar-row" style={{ width: '100%' }} title={r.d ? `HS ${r.hs4}: ${r.d}` : `HS ${r.hs4}`} onClick={r.k ? () => openCommodity(r.k!) : undefined} disabled={!r.k}>
          <span class="bar-rank">{i + 1}</span>
          <span>
            <span class="bar-label">{r.label}</span>
            <div class="bar-track">
              <div class="bar-fill" style={{ width: `${Math.max(2, r.share * 100)}%` }} />
            </div>
            <span class="bar-sub">HS {r.hs4}{r.k ? ` · ${commodityMeta(r.k)?.name ?? r.k} in the atlas` : ''}</span>
          </span>
          <span class="bar-value">
            {fmt(r.usd)} bn USD<small>{pct(r.share, true)}</small>
          </span>
        </button>
      ))}
    </div>
  );
}

export function BasketBlock({ p }: { p: CountryProfile }) {
  const b = p.basket;
  if (!b || (!b.exports && !b.imports)) return null;
  return (
    <FoldSection title="All goods: largest exports and imports" aside={<span class="muted num">{b.y}</span>} foldOnPhone>
      {b.exports && <BasketList side="Exports" x={b.exports} />}
      {b.imports && <BasketList side="Imports" x={b.imports} />}
      <SourceLine s={b.s} y={b.y} n="HS headings of four digits, every chapter; shares are of the country's total merchandise exports or imports in the same file" />
    </FoldSection>
  );
}

// ---------------------------------------------------------------- operators

export function OperatorsBlock({ p }: { p: CountryProfile }) {
  const ops = p.operators ?? [];
  if (!ops.length) return null;
  return (
    <FoldSection title="Operators of the assets listed" aside={<span class="muted num">{ops.length}</span>} foldOnPhone>
      <div class="cp-list">
        <ShowAll
          rows={ops}
          first={6}
          render={(o) => (
            <div class="cp-op" key={o.name}>
              <span>{o.name}</span>
              <span class="muted num">{o.assets.length} asset{o.assets.length === 1 ? '' : 's'}</span>
            </div>
          )}
        />
      </div>
      <div class="muted small">As the infrastructure layer names the operator of each asset; the asset pages give the source.</div>
    </FoldSection>
  );
}
