/**
 * Left parameters panel: commodity picker, layer toggles, map colouring, filters.
 * Everything beyond the default "flows" layer is one click away here.
 */
import { useEffect, useState } from 'preact/hooks';
import { commodities } from '../lib/data';
import {
  family,
  commodity,
  layers,
  toggleLayer,
  metric,
  select,
  panelCollapsed,
  selection,
  vesselClasses,
  infraTypes,
  toggleInSet,
  type Metric,
} from '../lib/store';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import { SEGMENT_COLOR, SEGMENT_LABEL, loadRoutes, segmentOf, vesselClassList, vesselMatches, vesselName } from '../lib/freight';
import { RouteFinderSlot } from './RouteFinder';
import { Section, Switch, InfraIcon, INFRA_META, INFRA_ORDER } from './ui';
import type { Family, Route, Segment } from '../types';

const METRICS: { id: Metric; label: string }[] = [
  { id: 'none', label: 'Off' },
  { id: 'production', label: 'Production' },
  { id: 'reserves', label: 'Reserves' },
  { id: 'consumption', label: 'Consumption' },
  { id: 'exports', label: 'Exports' },
  { id: 'imports', label: 'Imports' },
];

const FAMILIES: Family[] = ['energy', 'metals', 'softs'];

export function SidePanel() {
  const fam = family.value;
  const list = commodities.value.filter((c) => c.family !== 'freight' && (fam === 'all' || fam === 'freight' || c.family === fam));
  const groups = FAMILIES.filter((f) => fam === 'all' || fam === 'freight' || f === fam);
  const freight = fam === 'freight';
  const current = commodities.value.find((c) => c.id === commodity.value);

  return (
    <aside class={`side-panel glass ${panelCollapsed.value ? 'collapsed' : ''}`} aria-label="Map parameters">
      <div class="panel-scroll">
        <Section title="Map layers">
          <Switch label="Physical flows" checked={layers.value.flows} onChange={(v) => toggleLayer('flows', v)} />
          <Switch label="Freight routes" checked={layers.value.routes} onChange={(v) => toggleLayer('routes', v)} />
          <Switch label="Chokepoints" checked={layers.value.chokepoints} onChange={(v) => toggleLayer('chokepoints', v)} />
          <Switch
            label="Infrastructure"
            checked={layers.value.infrastructure}
            onChange={(v) => toggleLayer('infrastructure', v)}
          />
          {layers.value.infrastructure && <InfraTypeChips />}
        </Section>

        {freight ? (
          <>
            <Section title="Route finder">
              <RouteFinderSlot always />
            </Section>
            <VesselFilter />
            <RouteList />
          </>
        ) : (
          <>
            <div class="rf-top">
              <RouteFinderSlot />
            </div>
        <Section title="Colour countries by" aside={current ? <span class="muted">{current.name}</span> : null}>
          <div class="chips" role="radiogroup">
            {METRICS.map((m) => (
              <button
                class="chip"
                role="radio"
                aria-checked={metric.value === m.id}
                aria-pressed={metric.value === m.id}
                disabled={m.id !== 'none' && !current}
                style={{ opacity: m.id !== 'none' && !current ? 0.4 : 1 }}
                onClick={() => (metric.value = m.id)}
              >
                {m.label}
              </button>
            ))}
          </div>
          {!current && <p class="muted" style={{ fontSize: '12px', margin: '8px 0 0' }}>Pick a commodity to colour the map.</p>}
        </Section>

        {groups.map((g) => {
          const items = list.filter((c) => c.family === g);
          if (!items.length) return null;
          return (
            <Section key={g} title={<span style={{ color: FAMILY_COLOR[g] }}>{FAMILY_LABEL[g]}</span>}>
              {items.map((c) => (
                <button
                  class="list-btn"
                  aria-pressed={commodity.value === c.id}
                  onClick={() => {
                    const same = commodity.value === c.id;
                    commodity.value = same ? null : c.id;
                    select(same ? null : { kind: 'commodity', id: c.id });
                  }}
                >
                  <span class="dot" style={{ color: FAMILY_COLOR[c.family], width: '6px', height: '6px' }} />
                  {c.name}
                  <span class="meta">{c.unit}</span>
                </button>
              ))}
            </Section>
          );
        })}
          </>
        )}
      </div>
    </aside>
  );
}

