import { useEffect, useRef } from 'preact/hooks';
import 'maplibre-gl/dist/maplibre-gl.css';
import { initMap } from '../map/controller';
import { installLayers } from '../map/layers';
import { layers, mapFailed, mapNotice } from '../lib/store';

/** The map is the page's <main> landmark; it comes last in the DOM so the controls are reached first by keyboard. */
export function MapView() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const m = initMap(ref.current);
    if (m) installLayers(m);
  }, []);
  const notice = mapFailed.value
    ? 'The map needs WebGL, which this browser has switched off or does not support. The panels, the Route finder and the prices work without it.'
    : layers.value.flows
      ? mapNotice.value
      : null;
  return (
    <main id="map" class="map-main" aria-label="Map">
      <div ref={ref} class="map-root" role="application" aria-label="World map of commodity flows" />
      {notice && (
        <div class="map-notice glass" role="status">
          {notice}
        </div>
      )}
    </main>
  );
}
