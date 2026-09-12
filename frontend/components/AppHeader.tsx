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
        <span className="eyebrow">Evidence → Intelligence → Decision → Action → Monitoring</span>
        <h1>
          FinRisk<span>Workbench</span>
        </h1>
      </div>
      <nav className="appNav" aria-label="Workbench sections">
        <span>Portfolio</span>
        <span>Entity</span>
        <span>Evidence</span>
        <span>Decision</span>
        <span>Governance</span>
      </nav>
      <div className="headerMeta">
        <OriginBadge origin={origin} />
        <span className="runtime">runtime {runtime}</span>
        <span className="prototype">
          <i aria-hidden="true" />
          research prototype
        </span>
      </div>
    </header>
  );
}
