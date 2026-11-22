/**
 * Map layer switches (side panel "Map layers" dropdown; explanations as hover tooltips) and the
 * infrastructure type chips (side panel "Infrastructure types" dropdown).
 */
import { commodities } from '../lib/data';
import { commodity, family, infraAvailable, infraHidden, layers, toggleInSet, toggleLayer } from '../lib/store';
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
    </>
  );
}

export function InfraTypeChips() {
  const hidden = infraHidden.value;
  const avail = infraAvailable.value;
  const shown = INFRA_ORDER.filter((t) => !avail || avail.has(t));
  const nHidden = shown.filter((t) => hidden.has(t)).length;
  const cur = commodities.value.find((c) => c.id === commodity.value);
  const scope = cur ? cur.name : family.value !== 'all' ? (family.value === 'freight' ? 'Freight' : FAMILY_LABEL[family.value as Family]) : null;
  return (
    <div class="infra-filter">
      {scope && <div class="infra-scope">Showing assets for {scope}</div>}
      <div class="chips">
        {/* every type is on by default; a click hides or shows that type */}
        {shown.map((t) => {
          const on = !hidden.has(t);
          return (
            <button
              class="chip chip-infra"
              key={t}
              aria-pressed={on}
              onClick={() => toggleInSet(infraHidden, t)}
              title={`${on ? 'Hide' : 'Show'} ${INFRA_META[t].plural.toLowerCase()}`}
            >
              <InfraIcon type={t} size={18} color={on ? '#3ee6ff' : '#7d8896'} />
              {INFRA_META[t].plural}
            </button>
          );
        })}
      </div>
      <div class="infra-hint">
        {nHidden ? (
          <button class="link-btn" onClick={() => (infraHidden.value = new Set())}>Show all types</button>
        ) : (
          <span>All types shown. Click a type to hide it.</span>
        )}
      </div>
    </div>
  );
}

