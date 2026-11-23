/**
 * Route finder: "if I buy coal from Indonesia to China, which route and vessel class is
 * typical, and what share of that trade does it represent?"
 * Answers for every pair CEPII BACI records for the latest year (the pairs files), whether it is drawn as a
 * lane, only listed, moves overland, moves by sea and overland, or is not recorded. The question can start
 * from the origin or from the destination and lives in the address (`rf=`).
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { batch } from '@preact/signals';
import type { CaveatsFile, Lane, LaneFile, PairsFile, PortRef, Route } from '../types';
import { commodityMeta, countryName } from '../lib/data';
import {
  GROUP_LABEL,
  LANE_GROUPS,
  altLabel,
  altOptions,
  caveatFor,
  chokepointName,
  corridorHas,
  decodePairs,
  familyLabel,
  finderCommodity,
  ladenDays,
  lacksSpeed,
  laneEst,
  loadCaveats,
  loadLaneFile,
  loadPairs,
  loadRoutes,
  originCaveats,
  sameVesselFamily,
  vesselName,
  NO_SPEED,
  type LaneStatus,
  type Pair,
} from '../lib/freight';
import { fmt, pct, sig2 } from '../lib/format';
import { rfCommodity, rfDest, rfFrom, rfGroup, rfOrigin, routeFinderOpen, select } from '../lib/store';
import { isSheetLayout } from '../map/controller';
import { SourceLine } from './ui';
import { PortSource } from './views/shared';
import '../styles/finder.css';

/** One "Coal" entry covers both coal commodities: customs data do not separate thermal and metallurgical coal. */
const COAL = 'coal';
const commodityLabel = (k: string) => (k === COAL ? 'Coal (thermal + met)' : (commodityMeta(k)?.name ?? k));
const groupsOf = (k: string) => (k === COAL ? ['coal'] : (LANE_GROUPS[k] ?? []));
const OPTIONS = [COAL, ...Object.keys(LANE_GROUPS).filter((id) => id !== 'thermal-coal' && id !== 'met-coal')];
/** Below this tonnage (kt) a country is not offered as the starting point of a question. */
const MIN_KT = 50;
/** Lane last opened by the finder itself on a phone: the same answer is not forced open again (a re-opened dropdown, say). */
let autoOpened: string | null = null;

/**
 * Customs tonnes (kt) as printed everywhere in the finder (lists, Flow, overland sentence): Mt from 100 kt, kt below,
 * "under 1 kt" under 1 kt (the files keep 0.1 kt, so nothing finer is known). An estimate keeps two significant digits.
 */
function tonnage(kt: number, est = false): string {
  if (kt < 1) return 'under 1 kt';
  if (kt < 100) {
    const v = est ? sig2(kt) : kt;
    return `${kt < 10 ? fmt(v) : Math.round(v)} kt`;
  }
  const mt = kt / 1000;
  return `${fmt(est ? sig2(mt) : mt)} Mt`;
}
const KIND_HINT: Record<Pair['kind'], string> = { sea: '', transit: '', mixed: 'sea + overland', land: 'overland' };

type Loaded = { k: string; files: PairsFile[]; pairs: Pair[] };

