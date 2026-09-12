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

export default function Page() {
  const [pilot, setPilot] = useState<Loaded<PilotPayload> | null>(null);
  const [assessment, setAssessment] = useState<AssessmentPayload | null>(null);
  const [origin, setOrigin] = useState<DataOrigin>("offline-sample");
  const [loadingPilot, setLoadingPilot] = useState(true);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorIsUpstream, setErrorIsUpstream] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  useEffect(() => {
    let cancelled = false;
    loadPilot().then((res) => {
      if (cancelled) return;
      setPilot(res);
      setOrigin(res.origin);
      setLoadingPilot(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoadSample = () => {
    setError(null);
    setErrorIsUpstream(false);
    setLoadingAnalysis(true);
    setTimeout(() => {
      const res = loadSampleAssessment();
      setAssessment(res.payload);
      setOrigin(res.origin);
      setLoadingAnalysis(false);
      setActiveTab("overview");
    }, 400);
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
      setOrigin(result.loaded.origin);
      setActiveTab("overview");
    } else {
      setError(result.failure.message);
      setErrorIsUpstream(result.failure.upstreamUnavailable);
    }
  };

  const agent = assessment?.agent;

  return (
    <>
      <AppHeader
        origin={origin}
        runtime={pilot?.payload.runtime ?? "v0.3.2"}
      />
      <main>
        {/* Pilot table */}
        <section className="portfolio">
          <p className="eyebrow">Public pilot — 2021 filings</p>
          <h2>Evidence-grounded risk assessment</h2>
          <p className="portfolioNote">
            A rule-hybrid agent that reads annual reports, computes metrics, evaluates models,
            checks for contradictions, and renders a decision only when the evidence chain is
            verifiable. If sources are missing or conflicting, it abstains.
          </p>

          {loadingPilot ? (
            <p className="muted">Loading pilot data…</p>
          ) : (
            <PilotTable pilot={pilot} />
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
            <DecisionSummary payload={assessment} />

            <nav className="tabBar" aria-label="Analysis sections">
              {(Object.keys(TAB_LABEL) as TabKey[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  className={activeTab === key ? "active" : ""}
                  onClick={() => setActiveTab(key)}
                >
                  {TAB_LABEL[key]}
                </button>
              ))}
            </nav>

            <div className="tabBody">
              {activeTab === "overview" && (
                <WhyDecision payload={assessment} />
              )}

              {activeTab === "dimensions" && (
                <DimensionGrid dimensions={assessment.dimensions} />
              )}

              {activeTab === "evidence" && (
                <EvidenceTrail
                  conclusions={agent?.conclusions ?? []}
                />
              )}

              {activeTab === "paths" && agent?.decision_trace && (
                <DecisionPaths trace={agent.decision_trace} />
              )}

              {activeTab === "trace" && agent && (
                <AgentTrace
                  plan={agent.plan}
                  trace={agent.trace}
                  status={agent.status}
                />
              )}

              {activeTab === "telemetry" && agent?.component_telemetry && (
                <TelemetryPanel items={agent.component_telemetry} />
              )}
            </div>
          </section>
        )}

        {/* Footer */}
        <footer>
          <p>
            FinRisk-Agent v0.3.0 · Un-calibrated research prototype · Not for production use.
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
