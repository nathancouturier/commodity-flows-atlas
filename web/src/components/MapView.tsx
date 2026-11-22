import { useEffect, useRef } from 'preact/hooks';
import 'maplibre-gl/dist/maplibre-gl.css';
import { initMap } from '../map/controller';
import { installLayers } from '../map/layers';

export function MapView() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const m = initMap(ref.current);
    installLayers(m);
  }, []);
  return <div ref={ref} class="map-root" role="application" aria-label="World map of commodity flows" />;
}
