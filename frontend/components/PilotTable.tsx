import { displayRatio, displayReliability, displayScore, normalizeDecision } from "../lib/presentation.mjs";
import type { Loaded, PilotPayload } from "../lib/types";
import type { DataOrigin } from "../lib/types";

interface Props {
  pilot: Loaded<PilotPayload> | null;
}

const COLUMNS = [
  "Entity",
  "Decision",
  "Risk index",
  "Evidence coverage",
  "Reliability",
  "Filing",
] as const;

/**
 * The frozen v0.3.0 pilot. These are the repository's published, immutable
 * results - including the ones that are unflattering to the architecture.
 */
export function PilotTable({ pilot }: Props) {
  if (!pilot) {
    return (
      <section className="panel pilotPanel">
        <PanelHeading
          kicker="Analyst workbench"
          title="Portfolio risk intelligence"
          meta="loading frozen pilot…"
        />
        <p className="skeleton">Loading the frozen public pilot…</p>
      </section>
    );
  }

  const { payload, origin, note } = pilot;
  const rows = payload.rows ?? [];

  return (
    <section className="panel pilotPanel">
      <PanelHeading
        kicker="Analyst workbench"
        title="Portfolio risk intelligence"
        // `isPilotPayload` requires `annotation_status`, but the bundled sample
        // bypasses that guard, and a missing field used to render the literal
        // text "annotation: undefined".
        meta={`${payload.snapshot ?? "unknown snapshot"} · annotation: ${payload.annotation_status ?? "not recorded"}`}
      />

      <div className="tableScroll">
        <table className="dataTable">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const decision = normalizeDecision(row.decision);
              return (
                // `filing` is the frozen artifact's unique row id; `entity` is not
                // guaranteed unique across filings.
                <tr key={row.filing || row.entity}>
                  <th scope="row">{row.entity}</th>
                  <td>
                    <span className={`riskPill ${decision.toLowerCase()}`}>{decision}</span>
                  </td>
                  <td className="numeric">{displayScore(row.score)}</td>
                  <td className="numeric">{displayRatio(row.coverage)}</td>
                  <td className="uncalibrated">{displayReliability(row.reliability, null)}</td>
                  <td className="mono dim">{row.filing}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="panelNote">
        {origin === "offline-sample"
          ? "Served from the bundled copy because the API upstream was not reachable. "
          : ""}
        These rows are the immutable v0.3.0 pilot artifact, not current runtime decisions, and they
        are not externally validated. The pilot is three company-years with a single reviewer.
        {typeof payload.dataset_evidence_coverage === "number"
          ? ` Dataset mean evidence coverage: ${displayRatio(payload.dataset_evidence_coverage)}.`
          : ""}
      </p>
      {note ? <p className="panelNote subtle">{note}</p> : null}
    </section>
  );
}

export function PanelHeading({
  kicker,
  title,
  meta,
}: {
  kicker?: string;
  title: string;
  meta?: string;
}) {
  return (
    <div className="panelHeading">
      <div>
        {kicker ? <p className="kicker">{kicker}</p> : null}
        <h2>{title}</h2>
      </div>
      {meta ? <p className="panelMeta">{meta}</p> : null}
    </div>
  );
}
