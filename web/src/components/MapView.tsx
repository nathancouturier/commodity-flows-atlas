import { useEffect, useRef } from 'preact/hooks';
import 'maplibre-gl/dist/maplibre-gl.css';
import { initMap } from '../map/controller';
import { installLayers } from '../map/layers';
import { layers, mapNotice } from '../lib/store';

/** The map is the page's <main> landmark; it comes last in the DOM so the controls are reached first by keyboard. */
export function MapView() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const m = initMap(ref.current);
    installLayers(m);
  }, []);
  const notice = layers.value.flows ? mapNotice.value : null;
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
