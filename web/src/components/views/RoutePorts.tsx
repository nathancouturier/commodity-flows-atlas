/** The ports of a route on the route page, each a link to its asset page, or to the largest lane through it. */
import { Fragment } from 'preact';
import type { InfraType } from '../../types';
import { select } from '../../lib/store';
import { laneOfGroups, loadPortIndex, portRowOf } from '../../lib/infra';
import { useLoaded } from './shared';
import '../../styles/infra.css';

/**
 * The ports of a route: a link to its asset page when the route names the asset (`assets`, written by
 * pipeline/infrastructure/route_assets.py) or when the port index row of the port is an asset; otherwise, for a port of
 * the port index (pipeline/freight/build_port_index.py), a link to the largest lane through it of a customs group the route
 * carries (`groups`: a steel route does not open a coal lane); otherwise plain text. `c` is the country of this end of the
 * route (`ends`), which tells two ports of one name apart.
 */
export function RoutePorts({ ports, assets, c, groups }: { ports: string[]; assets?: (string | null)[]; c?: string | null; groups: string[] }) {
  const needIndex = ports.some((_, i) => !assets?.[i]);
  const rows = useLoaded(() => (needIndex ? loadPortIndex().catch(() => []) : Promise.resolve([])), [needIndex]);
  return (
    <>
      {ports.map((name, i) => {
        const row = !assets?.[i] && rows ? portRowOf(rows, name, c) : undefined;
        const a = assets?.[i] ?? row?.asset;
        const at = a ? a.indexOf(':') : -1;
        const lane = !a ? laneOfGroups(row, groups) : null;
        return (
          <Fragment key={`${name}${i}`}>
            {i > 0 && ', '}
            {a && at > 0 ? (
              <button class="port-link" title={`Open the asset page of ${name}`} onClick={() => select({ kind: 'infra', id: a.slice(at + 1), layer: a.slice(0, at) as InfraType })}>
                {name}
              </button>
            ) : lane ? (
              <button class="port-link" title="Opens the largest lane of this route's cargo through this port" onClick={() => select({ kind: 'lane', id: lane })}>
                {name}
              </button>
            ) : (
              name
            )}
          </Fragment>
        );
      })}
    </>
  );
}
