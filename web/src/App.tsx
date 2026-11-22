import { useEffect } from 'preact/hooks';
import { effect } from '@preact/signals';
import { MapView } from './components/MapView';
import { TopBar } from './components/TopBar';
import { SidePanel } from './components/SidePanel';
import { DetailPanel } from './components/DetailPanel';
import { Tooltip } from './components/Tooltip';
import { detailOpen, writeHash, family, commodity, metric, year, selection } from './lib/store';

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
  return (
    <div class={`app ${detailOpen.value ? 'detail-open' : ''}`}>
      <MapView />
      <TopBar />
      <SidePanel />
      <DetailPanel />
      <Tooltip />
    </div>
  );
}
