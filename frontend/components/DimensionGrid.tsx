import type { Dimension } from "../lib/types";

const LABELS: Record<string, string> = {
  liquidity: "Liquidity",
  solvency_leverage: "Solvency & leverage",
  profitability: "Profitability",
  cash_flow: "Cash flow",
  earnings_quality: "Earnings quality",
  accounting: "Accounting",
  governance_audit: "Governance & audit",
  business_going_concern: "Business / going concern",
};

function band(score: number | null): string {
  if (score === null) return "none";
  if (score >= 80) return "critical";
  if (score >= 60) return "high";
  if (score >= 40) return "moderate";
  if (score >= 20) return "low";
  return "very_low";
}

/**
 * Eight dimensions, each shown with its own coverage. A dimension with no
 * triggered evidence is rendered as unknown rather than as zero - that
 * distinction is the point of the panel.
 */
export function DimensionGrid({ dimensions }: { dimensions: Record<string, Dimension> }) {
  const entries = Object.entries(dimensions);

  return (
    <div className="dimensionGrid">
      {entries.map(([key, dimension], index) => {
        const tone = band(dimension.score);
        const unknown = dimension.score === null;
        return (
          <article key={key} className={`dimensionCard band-${tone}`}>
            <header>
              <span className="index">{String(index + 1).padStart(2, "0")}</span>
              <h3>{LABELS[key] ?? key.replace(/_/g, " ")}</h3>
            </header>

            <p className="dimensionScore">
              {unknown ? <span className="unknown">unknown</span> : <><b>{dimension.score}</b><span>/100</span></>}
              <em>{dimension.level}</em>
            </p>

            <i className="bar" aria-hidden="true">
              <b style={{ width: `${unknown || dimension.score === null ? 0 : Math.min(100, Math.max(0, dimension.score))}%` }} />
            </i>

            <p className="dimensionMeta">
              coverage {dimension.coverage.toFixed(2)} · trend {dimension.trend}
            </p>

            {dimension.key_drivers.length ? (
              <ul className="driverList">
                {dimension.key_drivers.slice(0, 4).map((driver) => (
                  <li key={driver}>{driver}</li>
                ))}
                {dimension.key_drivers.length > 4 ? (
                  <li className="more">+{dimension.key_drivers.length - 4} more</li>
                ) : null}
              </ul>
            ) : (
              <p className="dimensionEmpty">No triggered evidence reached this dimension.</p>
            )}
          </article>
        );
      })}
    </div>
  );
}
