/**
 * Registry of map feature modules. Each module subscribes to the store and
 * updates its own sources/layers. Modules are added phase by phase.
 */
import type { Map as MLMap } from 'maplibre-gl';
import { onMapReady } from './controller';

type Installer = (m: MLMap) => void;
const installers: Installer[] = [];

export function registerLayerModule(fn: Installer) {
  installers.push(fn);
}

export function installLayers(_m: MLMap) {
  onMapReady((m) => installers.forEach((fn) => fn(m)));
}
