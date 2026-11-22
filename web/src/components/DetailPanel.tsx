/**
 * Right detail panel. Routes the current selection to the matching view.
 * Views are lazy so their code only loads when first opened.
 */
import { lazy, Suspense } from 'preact/compat';
import { selection, select } from '../lib/store';
import { CloseIcon, Skeleton } from './ui';

const CountryView = lazy(() => import('./views/CountryView'));
const CommodityView = lazy(() => import('./views/CommodityView'));
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
            ) : (
              <GenericView sel={s} />
            )}
          </Suspense>
        </>
      )}
    </aside>
  );
}
