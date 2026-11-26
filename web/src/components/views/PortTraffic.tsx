/**
 * The "Weekly port traffic" block of a port page, loaded when a port that has a PortWatch id opens: the block's code, the chart and
 * the port's file stay out of every other page. The block itself is PortTrafficSection.tsx.
 */
import { lazy, Suspense } from 'preact/compat';

const PortTrafficSection = lazy(() => import('./PortTrafficSection'));

export default function PortTraffic({ id, name, note }: { id: string; name: string; note?: string }) {
  return (
    <Suspense fallback={null}>
      <PortTrafficSection key={id} id={id} name={name} note={note} />
    </Suspense>
  );
}
