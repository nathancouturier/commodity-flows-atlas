import type { IControl, Map as MLMap } from 'maplibre-gl';

/** One button under the zoom buttons: back to the first view (the whole trading world, clear of the panels). */
export class ResetViewControl implements IControl {
  private el = document.createElement('div');
  constructor(private home: () => void) {}
  onAdd(_map: MLMap): HTMLElement {
    this.el.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'reset-view';
    b.title = 'Reset view';
    b.setAttribute('aria-label', 'Reset view');
    b.innerHTML =
      '<svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true"><circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M3 10h14M10 3c-3 3-3 11 0 14M10 3c3 3 3 11 0 14" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>';
    b.addEventListener('click', () => this.home());
    this.el.append(b);
    return this.el;
  }
  onRemove() {
    this.el.remove();
  }
}
