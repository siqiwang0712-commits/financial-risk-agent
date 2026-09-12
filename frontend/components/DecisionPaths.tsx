"use client";

import { useState } from "react";
import { evidenceLocator } from "../lib/presentation.mjs";
import type { DecisionPath, DecisionTrace } from "../lib/types";

interface Props {
  trace: DecisionTrace;
}

type Filter = "all" | "verified" | "unverified";

/**
 * The drill-down. Each material driver expands into the full chain:
 * document -> evidence span -> fact -> metric -> rule/model -> dimension -> decision.
 *
 * Paths whose inputs do not all carry verified provenance are shown too, and
 * labelled. Hiding them would make the decision look better supported than it is.
 */
export function DecisionPaths({ trace }: Props) {
  const [filter, setFilter] = useState<Filter>("all");

  const counts = {
    all: trace.paths.length,
    verified: trace.paths.filter((path) => path.evidence_path_status === "VERIFIED").length,
    unverified: trace.paths.filter((path) => path.evidence_path_status !== "VERIFIED").length,
  };

  const visible = trace.paths.filter((path) =>
    filter === "all" ? true : filter === "verified"
      ? path.evidence_path_status === "VERIFIED"
      : path.evidence_path_status !== "VERIFIED",
  );

  return (
    <div className="pathsPanel">
      <div className="pathsHeader">
        <div className="pathsSummary">
          <p>
            <b>{trace.verified_path_count}</b> of <b>{trace.material_path_count}</b> material paths are
            fully verified. Proof coverage <b>{trace.proof_coverage}</b>.
          </p>
          <p className="muted">
            Initial fusion decision <code>{trace.initial_fusion_decision}</code> → failure-aware{" "}
            <code>{trace.failure_aware_decision}</code> → final <code>{trace.decision}</code>.
          </p>
        </div>

        <div className="filterGroup" role="group" aria-label="Filter decision paths">
          {(["all", "verified", "unverified"] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={filter === option ? "active" : ""}
              onClick={() => setFilter(option)}
            >
              {option} <span>{counts[option]}</span>
            </button>
          ))}
        </div>
      </div>

      {visible.length ? (
        <ul className="pathList">
          {visible.map((path, index) => (
            <PathRow key={`${path.reason_code}-${index}`} path={path} />
          ))}
        </ul>
      ) : (
        <p className="muted">No paths match this filter.</p>
      )}
    </div>
  );
}

function PathRow({ path }: { path: DecisionPath }) {
  const verified = path.evidence_path_status === "VERIFIED";
  const provenanceEntries = Object.entries(path.input_provenance);

  return (
    <li className={`pathRow ${verified ? "verified" : "unverified"}`}>
      <details>
        <summary>
          <span className={`statusChip ${verified ? "ok" : "bad"}`}>
            {path.evidence_path_status}
          </span>
          <b>{path.reason_code}</b>
          <span className="pathDomain">{path.risk_domain}</span>
          <span className="pathRole">
            {path.fusion_contribution.role} · {path.fusion_contribution.dimension_score ?? "N/A"}
          </span>
        </summary>

        <div className="pathBody">
          <div className="pathMeta">
            <p>
              <span>Rule / model</span>
              <code>{path.rule_or_model}</code>
            </p>
            <p>
              <span>Fusion</span>
              <code>
                {path.fusion_contribution.method} · {path.fusion_version}
              </code>
            </p>
            <p>
              <span>Rule version</span>
              <code>{path.rule_version.slice(0, 16)}…</code>
            </p>
            <p>
              <span>Confidence · coverage · disagreement</span>
              <code>
                {path.confidence ?? "N/A"} · {path.coverage} · {path.disagreement}
              </code>
            </p>
          </div>

          <div className="pathChain">
            <small>Chain</small>
            <ol>
              {path.path.map((node) => (
                <li key={node}>{node.replace(/_/g, " ")}</li>
              ))}
            </ol>
          </div>

          <div className="pathProvenance">
            <small>Required inputs and their provenance</small>
            {provenanceEntries.length ? (
              <ul>
                {provenanceEntries.map(([input, refs]) => {
                  const allVerified = refs.length > 0 && refs.every((ref) => ref.verification_status === "verified");
                  return (
                    <li key={input} className={allVerified ? "ok" : "bad"}>
                      <code>{input}</code>
                      {refs.length ? (
                        <>
                          <span className={`statusChip ${allVerified ? "ok" : "bad"}`}>
                            {allVerified ? "verified" : refs[0].verification_status}
                          </span>
                          <em>{evidenceLocator(refs[0])}</em>
                        </>
                      ) : (
                        <span className="statusChip bad">no source</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="muted">This path records no required inputs.</p>
            )}
          </div>

          <div className="pathEvidence">
            <small>Source evidence</small>
            {path.source_evidence.length ? (
              path.source_evidence.map((item, index) => (
                <blockquote key={index}>
                  <b>{item.verification_status}</b> · {evidenceLocator(item)}
                  <p>{item.quote || item.source_text || "(no quoted span)"}</p>
                </blockquote>
              ))
            ) : (
              <p className="notice">
                No authoritative source span reaches this material driver. Under the project&apos;s
                own rules the decision must degrade or abstain.
              </p>
            )}
          </div>
        </div>
      </details>
    </li>
  );
}
