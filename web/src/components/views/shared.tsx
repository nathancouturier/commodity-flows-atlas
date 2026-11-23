/** Helpers shared by the freight detail views. */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { AltRouting, HistFlag, PortRef } from '../../types';
import { commodityMeta, sources } from '../../lib/data';
import { fmt } from '../../lib/format';
import { BASIS_QUALIFIER, SOURCED_BASES, altLabel, altOptions, chokepointName, loadFreightCatalogue, openVesselClass, vesselById, vesselClassList, vesselName, segmentOf, SEGMENT_COLOR } from '../../lib/freight';
import { commodity, select } from '../../lib/store';
import { Section, shortSource } from '../ui';
import { TimeChart, type TimeMarker } from '../charts/TimeChart';
import '../../styles/lane-engine.css';

/** Async loader hook: undefined = loading, null = missing/failed. */
export function useLoaded<T>(fn: () => Promise<T | null>, deps: unknown[]): T | null | undefined {
  const [v, setV] = useState<T | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    setV(undefined);
    fn().then(
      (r) => live && setV(r),
      () => live && setV(null),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return v;
}

/** Make sure vessel / chokepoint names resolve. */
export function useFreightCatalogue() {
  const n = vesselClassList.value.length;
  useEffect(() => {
    if (!n) loadFreightCatalogue().catch(() => {});
  }, [n]);
}

export const publisher = (s: string) => sources.value[s]?.publisher ?? s;

export function openCommodity(k: string) {
  if (!commodityMeta(k)) return;
  commodity.value = k;
  select({ kind: 'commodity', id: k });
}

export function CommodityChips(props: { ids: string[] }) {
  return (
    <div class="chips">
      {props.ids.map((k) => (
        <button class="chip" key={k} onClick={() => openCommodity(k)}>
          {commodityMeta(k)?.name ?? k}
        </button>
      ))}
    </div>
  );
}

export function VesselChip(props: { id: string }) {
  const color = SEGMENT_COLOR[segmentOf(props.id)];
  // a class that the catalogue lacks has no page and no routes to filter: plain text, not a button
  if (vesselClassList.value.length && !vesselById.value[props.id])
    return (
      <span class="chip chip-static">
        <i class="dot" style={{ background: color }} />
        {vesselName(props.id)}
      </span>
    );
  return (
    <button class="chip" onClick={() => openVesselClass(props.id)}>
      <i class="dot" style={{ background: color }} />
      {vesselName(props.id)}
    </button>
  );
}

/**
 * Voyage strip: load port, the chokepoints crossed in order, discharge port. The two ports are captioned
 * text ("From", "To"); only chokepoints are chips, so a port is never read as a chokepoint.
 */
export function RouteStrip(props: { from: string; to: string; via: string[]; noneText?: string }) {
  return (
    <>
      <div class="strip" role="list">
        <span class="strip-port" role="listitem" title={`From ${props.from}`}>
          <span class="strip-k">From</span> {props.from}
        </span>
        {props.via.map((id) => (
          <span class="strip-step" role="listitem" key={id}>
            <span class="strip-link" aria-hidden="true" />
            <button class="strip-cp" onClick={() => select({ kind: 'chokepoint', id })} title={`Chokepoint: open ${chokepointName(id)}`}>
              {chokepointName(id)}
            </button>
          </span>
        ))}
        <span class="strip-step" role="listitem" title={`To ${props.to}`}>
          <span class="strip-link" aria-hidden="true" />
          <span class="strip-port">
            <span class="strip-k">To</span> {props.to}
          </span>
        </span>
      </div>
      {props.via.length === 0 && <div class="muted small strip-none">{props.noneText ?? 'No tracked chokepoint on this voyage.'}</div>}
    </>
  );
}

/**
 * Where the atlas read a port: the source page of its gateway row. The basis adds a short qualifier where it matters (a page that
 * names the cargo in the other direction, the country's general port). A port with no page read says so; for a pair that is not
 * drawn, only the file's own basis decides, and nothing is printed when it names a page that is not linked here.
 * `settled` is false while the lane file that carries the links is still loading.
 */
export function PortSource({ p, basis, settled = true, cls = 'le-src' }: { p?: Partial<PortRef> | null; basis?: string; settled?: boolean; cls?: string }) {
  const b = p?.basis ?? basis;
  if (p?.s) {
    const name = shortSource(p.s).replace(/\s*\(.*\)$/, '');
    const q = b ? BASIS_QUALIFIER[b] : undefined;
    return (
      <span class={cls}>
        {' · '}
        {p.url ? <a href={p.url} target="_blank" rel="noopener">{name}</a> : name}
        {q && <span class="le-q"> ({q})</span>}
      </span>
    );
  }
  const unsourced = p ? true : b != null && !SOURCED_BASES.includes(b);
  return settled && unsourced ? <span class={`${cls} muted`}> · no source page yet</span> : null;
}

/**
 * The voyage with the chokepoints it has to cross. `viaAlt` lists passages that only some options cross. Two or more
 * options (parallel straits) read "One of:", the passages one option crosses together staying together; a single
 * passage reads "May also cross:" (another port option, or a route of similar length, avoids it).
 */
export function ViaSection(props: { from: string; to: string; via: string[]; viaAlt?: string[][] }) {
  const n = props.via.length;
  const alt = props.viaAlt ?? [];
  return (
    <Section title="Voyage" aside={n > 0 && <span class="muted strip-count">{n} chokepoint{n === 1 ? '' : 's'} crossed</span>}>
      <RouteStrip from={props.from} to={props.to} via={props.via} noneText={alt.length ? 'No chokepoint is crossed on every option.' : undefined} />
      {alt.map((list) => (
        <div class="le-oneof" key={list.join()}>
          <span class="le-oneof-k">{altLabel(list)}</span>
          {altOptions(list).map((option, i, all) => (
            <span class="le-option" key={option.join()}>
              {option.map((id, j) => (
                <>
                  {j > 0 && <span class="le-and">and</span>}
                  <button class="chip" key={id} onClick={() => select({ kind: 'chokepoint', id })} title={`Chokepoint: open ${chokepointName(id)}`}>
                    {chokepointName(id)}
                  </button>
                </>
              ))}
              {i < all.length - 1 && <span class="le-sep" aria-hidden="true">·</span>}
            </span>
          ))}
        </div>
      ))}
    </Section>
  );
}

function AltOne(props: { a: AltRouting; last: boolean }) {
  const a = props.a;
  const d = a.extraDays;
  return (
    <div class="alt-box">
      <div class="alt-label">{a.label}</div>
      <div class="alt-stats">
        <span class={`alt-days num ${d > 0 ? 'worse' : d < 0 ? 'better' : ''}`} title="Atlas estimate vs the main routing">
          {d > 0 ? '+' : d < 0 ? '−' : '±'}
          {fmt(Math.abs(d))} days
        </span>
        <span class="num">{fmt(a.distanceNm)} nm</span>
      </div>
      {a.via.length > 0 && (
        <div class="chips" style={{ marginTop: '8px' }}>
          {a.via.map((id) => (
            <button class="chip" key={id} onClick={() => select({ kind: 'chokepoint', id })}>
              via {chokepointName(id)}
            </button>
          ))}
        </div>
      )}
      {a.when && <div class="muted small" style={{ marginTop: '6px' }}>{a.when}</div>}
      {a.status?.map((n) => <div class="muted small alt-status" key={n.text}>{n.text}</div>)}
      {props.last && <div class="muted small" style={{ marginTop: '6px' }}>Atlas estimate</div>}
    </div>
  );
}

/**
 * Alternative routings: every entry of `alts` (a lane's alternatives; `alt` alone for a route), or the `note`
 * that says why none is shown (the way round is more than three times as long).
 */
export function AltBox(props: { alt?: AltRouting; alts?: AltRouting[]; note?: string }) {
  const list = props.alts?.length ? props.alts : props.alt ? [props.alt] : [];
  if (!list.length && !props.note) return null;
  return (
    <Section title="Alternative routing">
      {list.map((a, i) => <AltOne key={a.label} a={a} last={i === list.length - 1} />)}
      {!list.length && props.note && <p class="le-note">{props.note}</p>}
    </Section>
  );
}

/** What a flagged year of a history chart is called in the chart's hover list. */
const FLAG_TITLE: Partial<Record<HistFlag, string>> = {
  est: 'Atlas estimate (tonnage from the declared value)',
  check: 'Checked against a national statistic: see the note',
  nodata: 'No figure for this year',
  suspect: 'Not shown: the declared value does not fit the tonnage',
};
const DAY = 86400;

/** Annual history bars (2005-2024 style). `flags` marks the years that are estimated, checked or have no figure. */
export function HistoryChart(props: { years: number[]; values: (number | null)[]; unit: string; color?: string; label?: string; flags?: Record<string, HistFlag>; allEst?: boolean }) {
  const x = useMemo(() => props.years.map((y) => Date.UTC(y, 0, 1) / 1000), [props.years]);
  const series = useMemo(
    () => [{ label: props.label ?? 'Volume', values: props.values, color: props.color ?? '#3ee6ff' }],
    [props.values, props.label, props.color],
  );
  // a ribbon under the bars, one year wide and centred on the bar
  const markers = useMemo<TimeMarker[] | undefined>(() => {
    const out: TimeMarker[] = [];
    for (const [y, f] of Object.entries(props.flags ?? {})) {
      const title = FLAG_TITLE[f];
      if (!title) continue;
      const t = Date.UTC(Number(y), 0, 1) / 1000;
      out.push({ t: t - 182 * DAY, end: t + 182 * DAY, title: `${y}: ${title}`, subtle: true, color: f === 'est' ? '#ffb547' : '#8aa0b8' });
    }
    return out.length ? out : undefined;
  }, [props.flags]);
  // the readout prints an estimated year with the two significant digits the lane figure has; in a group that is an
  // Atlas estimate as a whole (allEst) every year is one
  const estimated = useMemo(() => props.years.map((y) => !!props.allEst || props.flags?.[String(y)] === 'est'), [props.years, props.flags, props.allEst]);
  return <TimeChart x={x} series={series} unit={props.unit} bars xFormat="year" height={130} zoom={false} markers={markers} estimated={estimated} ariaLabel={`Annual volume, ${props.unit}`} />;
}
