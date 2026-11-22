import { BrandMark } from './ui';
import { priceDrawer, historyOpen } from '../lib/store';
import { togglePrices, toggleHistory } from '../lib/prices';
import { openAbout } from './AboutHost';

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
        <button class="tool-btn" aria-haspopup="dialog" aria-label="About" title="About, sources and data freshness" onClick={(e) => openAbout('about', e.currentTarget)}>
          <svg viewBox="0 0 14 14" aria-hidden="true">
            <circle cx="7" cy="7" r="5.2" fill="none" stroke="currentColor" stroke-width="1.5" />
            <path d="M7 6.4v3.4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            <circle cx="7" cy="4.2" r="0.9" fill="currentColor" />
          </svg>
          <span>About</span>
        </button>
      </div>
    </header>
  );
}
