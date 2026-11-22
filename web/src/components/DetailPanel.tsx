/**
 * Right detail panel. Routes the current selection to the matching view.
 * Views are lazy so their code only loads when first opened.
 */
import { lazy, Suspense } from 'preact/compat';
import { useEffect, useRef } from 'preact/hooks';
import '../styles/views.css';
import { selection, select } from '../lib/store';
import { detailTitle, unknownKind } from '../lib/view';
import { CloseIcon, Placeholder, Skeleton } from './ui';

const CountryView = lazy(() => import('./views/CountryView'));
const CommodityView = lazy(() => import('./views/CommodityView'));
const RouteView = lazy(() => import('./views/RouteView'));
const LaneView = lazy(() => import('./views/LaneView'));
const ChokepointView = lazy(() => import('./views/ChokepointView'));
const VesselView = lazy(() => import('./views/VesselView'));
const InfraView = lazy(() => import('./views/InfraView'));
const EventView = lazy(() => import('./views/EventView'));
const GenericView = lazy(() => import('./views/GenericView'));

/** A link to a commodity or a country the atlas does not have: say so, instead of an empty page. */
function UnknownView({ kind, id }: { kind: string; id: string }) {
  return (
    <>
      <div class="detail-head">
        <div class="detail-kicker">{kind}</div>
        <h2 class="detail-title">{id}</h2>
      </div>
      <div class="panel-scroll">
        <Placeholder>
          Unknown {kind}: {id}. It is not in the atlas catalogue.
        </Placeholder>
      </div>
    </>
  );
}

/** The page's own heading, for the tab title ("Seaborne lane" and loading marks are not names). */
function readTitle(panel: HTMLElement): string | null {
  const title = panel.querySelector('.detail-title')?.textContent?.trim() ?? '';
  if (!title || /^(Loading)?…$/.test(title)) return null;
  // a lane's heading is its two countries: its kicker says which commodity
  const kicker = selection.peek()?.kind === 'lane' ? panel.querySelector('.detail-kicker')?.textContent?.trim() : '';
  return kicker && kicker !== 'Seaborne lane' ? `${kicker}: ${title}` : title;
}

export function DetailPanel() {
  const s = selection.value;
  const ref = useRef<HTMLElement>(null);
  // the views load their own data and write their own heading: follow it as it appears
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => (detailTitle.value = readTitle(el));
    const mo = new MutationObserver(read);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    read();
    return () => mo.disconnect();
  }, []);
  const unknown = s ? unknownKind(s) : null;
  return (
    <aside ref={ref} class={`detail-panel glass ${s ? 'open' : ''}`} aria-label="Details" aria-hidden={!s}>
      {s && (
        <>
          <button class="close-btn" onClick={() => select(null)} aria-label="Close details">
            <CloseIcon />
          </button>
          <Suspense fallback={<div style={{ padding: '18px' }}><Skeleton lines={6} /></div>}>
            {unknown ? (
              <UnknownView kind={unknown} id={s.id} />
            ) : s.kind === 'country' ? (
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