export function RouteFinder() {
  const known = OPTIONS.includes(finderCommodity(rfCommodity.value));
  const k = known ? finderCommodity(rfCommodity.value) : COAL;
  const from = rfFrom.value;
  const origin = rfOrigin.value;
  const dest = rfDest.value;
  const group = rfGroup.value;
  const multi = groupsOf(k).length > 1;
  const [data, setData] = useState<Loaded | 'error' | 'none' | null>(null);
  const [caveats, setCaveats] = useState<CaveatsFile | null>(null);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [laneSlot, setLaneSlot] = useState<{ group: string; file: LaneFile | null } | null>(null);

  // the pairs files of the chosen commodity's groups: every recorded pair of the latest year
  useEffect(() => {
    let live = true;
    setData(null);
    // a group whose pairs file the builder has not written yet is left out; with none at all the commodity has no table yet
    Promise.all(groupsOf(k).map((g) => loadPairs(g).catch(() => null)))
      .then((all) => {
        const files = all.filter((f): f is PairsFile => !!f);
        if (live) setData(files.length ? { k, files, pairs: files.flatMap(decodePairs).sort((a, b) => b.kt - a.kt) } : 'none');
      })
      .catch(() => live && setData('error'));
    return () => {
      live = false;
    };
  }, [k]);
  useEffect(() => {
    loadCaveats().then(setCaveats).catch(() => setCaveats({}));
    loadRoutes().then(setRoutes).catch(() => undefined);
  }, []);

  // a link with a commodity the finder does not know: the question is dropped, the finder starts empty
  useEffect(() => {
    if (known) return;
    batch(() => {
      rfCommodity.value = COAL;
      rfOrigin.value = null;
      rfDest.value = null;
      rfGroup.value = null;
    });
  }, [known]);

  // a group that is not one of the commodity's two products is dropped from the question (and so from the address)
  useEffect(() => {
    if (group && !(multi && groupsOf(k).includes(group))) rfGroup.value = null;
  }, [group, k, multi]);

  const ready = data && data !== 'error' && data !== 'none' && data.k === k ? data : null;
  const pairs = ready?.pairs ?? [];
  const lead = from === 'o' ? origin : dest;
  const other = from === 'o' ? dest : origin;
  const leadOf = (p: Pair) => (from === 'o' ? p.o : p.d);
  const otherOf = (p: Pair) => (from === 'o' ? p.d : p.o);

  // the first field: every country with a recorded flow on that side (an origin that customs data do not record, but that carries a caveat, too)
  const leads = useMemo(() => {
    const sum = new Map<string, number>();
    for (const p of pairs) sum.set(leadOf(p), (sum.get(leadOf(p)) ?? 0) + p.kt);
    const list = [...sum].filter(([, v]) => v >= MIN_KT).sort((a, b) => b[1] - a[1]);
    if (from === 'o' && caveats) {
      const gs = groupsOf(k);
      const unrecorded = new Set(Object.values(caveats).filter((e) => e.o && e.d == null && e.group && gs.includes(e.group)).map((e) => e.o!));
      for (const c of unrecorded) if (!sum.has(c)) list.push([c, 0]);
    }
    if (lead && !list.some(([c]) => c === lead)) list.push([lead, sum.get(lead) ?? 0]);
    return list;
  }, [pairs, from, caveats, lead, k]);

  // the second field: every country with a flow with the first, largest first, one entry per customs group
  const counterparts = useMemo(() => (lead ? pairs.filter((p) => leadOf(p) === lead) : []), [pairs, lead, from]);
  // pairs that customs data do not record but a caveat explains (crude oil from Russia to Turkey): offered too, so the caveat can be reached
  const absent = useMemo(() => {
    const out: { group: string; c: string }[] = [];
    if (!lead || !caveats) return out;
    const gs = groupsOf(k);
    for (const e of Object.values(caveats)) {
      const c = from === 'o' ? (e.o === lead ? e.d : null) : e.d === lead ? e.o : null;
      if (!c || !e.group || !gs.includes(e.group)) continue;
      const g = e.group;
      if (counterparts.some((p) => p.group === g && otherOf(p) === c) || out.some((a) => a.group === g && a.c === c)) continue;
      out.push({ group: g, c });
    }
    return out;
  }, [lead, caveats, counterparts, from, k]);

  const sel = useMemo(() => {
    if (!origin || !dest) return undefined;
    const both = pairs.filter((p) => p.o === origin && p.d === dest);
    return both.find((p) => p.group === group) ?? both[0];
  }, [pairs, origin, dest, group]);

  // the lane file of the answer: the lane itself when the pair is drawn, the ports' source pages when it is only routed
  const selGroup = sel && (sel.lane || (sel.load && sel.dis)) ? sel.group : null;
  useEffect(() => {
    if (!selGroup) return;
    let live = true;
    loadLaneFile(selGroup)
      .then((f) => live && setLaneSlot({ group: selGroup, file: f }))
      .catch(() => live && setLaneSlot({ group: selGroup, file: null }));
    return () => {
      live = false;
    };
  }, [selGroup]);
  const laneFile = selGroup && laneSlot?.group === selGroup ? laneSlot.file : null;
  // a drawn pair waits for its lane file (a card without the lane's own figures would change under the reader's eyes)
  const waiting = !!sel?.lane && laneSlot?.group !== sel.group;
  // only a main lane is drawn (a pair that was large in some earlier year has a history lane the file also holds)
  const lane = sel?.lane && laneFile?.group === sel.group ? laneFile.lanes.find((l) => l.o === sel.o && l.d === sel.d) : undefined;
  const pf = sel ? ready?.files.find((f) => f.group === sel.group) : undefined;

  const complete = !!(origin && dest && ready);
  const benchmarks = useMemo(() => {
    if (!sel || !pf || sel.kind === 'land') return [];
    return routes.filter((r) => corridorHas(r, pf.group, sel.o, sel.d));
  }, [sel, pf, routes]);

  const root = useRef<HTMLDivElement>(null);
  const matchId = lane?.id;
  // bottom-sheet layouts: the answer sits far below the lists and the open sheet hides the map, so
  // a found route opens its page (the lane is drawn and framed above the sheet); an answer without a lane is scrolled to
  useEffect(() => {
    if (!complete) {
      autoOpened = null;
      return;
    }
    if (!isSheetLayout()) return;
    if (matchId) {
      if (autoOpened === matchId) return;
      autoOpened = matchId;
      select({ kind: 'lane', id: matchId });
    } else if (!sel?.lane) {
      root.current?.querySelector('.rf-card')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [complete, matchId]);

  const setLead = (c: string | null) =>
    batch(() => {
      if (from === 'o') {
        rfOrigin.value = c;
        rfDest.value = null;
      } else {
        rfDest.value = c;
        rfOrigin.value = null;
      }
      rfGroup.value = null;
    });
  const setOther = (v: string) =>
    batch(() => {
      const i = v.indexOf(':');
      const c = i < 0 ? null : v.slice(i + 1) || null;
      if (from === 'o') rfDest.value = c;
      else rfOrigin.value = c;
      rfGroup.value = c && multi ? v.slice(0, i) : null;
    });

  const originCav = from === 'o' && origin && ready && !counterparts.length && caveats ? originCaveats(caveats, groupsOf(k), origin) : [];

  // Start from: with only one end chosen, that end moves into the first field of the new direction
  const switchFrom = (f: 'o' | 'd') => {
    if (f === from) return;
    batch(() => {
      if (!(origin && dest)) {
        const c = origin ?? dest;
        rfOrigin.value = f === 'o' ? c : null;
        rfDest.value = f === 'd' ? c : null;
        rfGroup.value = null;
      }
      rfFrom.value = f;
    });
  };

  const gs = groupsOf(k);
  const otherValue = sel
    ? `${sel.group}:${other}`
    : other
      ? `${group && gs.includes(group) ? group : (absent.find((a) => a.c === other)?.group ?? gs[0])}:${other}`
      : '';
  const absentGroups = gs.filter((g) => !group || g === group);
  // no row for the pair: the caveats that name it (and, unless the origin's own card shows it, the origin's)
  const noRowCav =
    complete && !sel && caveats
      ? [...new Map(absentGroups.map((g) => caveatFor(caveats, g, origin!, dest!)).filter((x) => x && (x.entry.d === dest || !originCav.length)).map((x) => [x!.id, x!])).values()]
      : [];
  const noRowExplained = noRowCav.some((x) => x.entry.d === dest);
  const leadName = from === 'o' ? 'origin' : 'destination';
  const otherName = from === 'o' ? 'destination' : 'origin';

  const announce = !complete
    ? ''
    : !sel
      ? `No trade recorded between ${countryName(origin!)} and ${countryName(dest!)}.`
      : waiting
        ? 'Loading the route…'
        : [
            `${countryName(sel.o)} to ${countryName(sel.d)}, ${multi ? (GROUP_LABEL[sel.group] ?? sel.group) : commodityLabel(k)}: ${tonnage(sel.kt, sel.est)}`,
            sel.kind === 'land' ? 'overland' : sel.kind === 'mixed' ? 'sea and overland' : sel.nm > 0 && sel.cls ? `${vesselName(sel.cls)}, ${fmt(sel.nm)} nautical miles` : 'sea, no route modelled',
          ].join(', ') + '.';

  return (
    <div class="rf" ref={root}>
      <label class="rf-field">
        <span>Commodity</span>
        <select
          class="rf-select"
          value={k}
          onChange={(e) =>
            batch(() => {
              rfCommodity.value = (e.target as HTMLSelectElement).value;
              rfOrigin.value = null;
              rfDest.value = null;
              rfGroup.value = null;
            })
          }
        >
          {OPTIONS.map((id) => (
            <option value={id}>{commodityLabel(id)}</option>
          ))}
        </select>
        {k === COAL && <small class="rf-note">Customs data do not separate thermal and metallurgical coal.</small>}
      </label>
      <div class="rf-switch" role="group" aria-label="Start from">
        <span>Start from</span>
        <span class="rf-switch-seg">
          <button type="button" aria-pressed={from === 'o'} onClick={() => switchFrom('o')}>
            Origin
          </button>
          <button type="button" aria-pressed={from === 'd'} onClick={() => switchFrom('d')}>
            Destination
          </button>
        </span>
      </div>
      <label class="rf-field">
        <span>{from === 'o' ? 'Origin' : 'Destination'}</span>
        <select class="rf-select" value={lead ?? ''} disabled={!ready} onChange={(e) => setLead((e.target as HTMLSelectElement).value || null)}>
          <option value="">{data === 'error' || data === 'none' ? 'Not available' : ready ? `Select ${leadName}…` : 'Loading…'}</option>
          {leads.map(([c, v]) => (
            <option value={c}>
              {countryName(c)} · {v > 0 ? tonnage(v) : 'no recorded tonnage'}
            </option>
          ))}
        </select>
      </label>
      <label class="rf-field">
        <span>{from === 'o' ? 'Destination' : 'Origin'}</span>
        <select class="rf-select" value={otherValue} disabled={!lead} onChange={(e) => setOther((e.target as HTMLSelectElement).value)}>
          <option value="">Select {otherName}…</option>
          {counterparts.map((p) => (
            <option value={`${p.group}:${otherOf(p)}`}>
              {[countryName(otherOf(p)), multi ? (GROUP_LABEL[p.group] ?? p.group) : '', tonnage(p.kt, p.est), KIND_HINT[p.kind]].filter(Boolean).join(' · ')}
            </option>
          ))}
          {absent.map((a) => (
            <option value={`${a.group}:${a.c}`}>{[countryName(a.c), multi ? (GROUP_LABEL[a.group] ?? a.group) : '', 'no recorded tonnage'].filter(Boolean).join(' · ')}</option>
          ))}
          {lead && other && !sel && !absent.some((a) => a.c === other) && <option value={otherValue}>{countryName(other)} · no record</option>}
        </select>
      </label>

      {(data === 'error' || data === 'none') && (
        <div class="rf-card">
          <p class="rf-empty">{data === 'none' ? 'The atlas has no trade table for this commodity yet.' : 'The trade table for this commodity could not be loaded.'}</p>
        </div>
      )}
      {originCav.length > 0 && origin && (
        <div class="rf-card">
          <div class="rf-title">
            {countryName(origin)}
            <small>{commodityLabel(k)}</small>
          </div>
          {originCav.map(({ id, entry }) => (
            <div class="rf-status" role="note" key={id}>
              <span>{entry.text}</span>
            </div>
          ))}
        </div>
      )}
      {complete && !sel && (
        <div class="rf-card">
          {noRowCav.map(({ id, entry }) => (
            <div class="rf-status" role="note" key={id}>
              <span>{entry.text}</span>
            </div>
          ))}
          <p class="rf-empty">
            No trade recorded between {countryName(origin!)} and {countryName(dest!)} for this commodity (CEPII BACI {ready!.files[0]?.y ?? ''}
            {noRowExplained ? '' : '; flows under 1,000 t and USD 1 million are not kept'}).
          </p>
        </div>
      )}
      {sel && pf && (
        <Answer
          key={`${sel.group}:${sel.o}-${sel.d}`}
          pair={sel}
          pf={pf}
          lane={lane}
          laneFile={laneFile?.group === sel.group ? laneFile : null}
          laneSettled={!selGroup || laneSlot?.group === selGroup}
          loading={waiting}
          caveats={caveats}
          benchmarks={benchmarks}
          name={multi ? (GROUP_LABEL[sel.group] ?? sel.group) : commodityLabel(k)}
          importsKt={ready!.pairs.filter((p) => p.group === sel.group && p.d === sel.d).reduce((s, p) => s + p.kt, 0)}
        />
      )}
      <div class="sr-only" role="status" aria-live="polite">
        {announce}
      </div>
    </div>
  );
}

function Answer({
  pair,
  pf,
  lane,
  laneFile,
  laneSettled,
  loading,
  caveats,
  benchmarks,
  name,
  importsKt,
}: {
  pair: Pair;
  pf: PairsFile;
  lane?: Lane;
  laneFile: LaneFile | null;
  /** the lane file has loaded (or failed): port source pages are known */
  laneSettled: boolean;
  loading: boolean;
  caveats: CaveatsFile | null;
  benchmarks: Route[];
  name: string;
  importsKt: number;
}) {
  const { kind } = pair;
  const title = (
    <div class="rf-title">
      {countryName(pair.o)} → {countryName(pair.d)}
      <small>{name}</small>
    </div>
  );
  const est = lane ? laneEst(lane) : pair.est;
  const vy = lane?.flow.y ?? pf.y;

  if (loading) {
    return (
      <div class="rf-card">
        {title}
        <p class="rf-empty">Loading the route…</p>
      </div>
    );
  }

  // overland or pipeline: nothing to route
  if (kind === 'land') {
    return (
      <div class="rf-card">
        {title}
        <p class="rf-empty">
          Recorded as overland or pipeline trade: <span class="num">{tonnage(pair.kt, est)}</span> (CEPII BACI {pf.y}).
        </p>
        <Notes pair={pair} pf={pf} lane={lane} caveats={caveats} est={est} />
      </div>
    );
  }

  const routed = pair.nm > 0 && !!pair.load && !!pair.dis;
  const shown = lane ?? undefined;
  const portName = (id: string) => laneFile?.ports[id]?.name ?? id;
  const loadIds = shown ? shown.load : pair.load ? [pair.load.id] : [];
  const disIds = shown ? shown.discharge : pair.dis ? [pair.dis.id] : [];
  const pairBasis = (id: string) => [pair.load, pair.dis].find((p) => p?.id === id)?.basis;
  const portsOf = (ids: string[]) =>
    ids.map((id, i) => (
      <span key={id}>
        {i > 0 && ', '}
        {shown ? portName(id) : ([pair.load, pair.dis].find((p) => p?.id === id)?.name ?? id)}
        <PortSource p={laneFile?.ports[id]} basis={pairBasis(id)} settled={laneSettled} cls="rf-src" />
      </span>
    ));
  const status = (shown as (Lane & { status?: LaneStatus[] }) | undefined)?.status ?? [];
  const classes = shown ? shown.vclass : pair.cls ? [pair.cls] : [];
  const typical = classes[0];
  const via = shown ? shown.via : pair.via;
  const alsoVia = shown ? (shown.viaAlt ?? []) : pair.viaAltLists;
  const alts = shown ? (shown.alts ?? (shown.alt ? [shown.alt] : [])) : [];
  const nm = shown ? shown.distanceNm : pair.nm;
  // from the pairs row, as the chokepoint list does (a lane's stored share is rounded to four decimals)
  const share = kind === 'mixed' ? null : pair.kt / pf.seaborne;
  const shareDest = est ? null : shown ? (shown.shareDest ?? null) : importsKt > 0 ? pair.kt / importsKt : null;
  // the flow figure is the pairs row's, so the list, the card and the overland sentence print the same number
  const kt = pair.kt;
  const transits =
    kind !== 'transit'
      ? []
      : shown?.transit
        ? [shown.transit, shown.transit2].filter((t): t is NonNullable<typeof t> => !!t).map((t) => ({ id: t.port, name: portName(t.port), c: t.c as string | undefined, p: { s: t.s, url: t.url, basis: t.url && laneFile?.ports[t.port]?.url === t.url ? laneFile.ports[t.port].basis : undefined } as Partial<PortRef> }))
        : transitPorts(pair).map((t) => ({ ...t, p: laneFile?.ports[t.id] }));
  // a class with no speed in the catalogue: the days cannot be checked against a speed, so none is printed and the card says so
  const noSpeed = !!typical && lacksSpeed(typical);
  const days = noSpeed ? undefined : shown ? shown.days : ladenDays(nm, typical ?? null)?.days;
  const speed = !shown ? ladenDays(nm, typical ?? null) : null;

  return (
    <div class="rf-card">
      {title}
      {shown && (
        <button class="rf-map-btn rf-map-top" onClick={() => select({ kind: 'lane', id: shown.id })}>
          Show on map
        </button>
      )}
      {kind === 'mixed' && (
        <div class="rf-status" role="note">
          <span>Moves by sea and overland; the split is not known. The tonnage is the customs total for all modes, so it is not counted as seaborne.</span>
        </div>
      )}
      <dl class="rf-stats">
        <div>
          <dt>
            {kind === 'mixed' ? 'Flow, all modes' : 'Flow'}
            {est && <em class="rf-est">Atlas estimate</em>}
          </dt>
          <dd class="num">
            {tonnage(kt, est)}
            <small> · {vy}</small>
          </dd>
        </div>
        {share != null && (
          <div>
            <dt>Share of seaborne trade</dt>
            <dd class="num">{pct(share, true)}</dd>
          </div>
        )}
        {shareDest != null && (
          <div>
            <dt>Share of {countryName(pair.d)} imports</dt>
            <dd class="num">{pct(shareDest, true)}</dd>
          </div>
        )}
        {routed && (
          <div>
            <dt>{days != null ? 'Distance · laden' : 'Distance'}</dt>
            <dd class="num" title={speed?.note ?? (noSpeed ? `The atlas publishes ${NO_SPEED}` : shown ? 'At the assumed laden service speed of the primary vessel class (Atlas assumption)' : undefined)}>
              {fmt(nm)} nm{days != null ? ` · ${fmt(days)} days` : ''}
              {days == null && noSpeed && <small> · {NO_SPEED}</small>}
            </dd>
          </div>
        )}
      </dl>
      <SourceLine s={est ? 'atlas' : (shown?.flow.s ?? pf.s)} y={vy} n="flow and shares" />
      <Notes pair={pair} pf={pf} lane={shown} caveats={caveats} est={est} />

      {!routed ? (
        <p class="rf-empty">
          {kind === 'transit'
            ? 'Sea through a port of another country, which the atlas does not know. No route is modelled.'
            : 'Counted as seaborne, but no route is modelled: a port is missing for one end, or both ends use the same port.'}
        </p>
      ) : (
        <>
          {transits.length > 0 && (
            <p class="rf-line">
              Sea via{' '}
              {transits.map((t, i) => (
                <span key={t.id}>
                  {i > 0 && ' and '}
                  {t.name}
                  {t.c ? ` (${countryName(t.c)})` : ''}
                  <PortSource p={t.p} basis={pairBasis(t.id)} settled={laneSettled} cls="rf-src" />
                </span>
              ))}
              : {transits.length > 1 ? 'both ends are landlocked and ship through ports of other countries.' : 'the landlocked end ships through a port of another country.'}
            </p>
          )}
          <dl class="rf-stats rf-ports">
            <div>
              <dt>Load port{loadIds.length > 1 ? 's' : ''}</dt>
              <dd>{loadIds.length ? portsOf(loadIds) : 'n/a'}</dd>
            </div>
            <div>
              <dt>Discharge port{disIds.length > 1 ? 's' : ''}</dt>
              <dd>{disIds.length ? portsOf(disIds) : 'n/a'}</dd>
            </div>
          </dl>
          {shown?.opts && shown.opts.length > 0 && (
            <>
              <div class="rf-sub">Other port options</div>
              {shown.opts.map((o) => (
                <p class="rf-line">
                  {portName(o.load)} → {portName(o.discharge)}: <span class="num">{fmt(o.nm)} nm</span>, <span class="num">{fmt(o.days)} days</span>
                  {o.via.length > 0 && <> · via {o.via.map(chokepointName).join(', ')}</>}
                </p>
              ))}
              <p class="rf-small">The ports above are each country's principal gateway; customs data do not say which port the cargo used.</p>
            </>
          )}
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
            {classes.length ? (
              classes.map((v, i) => (
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
            {via.length ? (
              via.map((c) => (
                <button class="rf-tag rf-link" onClick={() => select({ kind: 'chokepoint', id: c })}>
                  {chokepointName(c)}
                </button>
              ))
            ) : (
              <span class="muted">{alsoVia.length ? 'None on every option' : 'None (direct passage)'}</span>
            )}
          </div>
          {alsoVia.map((list) => (
            <div class="rf-tags rf-or">
              <span>{altLabel(list)}</span>
              {altOptions(list).map((option, i, all) => (
                <>
                  {option.map((c, j) => (
                    <>
                      {j > 0 && <span>and</span>}
                      <button class="rf-tag rf-link" onClick={() => select({ kind: 'chokepoint', id: c })}>
                        {chokepointName(c)}
                      </button>
                    </>
                  ))}
                  {i < all.length - 1 && <span aria-hidden="true">·</span>}
                </>
              ))}
            </div>
          ))}

          {alts.length > 0 && (
            <>
              <div class="rf-sub">Alternative routing</div>
              {alts.map((a) => (
                <p class="rf-alt">
                  {a.label}: <span class="num">{fmt(a.distanceNm)} nm</span>,{' '}
                  <span class="num">
                    {a.extraDays > 0 ? '+' : ''}
                    {fmt(a.extraDays)} days
                  </span>
                </p>
              ))}
            </>
          )}
          {shown?.altNote && <p class="rf-small">{shown.altNote}</p>}
          {speed && (
            <p class="rf-small">
              Days at {speed.speedKn} kn, the assumed laden service speed of the {vesselName(typical!)} (Atlas assumption).
            </p>
          )}
          <div class="src-line">Atlas estimate · {pf.y} · vessel classes, distances{days != null ? ' and days' : ''}</div>
          {!shown && !pair.lane && <p class="rf-small">Not drawn on the map (below the lanes shown for this commodity).</p>}

          {benchmarks.length > 0 && (
            <>
              <div class="rf-sub">Routes on this corridor</div>
              <div class="muted small">Ports and distance above are this country-to-country pair's own; the routes below have their own ports and distance.</div>
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
        </>
      )}
    </div>
  );
}

/** The sea route's transit ports, from the pairs table, when the lane does not name them: the ports that lie in a third country (one per landlocked end). */
function transitPorts(pair: Pair): { id: string; name: string; c?: string }[] {
  const foreign = (p: Pair['load'], end: string) => (p && p.c.length === 3 && p.c !== end ? { id: p.id, name: p.name, c: p.c } : null);
  return [foreign(pair.load, pair.o), foreign(pair.dis, pair.d)].filter((t): t is NonNullable<typeof t> => !!t);
}

/** Caveat box, estimate note and check note of an answer. */
function Notes({ pair, pf, lane, caveats, est }: { pair: Pair; pf: PairsFile; lane?: Lane; caveats: CaveatsFile | null; est: boolean }) {
  const cav = lane?.caveat && caveats?.[lane.caveat] ? caveats[lane.caveat] : pair.caveat ? caveatFor(caveats, pair.group, pair.o, pair.d)?.entry : undefined;
  // the lane's note, or the pairs file's for a pair that has no lane
  const note = lane?.flow.n ?? pf.notes?.[`${pair.o}-${pair.d}`];
  return (
    <>
      {cav && (
        <div class="rf-status" role="note">
          <span>{cav.text}</span>
        </div>
      )}
      {est && (
        <p class="rf-small">
          {note?.startsWith('Atlas estimate')
            ? note
            : 'Atlas estimate: the atlas computed this tonnage from the declared value (CEPII BACI) and a reference unit value; the inputs for this pair are not published yet. The method is in the methodology.'}
        </p>
      )}
      {pair.flagged && (
        <p class="rf-small">
          {note && !est
            ? note
            : 'An atlas data check flags this figure: it changed sharply against the previous year, or differs from another source. Treat it with care.'}
        </p>
      )}
    </>
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
