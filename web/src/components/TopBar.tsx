import { family, select, commodity, layers, type FamilyFilter } from '../lib/store';
import { FAMILY_COLOR } from '../lib/format';
import { BrandMark } from './ui';

const TABS: { id: FamilyFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'freight', label: 'Freight' },
  { id: 'energy', label: 'Energy' },
  { id: 'metals', label: 'Metals' },
  { id: 'softs', label: 'Softs' },
];

export function TopBar() {
  return (
    <header class="topbar">
      <a class="brand glass" href="./" aria-label="Commodity Flows Atlas home" style={{ textDecoration: 'none', color: 'inherit' }}>
        <BrandMark />
        <span class="brand-name">
          Commodity Flows Atlas
          <small>Raw materials · trade · freight</small>
        </span>
      </a>
      <nav class="family-tabs glass" aria-label="Commodity family">
        {TABS.map((t) => (
          <button
            class="family-tab"
            aria-pressed={family.value === t.id}
            onClick={() => {
              // the Freight tab brings routes and chokepoints in; other tabs return to flows only
              const toFreight = t.id === 'freight';
              if (toFreight !== (family.value === 'freight')) {
                layers.value = { ...layers.value, routes: toFreight, chokepoints: toFreight };
              }
              family.value = t.id;
              commodity.value = null;
              select(null);
            }}
          >
            {t.id !== 'all' && <span class="dot" style={{ color: FAMILY_COLOR[t.id] }} />}
            {t.label}
          </button>
        ))}
      </nav>
      <div class="spacer" />
    </header>
  );
}
