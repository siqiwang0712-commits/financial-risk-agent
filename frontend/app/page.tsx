"use client";

import { useState } from "react";
import { AgentTrace } from "../components/AgentTrace";
import { AppHeader } from "../components/AppHeader";
import { DecisionPaths } from "../components/DecisionPaths";
import { DecisionSummary } from "../components/DecisionSummary";
import { DimensionGrid } from "../components/DimensionGrid";
import { EvidenceTrail } from "../components/EvidenceTrail";
import { TelemetryPanel } from "../components/TelemetryPanel";
import { WhyDecision } from "../components/WhyDecision";
import { DEMO_FIXTURE } from "../lib/demoFixture";

type TabKey = "overview" | "dimensions" | "evidence" | "paths" | "trace" | "telemetry";

const TAB_LABEL: Record<TabKey, string> = {
  overview: "Decision logic",
  dimensions: "Risk dimensions",
  evidence: "Evidence chain",
  paths: "Decision paths",
  trace: "Agent execution",
  telemetry: "Telemetry",
};

const RESEARCH_METRICS = [
  { value: "2,000", label: "company-disjoint E4 cohort" },
  { value: "674", label: "deterministically verified outcomes" },
  { value: "+0.030", label: "paired AUROC improvement" },
  { value: "0.0015", label: "Holm-adjusted p-value" },
] as const;

const PIPELINE = [
  { index: "01", title: "Ingest", copy: "Annual filings, XBRL facts and page-aware documents." },
  { index: "02", title: "Compute", copy: "Ratios, trends and traditional models run deterministically." },
  { index: "03", title: "Interpret", copy: "Constrained language models extract claims, never final scores." },
  { index: "04", title: "Verify", copy: "Every material conclusion must resolve to source evidence." },
  { index: "05", title: "Decide", copy: "Failure-aware fusion can flag, review, pass or abstain." },
] as const;

