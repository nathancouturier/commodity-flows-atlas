/**
 * What the open view is called (the tab title follows it) and whether the ids a link carries exist.
 */
import { effect, signal } from '@preact/signals';
import { commodities, commodityMeta, countries } from './data';
import { FAMILY_LABEL } from './format';
import { openVesselClass } from './freight';
import { commodity, family, linkApplied, metric, selection, vesselClasses, type Selection } from './store';

/** Title of the open page as its view shows it; null while no page is open or it is still loading. */
export const detailTitle = signal<string | null>(null);

// the site name as index.html gives it
const SITE = document.title;

// "Copper · Commodity Flows Atlas": tabs, bookmarks and the history list tell the views apart
effect(() => {
  const k = commodity.value;
  const f = family.value;
  let name: string | null | undefined;
  if (selection.value) name = detailTitle.value;
  else if (k) name = commodityMeta(k)?.name;
  else if (f === 'freight') name = 'Freight';
  else if (f !== 'all') name = FAMILY_LABEL[f];
  document.title = name ? `${name} · ${SITE}` : SITE;
});

/**
 * "commodity" or "country" when the selection names one the catalogue does not have (a mistyped or outdated
 * link), null otherwise. The other kinds are checked by their own views, which load their own files.
 */
export function unknownKind(s: Selection): string | null {
  if (s.kind === 'commodity' && commodities.value.length && !commodityMeta(s.id)) return 'commodity';
  if (s.kind === 'country' && Object.keys(countries.value).length && !countries.value[s.id]) return 'country';
  return null;
}

// an unknown commodity id in a pasted link (#c=nope) falls back to the overview, as it does on a fresh load
effect(() => {
  const k = commodity.value;
  if (k && commodities.value.length && !commodityMeta(k)) commodity.value = null;
});

// A link applied to the open atlas gets what a fresh load of it gets:
linkApplied.subscribe((link) => {
  if (!link) return; // the load itself is handled where the catalogues arrive (lib/freight.ts, map/modules/choropleth.ts)
  // a vessel class without its filter (#sel=vessel:vlcc) opens on the Freight view
  const s = selection.peek();
  if (s?.kind === 'vessel' && !vesselClasses.peek().size) openVesselClass(s.id, false);
  // a commodity without a colouring (#c=copper) is coloured by its first country table (same rule as
  // map/modules/choropleth.ts); Back to a view the atlas wrote keeps a colouring the user switched off
  const k = commodity.peek();
  const meta = k ? commodityMeta(k) : undefined;
  if (!link.own && meta && metric.peek() === 'none') metric.value = (['production', 'exports', 'imports'] as const).find((x) => meta.has.includes(x)) ?? 'none';
});
