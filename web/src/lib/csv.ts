/**
 * CSV downloads, built in the browser. One convention for every file of the site: one row per value, a header row,
 * CRLF line ends, a byte-order mark so that spreadsheet programs read accents as UTF-8, and the source and its
 * licence in the columns of each row (the registry data/sources.json gives both).
 */
import { sourceLabel, sources } from './data';
import { licenceAllows, licenceShort } from './licence';
import { LONG_LICENCE, LONG_SOURCE, csvCell, numberText, onceColumn, toCsv } from './csvCore';

/** The Atlas's own figures are published under this licence (the registry's `atlas` entry says the same). */
export const ATLAS_LICENCE = 'CC BY 4.0 (attribution: Commodity Flows Atlas)';

export { csvCell, numberText, toCsv };

/** Name of the source, as the page prints it. `extra` is appended after a semicolon (what the Atlas did to the figure). */
export function sourceName(id: string, extra?: string): string {
  return [sourceLabel(id), extra].filter(Boolean).join('; ');
}

/** The licence of a source, as data/sources.json states it ("" for a source the registry lacks). */
export function licenceOf(id: string): string {
  return id === 'atlas' ? ATLAS_LICENCE : (sources.value[id]?.licence ?? '');
}

/** The `licence` cell: called with `licenceTexts(ids, suffix)`, the full text and the short one of the sources a row rests on. */
export const licenceColumn = () => onceColumn(LONG_LICENCE, 'full text');
/** The `source` cell: the source's name as the page prints it, and a short form (its publisher) for the rows after the first. */
export const sourceColumn = () => onceColumn(LONG_SOURCE, 'full name');
/** The registry's licence texts of sources, joined, and their short names, joined: the two arguments of `licenceColumn()`'s function. */
export const licenceTexts = (ids: string[], suffix = ''): [string, string] => [
  ids.map(licenceOf).join('; ') + suffix,
  ids.map((i) => licenceShort(licenceOf(i))).join('; ') + suffix,
];

/** Who publishes a source, as the registry says it, up to its first colon or bracket ("U.S. Geological Survey"). */
export const publisherOf = (id: string): string => (id === 'atlas' ? 'Commodity Flows Atlas' : (sources.value[id]?.publisher ?? id)).split(/[:(]/)[0].trim();

/** Publishers whose licence text states no permission to reuse their data: with any of them among `ids`, no CSV is offered. */
export function termsNotConfirmed(ids: string[]): string[] {
  const out: string[] = [];
  for (const id of new Set(ids)) {
    if (licenceAllows(licenceOf(id))) continue;
    const who = publisherOf(id);
    if (!out.includes(who)) out.push(who);
  }
  return out;
}

/** Save text as a file (UTF-8 with a byte-order mark). */
export function downloadCsv(file: string, text: string) {
  const url = URL.createObjectURL(new Blob(['﻿', text], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = file;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** "Crude oil, top exporters" -> "crude-oil-top-exporters": a file name part (cut at a word when it is long). */
export function slug(s: string): string {
  const t = s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return (t.length > 80 ? t.slice(0, 80).replace(/-[^-]*$/, '') : t) || 'data';
}
