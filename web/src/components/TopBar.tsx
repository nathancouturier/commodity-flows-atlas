import { family, select, commodity, layers, type FamilyFilter } from '../lib/store';
import { FAMILY_COLOR } from '../lib/format';
import { BrandMark } from './ui';
import { priceDrawer, historyOpen } from '../lib/store';
import { togglePrices, toggleHistory } from '../lib/prices';

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
      <div class="tool-btns glass" role="group" aria-label="Tools">
        <button class="tool-btn" aria-pressed={priceDrawer.value !== null} aria-label="Prices" title="Price explorer" onClick={togglePrices}>
          <svg viewBox="0 0 14 14" aria-hidden="true">
            <path d="M1.5 11.5l3.2-4.2 2.6 2.2 5.2-6.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span>Prices</span>
        </button>
        <button class="tool-btn" aria-pressed={historyOpen.value} aria-label="History" title="History timeline" onClick={toggleHistory}>
          <svg viewBox="0 0 14 14" aria-hidden="true">
            <circle cx="7" cy="7" r="5.2" fill="none" stroke="currentColor" stroke-width="1.5" />
            <path d="M7 4v3.2l2.2 1.3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
          <span>History</span>
        </button>
      </div>
    </header>
  );
}
