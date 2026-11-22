import { useEffect } from 'preact/hooks';
import { effect } from '@preact/signals';
import { MapView } from './components/MapView';
import { TopBar } from './components/TopBar';
import { SidePanel } from './components/SidePanel';
import { DetailPanel } from './components/DetailPanel';
import { Tooltip } from './components/Tooltip';
import { Legend } from './components/Legend';
import { PriceDrawer } from './components/PriceDrawer';
import { Timeline } from './components/Timeline';
import * as prices from './lib/prices';
import { detailOpen, writeHash, family, commodity, metric, year, selection, select, historyOpen, priceDrawer, panelCollapsed } from './lib/store';

/** Remembers which control opened a panel so Escape can hand focus back to it. */
function useFocusReturn() {
  useEffect(() => {
    const openers = new Map<string, HTMLElement>();
    const grab = (key: string) => {
      const el = document.activeElement as HTMLElement | null;
      // a click on a button focuses it in all current browsers; the map canvas is not a useful return target
      if (el && el !== document.body && !el.closest('.map-root')) openers.set(key, el);
    };
    let sel = selection.value !== null;
    let pd = priceDrawer.value !== null;
    let tl = historyOpen.value;
    const stop = effect(() => {
      const s = selection.value !== null;
      const p = priceDrawer.value !== null;
      const t = historyOpen.value;
      if (s && !sel) grab('detail');
      if (p && !pd) grab('prices');
      if (t && !tl) grab('history');
      sel = s;
      pd = p;
      tl = t;
    });
    (window as any).__focusOpeners = openers;
    return stop;
  }, []);
}

function restoreFocus(key: string) {
  const el = ((window as any).__focusOpeners as Map<string, HTMLElement> | undefined)?.get(key);
  if (el && el.isConnected) requestAnimationFrame(() => el.focus());
}

/** Escape closes the topmost layer: popover/menu, price drawer, detail panel, history timeline. */
function useEscape() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      // 1. an open popover / menu
      const pop = document.querySelector<HTMLElement>('[aria-haspopup][aria-expanded="true"]');
      if (pop) {
        pop.click();
        pop.focus();
        e.preventDefault();
        return;
      }
      // 2. price drawer
      if (priceDrawer.value) {
        const close = (prices as { closePrices?: () => void }).closePrices;
        if (close) close();
        else priceDrawer.value = null;
        restoreFocus('prices');
        e.preventDefault();
        return;
      }
      // 3. detail selection
      if (selection.value) {
        select(null);
        restoreFocus('detail');
        e.preventDefault();
        return;
      }
      // 4. history timeline
      if (historyOpen.value) {
        historyOpen.value = false;
        restoreFocus('history');
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}

export function App() {
  useFocusReturn();
  useEscape();
  useEffect(
    () =>
      effect(() => {
        // touch the signals that make up the shareable view, then mirror them in the URL hash
        void [family.value, commodity.value, metric.value, year.value, selection.value];
        writeHash();
      }),
    [],
  );
  // the price drawer and the timeline share the bottom edge: opening one closes the other
  useEffect(
    () =>
      effect(() => {
        if (priceDrawer.value) historyOpen.value = false;
      }),
    [],
  );
  useEffect(
    () =>
      effect(() => {
        if (historyOpen.value) priceDrawer.value = null;
      }),
    [],
  );
  return (
    <div class={`app ${detailOpen.value ? 'detail-open' : ''}${historyOpen.value ? ' tl-open' : ''}${priceDrawer.value ? ' pd-open' : ''}${panelCollapsed.value ? ' panel-hidden' : ''}`}>
      <a
        class="skip-link"
        href="#controls"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById('controls')?.focus();
        }}
      >
        Skip to controls
      </a>
      {/* DOM (= tab) order: top bar, side panel, detail panel, drawers, then the map with its zoom controls */}
      <TopBar />
      <SidePanel />
      <DetailPanel />
      <PriceDrawer />
      <Timeline />
      <MapView />
      <Legend />
      <Tooltip />
    </div>
  );
}
