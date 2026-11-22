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
import { detailOpen, writeHash, family, commodity, metric, year, selection, historyOpen, priceDrawer } from './lib/store';

export function App() {
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
    <div class={`app ${detailOpen.value ? 'detail-open' : ''}${historyOpen.value ? ' tl-open' : ''}`}>
      <MapView />
      <TopBar />
      <SidePanel />
      <DetailPanel />
      <Legend />
      <PriceDrawer />
      <Timeline />
      <Tooltip />
    </div>
  );
}
