/**
 * Map layer switches. On desktop they sit in the map legend (bottom); on phones and tablets,
 * where the legend is hidden, the side panel shows them instead (see .layers-in-panel / .legend-layers).
 */
import { commodities } from '../lib/data';
import { commodity, family, infraAvailable, infraTypes, layers, toggleInSet, toggleLayer } from '../lib/store';
import { FAMILY_LABEL } from '../lib/format';
import { InfraIcon, INFRA_META, INFRA_ORDER, Switch } from './ui';
import type { Family } from '../types';

const LAYERS = [
  { id: 'flows', label: 'Physical flows', desc: 'What is traded: country-to-country volumes (customs data); width = tonnage' },
  { id: 'routes', label: 'Freight routes', desc: 'How it ships: Baltic benchmark and main routes, by vessel class' },
  { id: 'chokepoints', label: 'Chokepoints', desc: 'Straits and canals, with current traffic' },
  { id: 'infrastructure', label: 'Infrastructure', desc: 'Mines, fields, refineries, LNG terminals, pipelines, ports' },
] as const;

/** Full switches with explanations (side panel on small screens). */
export function LayerSwitches() {
  return (
    <>
      {LAYERS.map((l) => (
        <Switch key={l.id} label={l.label} hint={l.desc} checked={layers.value[l.id]} onChange={(v) => toggleLayer(l.id, v)} />
      ))}
      {layers.value.infrastructure && <InfraTypeChips />}
    </>
  );
}

/** Compact toggles for the legend (desktop); the explanation is in the tooltip. */
export function LayerToggles() {
  return (
    <div class="legend-layers" role="group" aria-label="Map layers">
      {LAYERS.map((l) => (
        <button
          key={l.id}
          class="layer-toggle"
          role="switch"
          aria-checked={layers.value[l.id]}
          title={l.desc}
          onClick={() => toggleLayer(l.id, !layers.value[l.id])}
        >
          <span class="switch" aria-hidden="true" />
          {l.label}
        </button>
      ))}
    </div>
  );
}

export function InfraTypeChips() {
  const sel = infraTypes.value;
  const avail = infraAvailable.value;
  const shown = INFRA_ORDER.filter((t) => !avail || avail.has(t));
  const cur = commodities.value.find((c) => c.id === commodity.value);
  const scope = cur ? cur.name : family.value !== 'all' ? (family.value === 'freight' ? 'Freight' : FAMILY_LABEL[family.value as Family]) : null;
  return (
    <div class="infra-filter">
      {scope && <div class="infra-scope">Showing assets for {scope}</div>}
      <div class="chips">
        {shown.map((t) => (
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