export default function Page() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const assessment = DEMO_FIXTURE.assessment;
  const agent = assessment.agent;
  const trace = agent?.decision_trace;
  const completedSteps = agent?.trace.filter((step) => step.status === "success").length ?? 0;

  return (
    <>
      <AppHeader origin="offline-sample" runtime="v0.3.4" />
      <main className="showcaseShell">
        <section className="showcaseHero" id="overview">
          <div className="heroCopy">
            <p className="heroEyebrow"><span /> Structured financial reasoning</p>
            <h2>
              Financial risk intelligence
              <em>that shows its work.</em>
            </h2>
            <p className="heroLead">
              FinRisk turns corporate filings into an auditable risk view. Deterministic finance,
              constrained language models and evidence verification stay separate—so every decision
              can be inspected, challenged and replayed.
            </p>
            <div className="heroActions">
              <a className="primaryAction" href="#case">Explore the assessment</a>
              <a className="secondaryAction" href="#research">View validation evidence <span>↗</span></a>
            </div>
            <div className="heroTrust">
              <span>Deterministic arithmetic</span>
              <span>Evidence-linked decisions</span>
              <span>Explicit abstention</span>
            </div>
          </div>

          <aside className="heroConsole" aria-label="Bundled assessment snapshot">
            <header>
              <div>
                <span className="consolePulse" />
                ANALYSIS SNAPSHOT
              </div>
              <code>FR-2025-0042</code>
            </header>
            <div className="consoleEntity">
              <div>
                <small>ENTITY</small>
                <b>{assessment.company}</b>
                <span>FY{assessment.reporting_period} · synthetic filing</span>
              </div>
              <strong>{assessment.final_decision}</strong>
            </div>
            <div className="consoleScore">
              <div className="scoreDial" style={{ "--score": `${assessment.overall_score ?? 0}%` } as React.CSSProperties}>
                <span>{assessment.overall_score?.toFixed(0) ?? "—"}</span>
                <small>/100</small>
              </div>
              <div className="scoreNarrative">
                <small>HEURISTIC RISK INDEX</small>
                <b>{assessment.risk_level}</b>
                <p>Not a probability · reliability remains UNCALIBRATED</p>
              </div>
            </div>
            <div className="consoleGrid">
              <Metric label="Evidence coverage" value={`${Math.round(assessment.evidence_coverage * 100)}%`} />
              <Metric label="Verified paths" value={`${trace?.verified_path_count ?? 0}/${trace?.material_path_count ?? 0}`} />
              <Metric label="Rules triggered" value={String(assessment.triggered_rules.length)} />
              <Metric label="Steps completed" value={`${completedSteps}/${agent?.plan.length ?? 0}`} />
            </div>
            <div className="consoleFlow" aria-label="Analysis stages">
              {PIPELINE.map((step) => <i key={step.index} />)}
            </div>
            <footer>
              <span>● FROZEN DEMO DATA</span>
              <span>REPLAYABLE OUTPUT</span>
            </footer>
          </aside>
        </section>

        <section className="metricRibbon" aria-label="E4 study headline metrics">
          {RESEARCH_METRICS.map((metric) => (
            <article key={metric.label}>
              <b>{metric.value}</b>
              <span>{metric.label}</span>
            </article>
          ))}
        </section>

        <section className="systemSection" id="system">
          <SectionIntro
            eyebrow="How the system works"
            title="A controlled path from filing to decision."
            copy="The Agent orchestrates the work. It does not own the numbers, thresholds or final truth. Each layer has one explicit responsibility and one inspectable output."
          />
          <div className="pipelineGrid">
            {PIPELINE.map((step) => (
              <article key={step.index}>
                <span>{step.index}</span>
                <h3>{step.title}</h3>
                <p>{step.copy}</p>
              </article>
            ))}
          </div>
          <div className="systemRule">
            <span>CORE CONTROL</span>
            <p>No verified evidence path → <b>REVIEW</b> or <b>ABSTAIN</b></p>
            <code>evidence → fact → metric → rule/model → dimension → decision</code>
          </div>
        </section>

        <section className="researchSection" id="research">
          <SectionIntro
            eyebrow="External validation · E4"
            title="Measured on unseen companies, not polished examples."
            copy="The locked v0.3.4 architecture was evaluated out of time on a company-disjoint SEC cohort. The positive result belongs to temporal structured signal—not to an unqualified claim about AI or default prediction."
          />
          <div className="researchLayout">
            <article className="benchmarkCard">
              <header>
                <div>
                  <small>PRIMARY COMPARISON · VERIFIED SUBSET</small>
                  <h3>Temporal structure added ranking signal</h3>
                </div>
                <span className="evidenceStatus">ESTABLISHED_E4</span>
              </header>
              <div className="benchmarkPlot">
                <BenchmarkBar label="B0 · Ratios only" value={0.678} />
                <BenchmarkBar label="B6 · Temporal risk" value={0.708} highlight />
              </div>
              <div className="deltaCallout">
                <div><small>PAIRED ΔAUROC</small><b>+0.030</b></div>
                <div><small>95% CI</small><b>+0.014 — +0.048</b></div>
                <div><small>ADJUSTED P</small><b>0.0015</b></div>
              </div>
            </article>

            <aside className="researchBoundaries">
              <div className="boundaryTop">
                <span>33.7%</span>
                <p>verified outcome coverage<br /><small>674 of 2,000 companies</small></p>
              </div>
              <h3>What the evidence says—and what it does not.</h3>
              <ul>
                <li className="positive"><b>Established</b><span>B6 improved B0 on the prespecified verified cohort.</span></li>
                <li><b>Not established</b><span>Local Agent or hybrid incremental value.</span></li>
                <li><b>Not claimed</b><span>Calibrated default probability, regulatory or production validation.</span></li>
              </ul>
            </aside>
          </div>
        </section>

        <section className="caseSection" id="case">
          <SectionIntro
            eyebrow="Interactive evidence room"
            title="One assessment. Every layer visible."
            copy="This complete synthetic case is bundled with the site, so the public demo never depends on a private backend. It is genuine pipeline output, clearly labelled as synthetic and uncalibrated."
          />
          <div className="caseNotice">
            <span>STATIC DEMO</span>
            <p>{DEMO_FIXTURE.notice}</p>
          </div>

          <DecisionSummary payload={assessment} />

          <nav className="tabBar showcaseTabs" aria-label="Assessment sections">
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
                <span>{String((Object.keys(TAB_LABEL) as TabKey[]).indexOf(key) + 1).padStart(2, "0")}</span>
                {TAB_LABEL[key]}
              </button>
            ))}
          </nav>

          <div className="tabBody" id="tab-panel" role="tabpanel" aria-labelledby={`tab-${activeTab}`} aria-live="polite">
            {activeTab === "overview" ? <WhyDecision payload={assessment} /> : null}
            {activeTab === "dimensions" ? <DimensionGrid dimensions={assessment.dimensions} /> : null}
            {activeTab === "evidence" && agent ? <EvidenceTrail conclusions={agent.conclusions} /> : null}
            {activeTab === "paths" && trace ? <DecisionPaths trace={trace} /> : null}
            {activeTab === "trace" && agent ? <AgentTrace plan={agent.plan} trace={agent.trace} status={agent.status} /> : null}
            {activeTab === "telemetry" && agent ? <TelemetryPanel items={agent.component_telemetry} /> : null}
          </div>
        </section>

        <section className="capabilitySection" id="controls">
          <SectionIntro
            eyebrow="System controls"
            title="Designed for challenge, not blind trust."
            copy="Severity, evidence quality, coverage, disagreement and reliability remain separate quantities throughout the interface."
          />
          <div className="capabilityGrid">
            <Capability number="68" title="Versioned rules" copy="Thresholds live in inspectable policy, not scattered application code." />
            <Capability number="04" title="Traditional models" copy="Altman, Beneish, Piotroski and Ohlson run with applicability checks." />
            <Capability number="08" title="Risk dimensions" copy="Coverage and missingness stay visible beside every dimension score." />
            <Capability number="100%" title="Replayable" copy="Inputs, versions and material evidence paths are retained for audit." />
          </div>
        </section>

        <footer className="showcaseFooter">
          <div>
            <b>FinRisk</b>
            <span>Evidence-grounded financial risk intelligence</span>
          </div>
          <p>
            v0.3.4 · Research prototype · All scores are heuristic and UNCALIBRATED.<br />
            Not a bankruptcy probability, credit rating, investment recommendation or regulatory determination.
          </p>
        </footer>
      </main>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><small>{label}</small><b>{value}</b></div>;
}

function SectionIntro({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return (
    <header className="sectionIntro">
      <p className="eyebrow">{eyebrow}</p>
      <div><h2>{title}</h2><p>{copy}</p></div>
    </header>
  );
}

function BenchmarkBar({ label, value, highlight = false }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`benchmarkRow${highlight ? " highlight" : ""}`}>
      <span>{label}</span>
      <i><b style={{ width: `${value * 100}%` }} /></i>
      <strong>{value.toFixed(3)}</strong>
    </div>
  );
}

function Capability({ number, title, copy }: { number: string; title: string; copy: string }) {
  return (
    <article>
      <span>{number}</span>
      <h3>{title}</h3>
      <p>{copy}</p>
    </article>
  );
}
