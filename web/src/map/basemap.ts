/**
 * Base map style. No third-party tiles: land and borders come from our own
 * Natural Earth topology (data/geo/countries.topo.json), so the map always
 * renders and the look is fully controlled.
 */
import type { StyleSpecification } from 'maplibre-gl';
import type { FeatureCollection, LineString } from 'geojson';
import { SHARE_STOPS } from '../lib/format';

export const C = {
  ocean: '#05090f',
  land: '#111821',
  landHover: '#1b2734',
  landSelected: '#233a52',
  border: '#24313f',
  coast: '#2d3e53',
  graticule: 'rgba(120, 150, 190, 0.07)',
};

function graticule(step = 30): FeatureCollection<LineString> {
  const features: FeatureCollection<LineString>['features'] = [];
  for (let lon = -180; lon <= 180; lon += step) {
    const coords: [number, number][] = [];
    for (let lat = -80; lat <= 80; lat += 2) coords.push([lon, lat]);
    features.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } });
  }
  for (let lat = -60; lat <= 60; lat += step) {
    const coords: [number, number][] = [];
    for (let lon = -180; lon <= 180; lon += 2) coords.push([lon, lat]);
    features.push({ type: 'Feature', properties: { eq: lat === 0 }, geometry: { type: 'LineString', coordinates: coords } });
  }
  return { type: 'FeatureCollection', features };
}

export function baseStyle(): StyleSpecification {
  return {
    version: 8,
    name: 'Abyssal',
    sources: {
      graticule: { type: 'geojson', data: graticule() },
      countries: { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, promoteId: 'c' },
    },
    layers: [
      { id: 'ocean', type: 'background', paint: { 'background-color': C.ocean } },
      {
        id: 'graticule',
        type: 'line',
        source: 'graticule',
        paint: { 'line-color': C.graticule, 'line-width': 0.6 },
      },
      {
        id: 'land',
        type: 'fill',
        source: 'countries',
        paint: {
          'fill-color': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            C.landSelected,
            ['boolean', ['feature-state', 'hover'], false],
            C.landHover,
            C.land,
          ],
        },
      },
      {
        // choropleth overlay, driven by feature-state "v" (0..1 share) and "col"
        id: 'choropleth',
        type: 'fill',
        source: 'countries',
        layout: { visibility: 'none' },
        paint: {
          'fill-color': ['coalesce', ['feature-state', 'col'], 'rgba(0,0,0,0)'],
          'fill-opacity': ['interpolate', ['linear'], ['coalesce', ['feature-state', 'v'], 0], ...SHARE_STOPS.flat()],
        },
      },
      {
        id: 'borders',
        type: 'line',
        source: 'countries',
        paint: {
          'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#5d86b3', C.border],
          'line-width': ['interpolate', ['linear'], ['zoom'], 1, 0.4, 5, 1.1],
        },
      },
    ],
  };
}
