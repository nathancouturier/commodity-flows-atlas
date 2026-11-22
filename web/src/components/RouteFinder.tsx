/**
 * Route finder: "if I buy coal from Indonesia to China, which route and vessel class is
 * typical, and what share of that trade does it represent?"
 * Answers from the seaborne lane files (CEPII BACI customs data + Atlas estimates) and
 * links the matching Baltic / benchmark routes.
 */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { Lane, LaneFile, Route } from '../types';
import { commodityMeta, countryName } from '../lib/data';
import { LANE_GROUPS, chokepointName, familyLabel, loadLaneFile, loadRoutes, sameVesselFamily, vesselName, type LaneStatus } from '../lib/freight';
import { fmt, pct } from '../lib/format';
import { rfCommodity, rfDest, rfOrigin, routeFinderOpen, select } from '../lib/store';
import { SourceLine } from './ui';

type Row = { lane: Lane; file: LaneFile };

/** One "Coal" entry covers both coal commodities: customs data do not separate thermal and metallurgical coal. */
const COAL = 'coal';
const commodityLabel = (k: string) => (k === COAL ? 'Coal (thermal + met)' : (commodityMeta(k)?.name ?? k));
const groupsOf = (k: string) => (k === COAL ? ['coal'] : (LANE_GROUPS[k] ?? []));
const OPTIONS = [COAL, ...Object.keys(LANE_GROUPS).filter((id) => id !== 'thermal-coal' && id !== 'met-coal')];
/** Below this volume a lane is not offered as a destination (and never shown as "0.0 Mt"). */
const MIN_FLOW = 0.05;
const OTHER = '__other';

export function RouteFinder() {
  const k0 = rfCommodity.value;
  const k = k0 === 'thermal-coal' || k0 === 'met-coal' ? COAL : k0;
  const [otherMode, setOtherMode] = useState(false);
  const origin = rfOrigin.value;
  const dest = rfDest.value;
  const [rows, setRows] = useState<Row[] | null>(null);
  const [routes, setRoutes] = useState<Route[]>([]);

  // load the lane files of the chosen commodity's groups
  useEffect(() => {
    let live = true;
    setRows(null);
    Promise.all(groupsOf(k).map((g) => loadLaneFile(g).catch(() => null))).then((files) => {
      if (live) setRows(files.flatMap((f) => (f ? f.lanes.map((lane) => ({ lane, file: f })) : [])));
    });
    return () => {
      live = false;
    };
  }, [k]);
  useEffect(() => {
    loadRoutes().then(setRoutes).catch(() => undefined);
  }, []);

  const origins = useMemo(() => {
    const sum = new Map<string, number>();
    for (const { lane } of rows ?? []) sum.set(lane.o, (sum.get(lane.o) ?? 0) + lane.flow.v);
    return [...sum].filter(([, v]) => v >= MIN_FLOW).sort((a, b) => b[1] - a[1]);
  }, [rows]);

  const { dests, others } = useMemo(() => {
    const mine = (rows ?? []).filter((r) => r.lane.o === origin).sort((a, b) => b.lane.flow.v - a.lane.flow.v);
    const big = mine.filter((r) => r.lane.flow.v >= MIN_FLOW);
    const have = new Set(big.map((r) => r.lane.d));
    // everything else (small or absent flows) sits behind "Other destination…"
    const rest = [...new Set((rows ?? []).map((r) => r.lane.d))].filter((d) => !have.has(d) && d !== origin);
    rest.sort((a, b) => countryName(a).localeCompare(countryName(b)));
    return { dests: big, others: rest };
  }, [rows, origin]);
  const showOther = otherMode || (!!dest && others.includes(dest));

  const match = origin && dest ? rows?.find((r) => r.lane.o === origin && r.lane.d === dest) : undefined;
  const complete = !!(origin && dest && rows);
  const unit = rows?.[0]?.file.unit ?? 'Mt';

  const benchmarks = useMemo(() => {
    if (!match) return [];
    const { lane } = match;
    return routes.filter((r) => r.corridor?.some((c) => c.k === lane.k && c.o.includes(lane.o) && c.d.includes(lane.d)));
  }, [match, routes]);

  return (
    <div class="rf">
      <label class="rf-field">
        <span>Commodity</span>
        <select
          class="rf-select"
          value={k}
          onChange={(e) => {
            rfCommodity.value = (e.target as HTMLSelectElement).value;
            rfOrigin.value = null;
            rfDest.value = null;
            setOtherMode(false);
          }}
        >
          {OPTIONS.map((id) => (
            <option value={id}>{commodityLabel(id)}</option>
          ))}
        </select>
        {k === COAL && <small class="rf-note">Customs data do not separate thermal and metallurgical coal.</small>}
      </label>
      <label class="rf-field">
        <span>Origin</span>
        <select
          class="rf-select"
          value={origin ?? ''}
          disabled={!rows}
          onChange={(e) => {
            rfOrigin.value = (e.target as HTMLSelectElement).value || null;
            rfDest.value = null;
            setOtherMode(false);
          }}
        >
          <option value="">{rows ? 'Select origin…' : 'Loading…'}</option>
          {origins.map(([c, v]) => (
            <option value={c}>
              {countryName(c)} · {fmt(v)} {unit}
            </option>
          ))}
        </select>
      </label>
      <label class="rf-field">
        <span>Destination</span>
        <select
          class="rf-select"
          value={showOther ? OTHER : (dest ?? '')}
          disabled={!origin}
          onChange={(e) => {
            const v = (e.target as HTMLSelectElement).value;
            if (v === OTHER) {
              setOtherMode(true);
              rfDest.value = null;
            } else {
              setOtherMode(false);
              rfDest.value = v || null;
            }
          }}
        >
          <option value="">Select destination…</option>
          {dests.map(({ lane }) => (
            <option value={lane.d}>
              {countryName(lane.d)} · {fmt(lane.flow.v)} {unit}
            </option>
          ))}
          {others.length > 0 && <option value={OTHER}>Other destination…</option>}
        </select>
      </label>
      {showOther && (
        <label class="rf-field">
          <span>Other destination</span>
          <select class="rf-select" value={dest ?? ''} onChange={(e) => (rfDest.value = (e.target as HTMLSelectElement).value || null)}>
            <option value="">Select country…</option>
            {others.map((d) => (
              <option value={d}>{countryName(d)}</option>
            ))}
          </select>
        </label>
      )}

      {complete && !match && (
        <div class="rf-card">
          <p class="rf-empty">No significant seaborne flow recorded (CEPII BACI 2024).</p>
        </div>
      )}
      {match && <Result row={match} benchmarks={benchmarks} />}
    </div>
  );
}

