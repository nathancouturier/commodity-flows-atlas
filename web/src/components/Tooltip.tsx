import { hovered } from '../lib/store';

/** Floating hover card. Content is pre-escaped HTML produced by map layer modules. */
export function Tooltip() {
  const h = hovered.value;
  if (!h || !h.html) return null;
  const flip = h.x > window.innerWidth - 300;
  return (
    <div
      class="tooltip"
      role="status"
      style={{ left: `${h.x}px`, top: `${h.y}px`, transform: flip ? 'translate(calc(-100% - 14px), 14px)' : undefined }}
      dangerouslySetInnerHTML={{ __html: h.html }}
    />
  );
}
