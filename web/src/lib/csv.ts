/**
 * CSV downloads, built in the browser. One convention for every file of the site: one row per value, a header row,
 * CRLF line ends, a byte-order mark so that spreadsheet programs read accents as UTF-8, and the source and its
 * licence in the columns of each row (the registry data/sources.json gives both).
 */
import { sourceLabel, sources } from './data';

/** The Atlas's own figures are published under this licence (the registry's `atlas` entry says the same). */
export const ATLAS_LICENCE = 'CC BY 4.0 (attribution: Commodity Flows Atlas)';

export const csvCell = (x: string | number | boolean | null | undefined): string => {
  const t = x == null ? '' : String(x);
  return /[",\r\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
};

/** Header and rows as CSV text. */
export function toCsv(head: string[], rows: (string | number | boolean | null | undefined)[][]): string {
  return [head, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
}

/** Name of the source, as the page prints it. `extra` is appended after a semicolon (what the Atlas did to the figure). */
export function sourceName(id: string, extra?: string): string {
  return [sourceLabel(id), extra].filter(Boolean).join('; ');
}

/** The licence of a source, as data/sources.json states it ("" for a source the registry lacks). */
export function licenceOf(id: string): string {
  return id === 'atlas' ? ATLAS_LICENCE : (sources.value[id]?.licence ?? '');
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
