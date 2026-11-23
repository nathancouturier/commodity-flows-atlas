/**
 * Right detail panel. Routes the current selection to the matching view.
 * Views are lazy so their code only loads when first opened.
 */
import { lazy, Suspense } from 'preact/compat';
import { useEffect, useRef, useState } from 'preact/hooks';
import '../styles/views.css';
import { selection, select, type SheetSnap } from '../lib/store';
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
  // a page whose only content is its "not in the catalogue" message: the id of a mistyped link is not a name
  // (a country of the atlas without a profile also has a lone placeholder, under its own name)
  const sel = selection.peek();
  if (sel && !(sel.kind === 'country' && !unknownKind(sel)) && panel.querySelector('.panel-scroll > .placeholder:only-child')) {
    return `Unknown ${sel.kind === 'infra' ? 'asset' : sel.kind === 'vessel' ? 'vessel class' : sel.kind}`;
  }
  const title = panel.querySelector('.detail-title')?.textContent?.trim() ?? '';
  if (!title || /^(Loading)?…$/.test(title)) return null;
  // a lane's heading is its two countries: its kicker says which commodity
  const kicker = selection.peek()?.kind === 'lane' ? panel.querySelector('.detail-kicker')?.textContent?.trim() : '';
  return kicker && kicker !== 'Seaborne lane' ? `${kicker}: ${title}` : title;
}

const SNAPS: SheetSnap[] = ['peek', 'half', 'full'];

// A page opened from the keyboard (Enter or Space on a marker, a button or a row) takes the focus to its heading, so
// that the next Tab reads the page; a click leaves the focus where it is. Enter or Space within the last 1.5 s is what
// tells the two apart, since a selection can come from anywhere (Back, a pasted link, the timeline).
let lastActivation = -Infinity;
addEventListener(
  'keydown',
  (e) => {
    if (e.key === 'Enter' || e.key === ' ') lastActivation = performance.now();
  },
  true,
);

/** Grab handle of the detail sheet (tablet / phone, hidden by CSS elsewhere): same gestures as the controls sheet. */
function DetailHandle({ snap, setSnap }: { snap: SheetSnap; setSnap: (s: SheetSnap) => void }) {
  const start = useRef<number | null>(null);
  const step = (dir: 1 | -1) => setSnap(SNAPS[Math.max(0, Math.min(SNAPS.length - 1, SNAPS.indexOf(snap) + dir))]);
  const cycle = () => setSnap(SNAPS[(SNAPS.indexOf(snap) + 1) % SNAPS.length]);
  return (
    <div class="sheet-head detail-sheet-head">
      <button
        class="sheet-handle"
        aria-label={`Resize details, now ${snap === 'peek' ? 'minimised' : snap === 'half' ? 'half height' : 'full height'}`}
        onPointerDown={(e) => {
          start.current = e.clientY;
          (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
        }}
        onPointerUp={(e) => {
          const dy = start.current == null ? 0 : e.clientY - start.current;
          start.current = null;
          if (Math.abs(dy) > 24) step(dy < 0 ? 1 : -1);
          else cycle();
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowUp') step(1);
          else if (e.key === 'ArrowDown') step(-1);
        }}
        onClick={(e) => e.detail === 0 && cycle()}
      >
        <span class="sheet-grip" aria-hidden="true" />
      </button>
    </div>
  );
}

export function DetailPanel() {
  const s = selection.value;
  const ref = useRef<HTMLElement>(null);
  // bottom sheet height (tablet / phone): every new page opens at half height
  const [snap, setSnap] = useState<SheetSnap>('half');
  const selKey = s ? `${s.kind}:${s.id}` : '';
  useEffect(() => setSnap('half'), [selKey]);
  // the heading of a page opened from the keyboard, once the view has written it
  const focusHeading = useRef(false);
  useEffect(() => {
    // the previous / next event buttons of the timeline keep the focus: they are stepping through pages
    const stepping = !!document.activeElement?.closest('.tl-step');
    focusHeading.current = !!selKey && !stepping && performance.now() - lastActivation < 1500;
  }, [selKey]);
  // the views load their own data and write their own heading: follow it as it appears
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      detailTitle.value = readTitle(el);
      const h = focusHeading.current && el.querySelector<HTMLElement>('.detail-title');
      if (h && detailTitle.value) {
        focusHeading.current = false;
        h.tabIndex = -1;
        h.focus({ preventScroll: true });
      }
    };
    const mo = new MutationObserver(read);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    read();
    return () => mo.disconnect();
  }, []);
  const unknown = s ? unknownKind(s) : null;
  return (
    <aside ref={ref} class={`detail-panel glass snap-${snap} ${s ? 'open' : ''}`} data-snap={snap} aria-label="Details" aria-hidden={!s}>
      {s && (
        <>
          <DetailHandle snap={snap} setSnap={setSnap} />
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