function Result({ row, benchmarks }: { row: Row; benchmarks: Route[] }) {
  const { lane, file } = row;
  const name = file.label || commodityLabel(lane.k);
  const portNames = (ids: string[]) => ids.map((id) => file.ports[id]?.name ?? id).join(', ');
  const status = (lane as Lane & { status?: LaneStatus[] }).status ?? [];
  const typical = lane.vclass[0];
  return (
    <div class="rf-card">
      <div class="rf-title">
        {countryName(lane.o)} → {countryName(lane.d)}
        <small>{name}</small>
      </div>
      <button class="rf-map-btn rf-map-top" onClick={() => select({ kind: 'lane', id: lane.id })}>
        Show on map
      </button>
      <dl class="rf-stats">
        <div>
          <dt>Flow</dt>
          <dd class="num">
            {fmt(lane.flow.v)} {lane.flow.u}
            <small> · {lane.flow.y}</small>
          </dd>
        </div>
        <div>
          <dt>Share of seaborne trade</dt>
          <dd class="num">{pct(lane.share)}</dd>
        </div>
        {lane.shareDest != null && (
          <div>
            <dt>Share of {countryName(lane.d)}'s imports</dt>
            <dd class="num">{pct(lane.shareDest)}</dd>
          </div>
        )}
        <div>
          <dt>Distance · laden</dt>
          <dd class="num">
            {fmt(lane.distanceNm)} nm · {fmt(lane.days)} days
          </dd>
        </div>
      </dl>
      <SourceLine s={lane.flow.s} y={lane.flow.y} n="flow and shares" />

      <dl class="rf-stats rf-ports">
        <div>
          <dt>Load port{lane.load.length > 1 ? 's' : ''}</dt>
          <dd>{lane.load.length ? portNames(lane.load) : 'n/a'}</dd>
        </div>
        <div>
          <dt>Discharge port{lane.discharge.length > 1 ? 's' : ''}</dt>
          <dd>{lane.discharge.length ? portNames(lane.discharge) : 'n/a'}</dd>
        </div>
      </dl>
      {status.map((st) => (
        <div class="rf-status" role="note">
          <span>{st.text}</span>
          {st.event && (
            <button class="rf-status-link" onClick={() => select({ kind: 'event', id: st.event! })}>
              View event
            </button>
          )}
        </div>
      ))}

      <div class="rf-sub">Typical vessel class</div>
      <div class="rf-tags">
        {lane.vclass.length ? (
          lane.vclass.map((v, i) => (
            <span class="rf-tag">
              {vesselName(v)}
              {i === 0 && <em>typical</em>}
            </span>
          ))
        ) : (
          <span class="muted">n/a</span>
        )}
      </div>

      <div class="rf-sub">Chokepoints crossed</div>
      <div class="rf-tags">
        {lane.via.length ? (
          lane.via.map((c) => (
            <button class="rf-tag rf-link" onClick={() => select({ kind: 'chokepoint', id: c })}>
              {chokepointName(c)}
            </button>
          ))
        ) : (
          <span class="muted">None (direct passage)</span>
        )}
      </div>

      {lane.alt && (
        <>
          <div class="rf-sub">Alternative routing</div>
          <p class="rf-alt">
            {lane.alt.label}: <span class="num">{fmt(lane.alt.distanceNm)} nm</span>,{' '}
            <span class="num">{lane.alt.extraDays > 0 ? '+' : ''}{fmt(lane.alt.extraDays)} days</span>
          </p>
        </>
      )}
      <div class="src-line">Atlas estimate · {file.y} · vessel classes, distances and days</div>

      {benchmarks.length > 0 && (
        <>
          <div class="rf-sub">Benchmark routes</div>
          {benchmarks.map((r) => (
            <button class="list-btn rf-route" onClick={() => select({ kind: 'route', id: r.id })}>
              {r.benchmark && <span class="code">{r.id}</span>}
              <span class="rf-route-name">{r.name}</span>
              <span class="meta">
                {typical && r.vclass !== typical && sameVesselFamily(typical, r.vclass) ? (familyLabel(r.vclass) ?? vesselName(r.vclass)) : vesselName(r.vclass)}
              </span>
            </button>
          ))}
        </>
      )}

    </div>
  );
}

/**
 * Where the finder lives in the side panel: always expanded on the Freight tab,
 * behind a single "Route finder" button elsewhere.
 */
export function RouteFinderSlot({ always }: { always?: boolean }) {
  const open = always || routeFinderOpen.value;
  return (
    <>
      {!always && (
        <button class="rf-toggle" aria-expanded={open} onClick={() => (routeFinderOpen.value = !open)}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M2 11c3 0 2-8 5-8s2 8 5 8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
          Route finder
          <span class="chev" aria-hidden="true">{open ? '–' : '+'}</span>
        </button>
      )}
      {open && <RouteFinder />}
    </>
  );
}
