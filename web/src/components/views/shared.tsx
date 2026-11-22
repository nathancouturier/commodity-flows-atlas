/** Helpers shared by the freight detail views. */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { AltRouting } from '../../types';
import { commodityMeta, sources } from '../../lib/data';
import { fmt } from '../../lib/format';
import { chokepointName, loadFreightCatalogue, vesselClassList, vesselName, segmentOf, SEGMENT_COLOR } from '../../lib/freight';
import { commodity, select } from '../../lib/store';
import { Section } from '../ui';
import { TimeChart } from '../charts/TimeChart';

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
  return (
    <button class="chip" onClick={() => select({ kind: 'vessel', id: props.id })}>
      <i class="dot" style={{ background: color }} />
      {vesselName(props.id)}
    </button>
  );
}

/** Horizontal strip: load port, true chokepoints in order, discharge port. Ports are plain muted end labels. */
export function RouteStrip(props: { from: string; to: string; via: string[] }) {
  return (
    <div class="strip" role="list">
      <span class="strip-port" role="listitem" title={props.from}>{props.from}</span>
      <span class="strip-link" aria-hidden="true" />
      {props.via.length === 0 && <span class="muted small strip-none" role="listitem">No major chokepoint</span>}
      {props.via.map((id) => (
        <>
          <button class="strip-cp" role="listitem" key={id} onClick={() => select({ kind: 'chokepoint', id })} title={`Open ${chokepointName(id)}`}>
            {chokepointName(id)}
          </button>
          <span class="strip-link" aria-hidden="true" />
        </>
      ))}
      {props.via.length === 0 && <span class="strip-link" aria-hidden="true" />}
      <span class="strip-port" role="listitem" title={props.to}>{props.to}</span>
    </div>
  );
}

export function ViaSection(props: { from: string; to: string; via: string[] }) {
  return (
    <Section title="Chokepoints crossed">
      <RouteStrip from={props.from} to={props.to} via={props.via} />
    </Section>
  );
}

export function AltBox(props: { alt: AltRouting }) {
  const a = props.alt;
  const d = a.extraDays;
  return (
    <Section title="Alternative routing">
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
        <div class="muted small" style={{ marginTop: '6px' }}>Atlas estimate</div>
      </div>
    </Section>
  );
}

/** Annual history bars (2005-2024 style). */
export function HistoryChart(props: { years: number[]; values: (number | null)[]; unit: string; color?: string; label?: string }) {
  const x = useMemo(() => props.years.map((y) => Date.UTC(y, 0, 1) / 1000), [props.years]);
  const series = useMemo(
    () => [{ label: props.label ?? 'Volume', values: props.values, color: props.color ?? '#3ee6ff' }],
    [props.values, props.label, props.color],
  );
  return <TimeChart x={x} series={series} unit={props.unit} bars xFormat="year" height={130} zoom={false} ariaLabel={`Annual volume, ${props.unit}`} />;
}
