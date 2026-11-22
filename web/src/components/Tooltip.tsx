import { useLayoutEffect, useRef } from 'preact/hooks';
import { hovered } from '../lib/store';
import { isSheetLayout } from '../map/controller';

const PAD = 8;
const OFFSET = 14;

/** Free map area: not under the side panel, the detail panel or the bottom sheet. */
function freeArea() {
  let left = 0;
  let right = window.innerWidth;
  let top = 0;
  let bottom = window.innerHeight;
  const side = document.querySelector('.side-panel')?.getBoundingClientRect();
  const detail = document.querySelector('.detail-panel.open')?.getBoundingClientRect();
  if (isSheetLayout()) {
    // panels are bottom sheets: the free area ends where the highest one starts
    for (const r of [side, detail]) if (r && r.height > 0) bottom = Math.min(bottom, r.top);
    top = 56;
  } else {
    if (side) left = Math.max(left, side.right);
    if (detail && detail.left < right) right = detail.left;
  }
  return { left, right, top, bottom };
}

/** Floating hover card. Content is pre-escaped HTML produced by map layer modules. */
export function Tooltip() {
  const h = hovered.value;
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !h) return;
    const { width: w, height: ht } = el.getBoundingClientRect();
    const a = freeArea();
    let x = h.x + OFFSET;
    let y = h.y + OFFSET;
    // flip to the other side of the pointer when it would run into a panel or the screen edge
    if (x + w > a.right - PAD) x = h.x - OFFSET - w;
    if (y + ht > a.bottom - PAD) y = h.y - OFFSET - ht;
    x = Math.max(a.left + PAD, Math.min(x, a.right - PAD - w));
    y = Math.max(a.top + PAD, Math.min(y, a.bottom - PAD - ht));
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.style.visibility = 'visible';
  });
  if (!h || !h.html) return null;
  return (
    <div
      ref={ref}
      class="tooltip"
      role="status"
      style={{ left: `${h.x}px`, top: `${h.y}px`, visibility: 'hidden' }}
      dangerouslySetInnerHTML={{ __html: h.html }}
    />
  );
}
