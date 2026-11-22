/**
 * Right detail panel. Routes the current selection to the matching view.
 * Views are lazy so their code only loads when first opened.
 */
import { lazy, Suspense } from 'preact/compat';
import '../styles/views.css';
import { selection, select } from '../lib/store';
import { CloseIcon, Skeleton } from './ui';

const CountryView = lazy(() => import('./views/CountryView'));
const CommodityView = lazy(() => import('./views/CommodityView'));
const RouteView = lazy(() => import('./views/RouteView'));
const LaneView = lazy(() => import('./views/LaneView'));
const ChokepointView = lazy(() => import('./views/ChokepointView'));
const VesselView = lazy(() => import('./views/VesselView'));
const InfraView = lazy(() => import('./views/InfraView'));
const EventView = lazy(() => import('./views/EventView'));
const GenericView = lazy(() => import('./views/GenericView'));

export function DetailPanel() {
  const s = selection.value;
  return (
    <aside class={`detail-panel glass ${s ? 'open' : ''}`} aria-label="Details" aria-hidden={!s}>
      {s && (
        <>
          <button class="close-btn" onClick={() => select(null)} aria-label="Close details">
            <CloseIcon />
          </button>
          <Suspense fallback={<div style={{ padding: '18px' }}><Skeleton lines={6} /></div>}>
            {s.kind === 'country' ? (
              <CountryView id={s.id} />
            ) : s.kind === 'commodity' ? (
              <CommodityView id={s.id} />
            ) : s.kind === 'route' ? (
              <RouteView id={s.id} />
            ) : s.kind === 'lane' ? (
              <LaneView id={s.id} />
            ) : s.kind === 'chokepoint' ? (
              <ChokepointView id={s.id} />
            ) : s.kind === 'infra' ? (
              <InfraView id={s.id} layer={s.layer} />
            ) : s.kind === 'vessel' ? (
              <VesselView id={s.id} />
            ) : s.kind === 'event' ? (
              <EventView id={s.id} />
            ) : (
              <GenericView sel={s} />
            )}
          </Suspense>
        </>
      )}
    </aside>
  );
}
