import { panelCollapsed } from '../lib/store';
import { BrandMark } from './ui';
import { priceDrawer, historyOpen } from '../lib/store';
import { togglePrices, toggleHistory } from '../lib/prices';

export function TopBar() {
  return (
    <header class="topbar">
      <div class="brand glass">
        <h1 class="brand-h1">
          <a class="brand-link" href="./">
            <BrandMark />
            <span class="brand-name">
              Commodity Flows Atlas
              <small aria-hidden="true">Raw materials · trade · freight</small>
            </span>
          </a>
        </h1>
        <button
          class="panel-toggle"
          aria-controls="controls"
          aria-expanded={!panelCollapsed.value}
          title={panelCollapsed.value ? 'Show the side panel' : 'Hide the side panel'}
          aria-label={panelCollapsed.value ? 'Show the side panel' : 'Hide the side panel'}
          onClick={() => (panelCollapsed.value = !panelCollapsed.value)}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <rect x="1.75" y="2.75" width="12.5" height="10.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.4" />
            <path d="M6 3v10" stroke="currentColor" stroke-width="1.4" />
            {panelCollapsed.value ? (
              <path d="M9 6.2 10.8 8 9 9.8" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
            ) : (
              <path d="M10.8 6.2 9 8l1.8 1.8" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
            )}
          </svg>
        </button>
      </div>
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
