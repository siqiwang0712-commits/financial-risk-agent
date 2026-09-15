"use client";

import { useEffect, useState } from "react";
import { AppHeader } from "../components/AppHeader";
import { IntakePanel } from "../components/IntakePanel";
import { PilotTable } from "../components/PilotTable";
import { DecisionSummary } from "../components/DecisionSummary";
import { WhyDecision } from "../components/WhyDecision";
import { DimensionGrid } from "../components/DimensionGrid";
import { EvidenceTrail } from "../components/EvidenceTrail";
import { DecisionPaths } from "../components/DecisionPaths";
import { AgentTrace } from "../components/AgentTrace";
import { TelemetryPanel } from "../components/TelemetryPanel";
import { PanelBoundary } from "../components/PanelBoundary";
import {
  loadPilot,
  loadSampleAssessment,
  analyzeDocument,
} from "../lib/api";
import type {
  AssessmentPayload,
  Loaded,
  PilotPayload,
  DataOrigin,
} from "../lib/types";

type TabKey =
  | "overview"
  | "dimensions"
  | "evidence"
  | "paths"
  | "trace"
  | "telemetry";

const TAB_LABEL: Record<TabKey, string> = {
  overview: "Why this decision",
  dimensions: "Risk dimensions",
  evidence: "Evidence chain",
  paths: "Decision paths",
  trace: "Agent trace",
  telemetry: "Telemetry",
};

/** Shown when a tab has no data in this response, instead of a blank panel. */
function EmptyPanel({ reason }: { reason: string }) {
  return (
    <section className="panel">
      <p className="muted">{reason}</p>
    </section>
  );
}

