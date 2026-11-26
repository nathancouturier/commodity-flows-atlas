/**
 * Animated flow particles drawn on a 2D canvas above the map.
 *
 * MapLibre draws the static flow lines (crisp, hit-testable); this overlay adds
 * moving "comets" along each path to show direction and relative volume.
 * Screen-space geometry is cached and recomputed only when the map moves.
 */
import type { Map as MLMap } from 'maplibre-gl';
import { copyShifts } from './copies';
import { shouldDraw } from './overlayRules';

export interface FlowPath {
  id: string;
  coords: [number, number][];
  color: string;
  /** relative weight 0..1, drives particle density and size */
  weight: number;
  dim?: boolean;
}

interface Projected {
  path: FlowPath;
  xs: Float32Array;
  ys: Float32Array;
  cum: Float32Array;
  len: number;
}

export class FlowOverlay {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private pathSets = new Map<string, FlowPath[]>();
  private paths: FlowPath[] = [];
  private projected: Projected[] = [];
  private dirty = true;
  private raf = 0;
  private t0 = performance.now();
  private motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  private reduced = this.motionQuery.matches;
  /** a frame must be drawn although nothing moved (first frame, setting changed, shown again, resized) */
  private repaint = true;
  private visible = true;

  constructor(private map: MLMap) {
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'flow-canvas';
    this.canvas.setAttribute('aria-hidden', 'true');
    map.getContainer().appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d')!;
    const invalidate = () => (this.dirty = true);
    map.on('move', invalidate);
    map.on('resize', () => {
      this.resize();
      invalidate();
      this.repaint = true;
    });
    this.resize();
    // the setting can change while the page is open
    this.motionQuery.addEventListener('change', () => {
      this.reduced = this.motionQuery.matches;
      this.repaint = true;
    });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) cancelAnimationFrame(this.raf);
      else {
        this.repaint = true;
        this.loop();
      }
    });
    this.loop();
  }

  /** Set the particle paths of one named line set; sets are merged. */
  setPaths(key: string, paths: FlowPath[]) {
    if (paths.length) this.pathSets.set(key, paths);
    else this.pathSets.delete(key);
    this.paths = [...this.pathSets.values()].flat();
    this.dirty = true;
  }

  setVisible(v: boolean) {
    this.visible = v;
    this.canvas.style.display = v ? '' : 'none';
    if (v) this.repaint = true;
  }

  private resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const { clientWidth: w, clientHeight: h } = this.map.getContainer();
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  private project() {
    const { clientWidth: w, clientHeight: h } = this.map.getContainer();
    // the longitudes in view, with the 20 px margin `draw` culls at; `unproject` does not wrap them, so a camera
    // centred beyond +-180 (a selected trans-Pacific lane) gives a range beyond +-180
    const edges = [[-20, -20], [w + 20, -20], [-20, h + 20], [w + 20, h + 20]].map(([x, y]) => this.map.unproject([x, y]).lng);
    const west = Math.min(...edges);
    const east = Math.max(...edges);
    const out: Projected[] = [];
    for (const path of this.paths) {
      const n = path.coords.length;
      if (n < 2) continue;
      // the world is drawn again on each side: one projection per copy of the path that is in view
      for (const shift of copyShifts(path.coords, west, east)) {
        const xs = new Float32Array(n);
        const ys = new Float32Array(n);
        const cum = new Float32Array(n);
        let len = 0;
        for (let i = 0; i < n; i++) {
          const p = this.map.project([path.coords[i][0] + shift, path.coords[i][1]]);
          xs[i] = p.x;
          ys[i] = p.y;
          if (i > 0) len += Math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1]);
          cum[i] = len;
        }
        out.push({ path, xs, ys, cum, len });
      }
    }
    this.projected = out;
    this.dirty = false;
  }

  private loop = () => {
    this.raf = requestAnimationFrame(this.loop);
    if (!this.visible) return;
    const changed = this.dirty;
    if (changed) this.project();
    // under reduced motion the particles stand still: a still frame is drawn once, not on every animation frame
    if (!shouldDraw({ reduced: this.reduced, dirty: changed, repaint: this.repaint })) return;
    this.repaint = false;
    this.draw((performance.now() - this.t0) / 1000);
  };

  private draw(t: number) {
    const ctx = this.ctx;
    const { clientWidth: w, clientHeight: h } = this.map.getContainer();
    ctx.clearRect(0, 0, w, h);
    ctx.globalCompositeOperation = 'lighter';
    const zoom = this.map.getZoom();
    const speed = 38 + zoom * 6; // px per second
    for (const pr of this.projected) {
      if (pr.len < 4) continue;
      const { path } = pr;
      const spacing = 70 - 40 * path.weight; // denser for bigger flows
      const count = Math.max(1, Math.floor(pr.len / spacing));
      const r = 1.1 + 1.9 * path.weight;
      const alpha = path.dim ? 0.18 : 0.9;
      ctx.fillStyle = path.color;
      const phase = this.reduced ? 0 : (t * speed) % spacing;
      for (let k = 0; k < count; k++) {
        const d = k * spacing + phase;
        if (d > pr.len) break;
        // comet: head + two fading tail dots
        for (let tail = 0; tail < 3; tail++) {
          const dd = d - tail * r * 2.2;
          if (dd < 0) break;
          const pt = this.at(pr, dd);
          if (!pt || pt[0] < -20 || pt[1] < -20 || pt[0] > w + 20 || pt[1] > h + 20) continue;
          ctx.globalAlpha = alpha * (1 - tail * 0.33);
          ctx.beginPath();
          ctx.arc(pt[0], pt[1], r * (1 - tail * 0.22), 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }

  /** Point at distance d along the projected path (binary search on cumulative length). */
  private at(pr: Projected, d: number): [number, number] | null {
    const { cum, xs, ys } = pr;
    let lo = 0;
    let hi = cum.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cum[mid] < d) lo = mid + 1;
      else hi = mid;
    }
    if (lo === 0) return [xs[0], ys[0]];
    const seg = cum[lo] - cum[lo - 1] || 1;
    const f = (d - cum[lo - 1]) / seg;
    return [xs[lo - 1] + (xs[lo] - xs[lo - 1]) * f, ys[lo - 1] + (ys[lo] - ys[lo - 1]) * f];
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    this.canvas.remove();
  }
}