/** Infrastructure type filter: empty selection = all types. */
function InfraTypeChips() {
  const sel = infraTypes.value;
  return (
    <div class="infra-filter">
      <div class="chips">
        {INFRA_ORDER.map((t) => (
          <button class="chip chip-infra" key={t} aria-pressed={sel.has(t)} onClick={() => toggleInSet(infraTypes, t)} title={INFRA_META[t].label}>
            <InfraIcon type={t} size={18} color={sel.has(t) ? '#3ee6ff' : '#b9c4d0'} />
            {INFRA_META[t].plural}
          </button>
        ))}
      </div>
      <div class="infra-hint">
        {sel.size ? (
          <button class="link-btn" onClick={() => (infraTypes.value = new Set())}>Show all types</button>
        ) : (
          <span>All types shown. Pick one or more to filter.</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- freight tab

const SEGMENTS: Segment[] = ['dry', 'tanker', 'gas'];

/** Vessel class chips grouped by segment; multi-select drives the lanes and routes layers. */
function VesselFilter() {
  const sel = vesselClasses.value;
  const list = vesselClassList.value;
  return (
    <Section
      title="Vessel class"
      aside={
        sel.size > 0 ? (
          <button class="link-btn" onClick={() => (vesselClasses.value = new Set())}>
            Clear
          </button>
        ) : null
      }
    >
      {SEGMENTS.map((seg) => {
        const items = list.filter((v) => v.segment === seg);
        if (!items.length) return null;
        return (
          <div class="vc-group" key={seg}>
            <div class="vc-label">{SEGMENT_LABEL[seg]}</div>
            <div class="chips">
              {items.map((v) => (
                <button
                  class="chip"
                  aria-pressed={sel.has(v.id)}
                  style={{ '--chip-color': SEGMENT_COLOR[seg] }}
                  onClick={() => toggleInSet(vesselClasses, v.id)}
                >
                  {v.name}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </Section>
  );
}

/** Baltic benchmarks (by segment) and other heavy-traffic routes; discontinued ones last. */
function RouteList() {
  const [routes, setRoutes] = useState<Route[]>([]);
  useEffect(() => {
    loadRoutes().then(setRoutes).catch(() => undefined);
  }, []);
  const vc = vesselClasses.value;
  const sel = selection.value;
  const selId = sel?.kind === 'route' ? sel.id : null;
  void vesselClassList.value; // segmentOf() depends on the class list

  const visible = routes
    .filter((r) => vesselMatches(r.vclass, vc))
    .sort((a, b) => Number(!!a.discontinued) - Number(!!b.discontinued)); // stable: discontinued last
  const selSeg = selId ? segmentOf(routes.find((r) => r.id === selId)?.vclass ?? '') : null;

  const row = (r: Route) => (
    <button
      class={`list-btn route-row ${r.discontinued ? 'is-off' : ''}`}
      key={r.id}
      aria-pressed={selId === r.id}
      onClick={() => select({ kind: 'route', id: r.id })}
    >
      {r.benchmark ? (
        <span class="code">{r.id}</span>
      ) : (
        <span class="dot" style={{ color: SEGMENT_COLOR[segmentOf(r.vclass)], width: '6px', height: '6px' }} />
      )}
      <span class="route-name">
        {r.name}
        {r.discontinued && <small> (discontinued)</small>}
      </span>
      <span class="meta">{vesselName(r.vclass)}</span>
    </button>
  );

  const others = visible.filter((r) => !r.benchmark);
  return (
    <Section title="Baltic benchmarks">
      {SEGMENTS.map((seg) => {
        const items = visible.filter((r) => r.benchmark && segmentOf(r.vclass) === seg);
        if (!items.length) return null;
        return (
          <details class="route-group" key={seg} open={vc.size > 0 || seg === 'dry' || seg === selSeg}>
            <summary>
              <span class="dot" style={{ color: SEGMENT_COLOR[seg], width: '6px', height: '6px' }} />
              {SEGMENT_LABEL[seg]}
              <span class="meta">{items.length}</span>
            </summary>
            {items.map(row)}
          </details>
        );
      })}
      {others.length > 0 && (
        <>
          <h4 class="route-sub">Other heavy-traffic routes</h4>
          <details class="route-group" open={vc.size > 0 || selSeg != null && others.some((r) => r.id === selId)}>
            <summary>
              {others.length} routes<span class="meta">non-benchmark</span>
            </summary>
            {others.map(row)}
          </details>
        </>
      )}
      {!visible.length && <p class="muted" style={{ fontSize: '12px' }}>No routes for the selected vessel classes.</p>}
    </Section>
  );
}
