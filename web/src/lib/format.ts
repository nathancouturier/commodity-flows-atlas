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

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}
