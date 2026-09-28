import type { DataOrigin } from "../lib/types";

interface Props {
  origin: DataOrigin | null;
  runtime: string;
}

/**
 * The origin badge is not decoration. Every number below it either came from a
 * live run or from a bundled sample, and the reader must never have to guess.
 */
export function OriginBadge({ origin }: { origin: DataOrigin | null }) {
  if (!origin) {
    return <span className="originBadge idle">no result loaded</span>;
  }
  return origin === "live" ? (
    <span className="originBadge live">live run</span>
  ) : (
    <span className="originBadge sample">bundled sample</span>
  );
}

export function AppHeader({ origin, runtime }: Props) {
  return (
    <header className="appHeader">
      <div className="brand">
        <h1>
          Fin<span>Risk</span>
        </h1>
        <small>Financial intelligence system</small>
      </div>
      <nav className="appNav" aria-label="Workbench sections">
        <a href="#why">Why</a>
        <a href="#system">System</a>
        <a href="#research">Research</a>
        <a href="#case">Assessment</a>
      </nav>
      <div className="headerMeta">
        <OriginBadge origin={origin} />
        <span className="runtime">{runtime}</span>
        <span className="prototype">
          <i aria-hidden="true" />
          research system
        </span>
      </div>
    </header>
  );
}
