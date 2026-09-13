"use client";

import type { ComponentTelemetry } from "../lib/types";

interface Props {
  items: ComponentTelemetry[];
}

/**
 * Component-level telemetry: what changed, by how much, at what cost.
 *
 * Each row shows before → after for risk, coverage and disagreement, plus
 * whether the component flipped the decision or added new evidence.
 */
export function TelemetryPanel({ items }: Props) {
  const totalLatency = items.reduce((s, i) => s + i.latency_ms, 0);
  const totalCost = items.reduce((s, i) => s + i.estimated_cost_usd, 0);
  const flipped = items.filter((i) => i.decision_changed).length;

  return (
    <div>
      <div className="telemetryMeta">
        <p>
          <b>{items.length}</b> components · <b>{flipped}</b> flipped decision ·{" "}
          <b>{totalLatency.toLocaleString()}</b> ms total ·{" "}
          <b>${totalCost.toFixed(4)}</b> est. cost
        </p>
      </div>

      <div className="telemetryTableWrap">
        <table className="telemetryTable">
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Risk</th>
              <th>Coverage</th>
              <th>Disagreement</th>
              <th>New evidence</th>
              <th>Decision flipped</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.component}>
                <td>
                  <code>{item.component}</code>
                </td>
                <td>
                  {/* The producer emits "executed"/"not_executed"; matching only
                      "success" painted every normally-executed row red. */}
                  <span
                    className={`statusChip ${
                      item.status === "executed" || item.status === "success" ? "ok" : "bad"
                    }`}
                  >
                    {item.status}
                  </span>
                </td>
                <td>
                  <Delta before={item.risk_before} after={item.risk_after} />
                </td>
                <td>
                  <DeltaPct before={item.coverage_before} after={item.coverage_after} />
                </td>
                <td>
                  <DeltaPct before={item.disagreement_before} after={item.disagreement_after} />
                </td>
                <td>{item.new_evidence}</td>
                <td>
                  {item.decision_changed ? (
                    <span className="statusChip bad">yes</span>
                  ) : (
                    <span className="statusChip ok">no</span>
                  )}
                </td>
                <td>{item.latency_ms.toLocaleString()} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Delta({ before, after }: { before: number | null; after: number | null }) {
  if (before == null && after == null) return <span className="muted">—</span>;
  if (before == null) return <span>{after?.toFixed(3) ?? "—"}</span>;
  if (after == null) return <span className="bad">{before.toFixed(3)} → null</span>;
  const diff = after - before;
  const sign = diff > 0 ? "+" : "";
  const cls = diff > 0 ? "bad" : diff < 0 ? "ok" : "muted";
  return (
    <span className={cls}>
      {before.toFixed(3)} → {after.toFixed(3)} ({sign}{diff.toFixed(3)})
    </span>
  );
}

function DeltaPct({ before, after }: { before: number; after: number }) {
  const diff = after - before;
  const sign = diff > 0 ? "+" : "";
  const cls = diff > 0 ? "ok" : diff < 0 ? "bad" : "muted";
  return (
    <span className={cls}>
      {(before * 100).toFixed(0)}% → {(after * 100).toFixed(0)}% ({sign}{(diff * 100).toFixed(0)}pp)
    </span>
  );
}