export default function Page() {
  const [pilot, setPilot] = useState<Loaded<PilotPayload> | null>(null);
  const [assessment, setAssessment] = useState<AssessmentPayload | null>(null);
  // The badge must not claim an origin before a request has happened, and the
  // pilot and the assessment are separate results that must not overwrite each
  // other's provenance.
  const [pilotOrigin, setPilotOrigin] = useState<DataOrigin | null>(null);
  const [assessmentOrigin, setAssessmentOrigin] = useState<DataOrigin | null>(null);
  const [loadingPilot, setLoadingPilot] = useState(true);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorIsUpstream, setErrorIsUpstream] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [assessmentRevision, setAssessmentRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    loadPilot().then((result) => {
      if (cancelled) return;
      if (result.ok) {
        setPilot(result.loaded);
        setPilotOrigin(result.loaded.origin);
      } else {
        setError(result.failure.message);
        setErrorIsUpstream(result.failure.upstreamUnavailable);
      }
      setLoadingPilot(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoadSample = () => {
    setError(null);
    setErrorIsUpstream(false);
    // No artificial delay: the sample is synchronous, and a timer that outlives
    // unmount would call setState on a dead component.
    const res = loadSampleAssessment();
    setAssessment(res.payload);
    setAssessmentRevision((value) => value + 1);
    setAssessmentOrigin(res.origin);
    setActiveTab("overview");
  };

  const handleAnalyze = async (opts: {
    file: File;
    company: string;
    fiscalYear: number;
    apiKey: string;
  }) => {
    setError(null);
    setErrorIsUpstream(false);
    setLoadingAnalysis(true);
    const result = await analyzeDocument(opts);
    setLoadingAnalysis(false);
    if (result.ok) {
      setAssessment(result.loaded.payload);
      setAssessmentRevision((value) => value + 1);
      setAssessmentOrigin(result.loaded.origin);
      setActiveTab("overview");
    } else {
      setError(result.failure.message);
      setErrorIsUpstream(result.failure.upstreamUnavailable);
      // A failed run must not leave a stale "live run" badge in place.
      setAssessmentOrigin(null);
    }
  };

  const agent = assessment?.agent;
  const origin = assessmentOrigin ?? pilotOrigin;

  return (
    <>
      <AppHeader
        origin={origin}
        runtime={pilot?.payload.runtime ?? "v0.3.2"}
      />
      <main>
        {/* Pilot table */}
        <section className="portfolio">
          <p className="eyebrow">Public pilot — FY2024 filings</p>
          <h2>Evidence-grounded risk assessment</h2>
          <p className="portfolioNote">
            A rule-hybrid agent that reads annual reports, computes metrics, evaluates models,
            checks for contradictions, and renders a decision only when the evidence chain is
            verifiable. If sources are missing or conflicting, it abstains.
          </p>

          {loadingPilot ? (
            <p className="muted">Loading pilot data…</p>
          ) : pilot ? (
            <PilotTable pilot={pilot} />
          ) : (
            <p className="muted">
              Pilot data could not be loaded from the API upstream. Use “Load bundled sample”
              below to inspect the offline sample.
            </p>
          )}
        </section>

        {/* Intake */}
        <section className="intakeSection">
          <IntakePanel
            onLoadSample={handleLoadSample}
            onAnalyze={handleAnalyze}
            busy={loadingAnalysis}
            error={error}
            errorIsUpstream={errorIsUpstream}
            onDismissError={() => setError(null)}
          />
        </section>

        {/* Analysis result */}
        {assessment && (
          <section className="analysisSection">
            <PanelBoundary key={`summary-${assessmentRevision}`} label="Decision summary">
              <DecisionSummary payload={assessment} />
            </PanelBoundary>

            <nav className="tabBar" aria-label="Analysis sections">
              {(Object.keys(TAB_LABEL) as TabKey[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  id={`tab-${key}`}
                  role="tab"
                  aria-selected={activeTab === key}
                  aria-controls="tab-panel"
                  className={activeTab === key ? "active" : ""}
                  onClick={() => setActiveTab(key)}
                >
                  {TAB_LABEL[key]}
                </button>
              ))}
            </nav>

            <div
              className="tabBody"
              id="tab-panel"
              role="tabpanel"
              aria-labelledby={`tab-${activeTab}`}
              aria-live="polite"
              aria-busy={loadingAnalysis}
            >
              {/* Keyed on the active tab so switching tabs clears a previous
                  panel failure instead of showing the fallback forever. */}
              <PanelBoundary
                key={`${assessmentRevision}-${activeTab}`}
                label={TAB_LABEL[activeTab]}
              >
                {activeTab === "overview" ? (
                  <WhyDecision payload={assessment} />
                ) : null}

                {activeTab === "dimensions" ? (
                  <DimensionGrid dimensions={assessment.dimensions} />
                ) : null}

                {activeTab === "evidence" ? (
                  agent?.conclusions?.length ? (
                    <EvidenceTrail conclusions={agent.conclusions} />
                  ) : (
                    <EmptyPanel reason="No verified conclusions in this response." />
                  )
                ) : null}

                {activeTab === "paths" ? (
                  agent?.decision_trace ? (
                    <DecisionPaths trace={agent.decision_trace} />
                  ) : (
                    <EmptyPanel reason="No decision trace in this response." />
                  )
                ) : null}

                {activeTab === "trace" ? (
                  agent ? (
                    <AgentTrace
                      plan={agent.plan}
                      trace={agent.trace}
                      status={agent.status}
                    />
                  ) : (
                    <EmptyPanel reason="No agent trace in this response." />
                  )
                ) : null}

                {activeTab === "telemetry" ? (
                  agent?.component_telemetry?.length ? (
                    <TelemetryPanel items={agent.component_telemetry} />
                  ) : (
                    <EmptyPanel reason="No component telemetry in this response." />
                  )
                ) : null}
              </PanelBoundary>
            </div>
          </section>
        )}

        {/* Footer */}
        <footer>
          <p>
            FinRisk-Agent v0.3.2 · Un-calibrated research prototype · Not for production use.
          </p>
          <p className="muted">
            {assessment?.disclaimer ||
              "Risk scores are heuristic assessment scores, not bankruptcy probabilities or investment advice."}
          </p>
          <p className="muted">
            All decisions are provisional. Evidence coverage, model disagreement and reliability
            status are shown explicitly so that over-confidence is visible.
          </p>
        </footer>
      </main>
    </>
  );
}
