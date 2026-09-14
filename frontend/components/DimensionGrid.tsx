import { displayRatio } from "../lib/presentation.mjs";
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

/**
 * Severity band for a dimension score.
 *
 * `undefined` is folded in with `null` on purpose: both mean "no score was
 * produced". A truthiness or `=== null` test let `undefined` fall through to the
 * final `return`, which painted a dimension with no evidence as `very_low` -
 * a *safe* band for a dimension nothing is known about.
 */
function band(score: number | null | undefined): string {
  if (score === null || score === undefined) return "none";
  if (score >= 80) return "critical";
  if (score >= 60) return "high";
  if (score >= 40) return "moderate";
  if (score >= 20) return "low";
  return "very_low";
}

function hasScore(score: number | null | undefined): score is number {
  return typeof score === "number" && Number.isFinite(score);
}

/**
 * Eight dimensions, each shown with its own coverage. A dimension with no
 * triggered evidence is rendered as unknown rather than as zero - that
 * distinction is the point of the panel.
 */
export function DimensionGrid({ dimensions }: { dimensions: Record<string, Dimension> }) {
  const entries = Object.entries(dimensions ?? {});

  return (
    <div className="dimensionGrid">
      {entries.map(([key, dimension], index) => {
        const tone = band(dimension?.score);
        const unknown = !hasScore(dimension?.score);
        const drivers = dimension?.key_drivers ?? [];
        return (
          <article key={key} className={`dimensionCard band-${tone}`}>
            <header>
              <span className="index">{String(index + 1).padStart(2, "0")}</span>
              <h3>{LABELS[key] ?? key.replace(/_/g, " ")}</h3>
            </header>

            <p className="dimensionScore">
              {unknown ? <span className="unknown">unknown</span> : <><b>{dimension.score}</b><span>/100</span></>}
              <em>{dimension?.level ?? "unknown"}</em>
            </p>

            <i className="bar" aria-hidden="true">
              <b style={{ width: `${unknown ? 0 : Math.min(100, Math.max(0, dimension.score as number))}%` }} />
            </i>

            <p className="dimensionMeta">
              coverage {displayRatio(dimension?.coverage, 2)} · trend {dimension?.trend ?? "unknown"}
            </p>

            {drivers.length ? (
              <ul className="driverList">
                {drivers.slice(0, 4).map((driver) => (
                  <li key={driver}>{driver}</li>
                ))}
                {drivers.length > 4 ? (
                  <li className="more">+{drivers.length - 4} more</li>
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
