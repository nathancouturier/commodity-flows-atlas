/** Number and figure formatting helpers. */
import type { Fig, Family } from '../types';
import { sourceLabel } from './data';

const nf = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

/** Compact human number: 1234 -> "1,234", 0.456 -> "0.46", 12.34 -> "12.3". */
export function fmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return nf0.format(v);
  if (a >= 10) return nf.format(v);
  if (a >= 1) return v.toFixed(2).replace(/\.?0+$/, '');
  return v.toPrecision(2);
}

export function pct(share: number | null | undefined, digits = 1): string {
  if (share == null || Number.isNaN(share)) return '—';
  const p = share * 100;
  if (p > 0 && p < 0.1) return '<0.1%';
  return `${p.toFixed(p >= 10 ? 0 : digits)}%`;
}

export function fig(f: Fig | undefined): string {
  if (!f) return '—';
  return f.u === '%' ? `${fmt(f.v)}%` : `${fmt(f.v)} ${f.u}`;
}

/** "Source name, 2024" — used under every figure. */
export function cite(f: { s: string; y: number | string } | undefined): string {
  if (!f) return '';
  return `${sourceLabel(f.s)}, ${f.y}`;
}

export const FAMILY_COLOR: Record<Family, string> = {
  energy: '#ffb547',
  metals: '#9db7ff',
  softs: '#7ee0a1',
  freight: '#3ee6ff',
};

export const FAMILY_LABEL: Record<Family, string> = {
  energy: 'Energy',
  metals: 'Metals & minerals',
  softs: 'Softs & agriculture',
  freight: 'Freight',
};

/** Touch-first device (phones, tablets): hints talk about taps instead of mouse and keys. */
export const TOUCH = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

/**
 * Choropleth opacity as a function of a country's share of the world total (0..1).
 * Shared by the map style (paint expression) and the colour-ramp legend.
 */
export const SHARE_STOPS: [number, number][] = [
  [0, 0],
  [0.005, 0.18],
  [0.05, 0.42],
  [0.15, 0.68],
  [0.35, 0.9],
];

export function shareOpacity(v: number): number {
  const s = SHARE_STOPS;
  if (v <= s[0][0]) return s[0][1];
  for (let i = 1; i < s.length; i++) {
    if (v <= s[i][0]) {
      const [x0, y0] = s[i - 1];
      const [x1, y1] = s[i];
      return y0 + ((v - x0) / (x1 - x0)) * (y1 - y0);
    }
  }
  return s[s.length - 1][1];
}
