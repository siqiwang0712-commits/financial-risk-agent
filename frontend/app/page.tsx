"use client";

import { useState } from "react";
import { AgentTrace } from "../components/AgentTrace";
import { AssurancePanel } from "../components/AssurancePanel";
import { AppHeader } from "../components/AppHeader";
import { DecisionPaths } from "../components/DecisionPaths";
import { DecisionSummary } from "../components/DecisionSummary";
import { DimensionGrid } from "../components/DimensionGrid";
import { EvidenceTrail } from "../components/EvidenceTrail";
import { TelemetryPanel } from "../components/TelemetryPanel";
import { WhyDecision } from "../components/WhyDecision";
import { DEMO_FIXTURE } from "../lib/demoFixture";

type TabKey = "overview" | "assurance" | "dimensions" | "evidence" | "paths" | "trace" | "telemetry";

const TAB_LABEL: Record<TabKey, string> = {
  overview: "Decision logic",
  assurance: "Assurance",
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
  { index: "05", title: "Propose", copy: "Rules, models and Agent reasoning propose a risk disposition." },
  { index: "06", title: "Authorize", copy: "Assurance checks evidence, fragility and distribution validity before a final decision." },
] as const;

const PROJECT_URL = "https://github.com/siqiwang0712-commits/financial-risk-agent";
const VALIDATION_URL = `${PROJECT_URL}/blob/main/research/e4/public/VALIDATION_REPORT.md`;
const DOCUMENTATION_URL = `${PROJECT_URL}/blob/main/README.md`;

export default function Page() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const assessment = DEMO_FIXTURE.assessment;
  const agent = assessment.agent;
  const trace = agent?.decision_trace;
  const completedSteps = agent?.trace.filter((step) => step.status === "success").length ?? 0;

  return (
    <>
      <AppHeader origin="offline-sample" runtime="v0.4.2" />
      <main className="showcaseShell">
        <section className="showcaseHero" id="overview">
          <div className="heroCopy">
            <p className="heroEyebrow"><span /> Assured selective financial intelligence</p>
            <h2>
              Prediction proposes.{" "}
              <em>Assurance authorizes.</em>
            </h2>
            <p className="heroLead">
              FinRisk separates financial-risk prediction from decision authorization. A final decision
              is issued only after deterministic evidence, fragility and distribution-validity checks.
            </p>
            <div className="heroRoute" aria-label="FinRisk input, process and output">
              <div><small>INPUT</small><span>Company filing</span></div>
              <i aria-hidden="true">→</i>
              <div><small>PROCESS</small><span>Metrics · rules · evidence analysis</span></div>
              <i aria-hidden="true">→</i>
              <div><small>OUTPUT</small><span>Final decision + certificate</span></div>
            </div>
            <div className="heroActions">
              <a className="primaryAction" href="#case">Explore the assessment</a>
              <a className="secondaryAction" href="#research">View validation evidence <span>↗</span></a>
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
            <div className="consoleDecisionNote">
              <b>WHY ABSTAIN?</b>
              <span>High risk signal + insufficient verified evidence → ABSTAIN</span>
              <p>Evidence requirements govern the decision; a high score cannot override them.</p>
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

        <section className="whySection" id="why">
          <SectionIntro
            eyebrow="Why FinRisk?"
            title="More control than a report uploaded to a chatbot."
            copy="FinRisk separates calculation, interpretation and verification so the reasoning remains inspectable—and can stop when the evidence is not good enough."
          />
          <div className="whyFinRiskGrid">
            <article>
              <span>01</span>
              <h3>Traceable</h3>
              <p>Material conclusions link back through facts, metrics and rules to supporting evidence.</p>
            </article>
            <article>
              <span>02</span>
              <h3>Failure-aware</h3>
              <p>Missing, weak or conflicting evidence can trigger review or abstention instead of a guess.</p>
            </article>
            <article>
              <span>03</span>
              <h3>Hybrid by design</h3>
              <p>Deterministic components own the numbers and core logic; language models are constrained to interpretation.</p>
            </article>
          </div>
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
              <p className="benchmarkInterpretation">
                In plain language: adding multi-period financial signals improved how the system
                ranked future financial-deterioration risk among unseen companies.
              </p>
            </article>

            <aside className="researchBoundaries">
              <div className="boundaryTop">
                <span>33.7%</span>
                <p>verified outcome coverage<br /><small>674 of 2,000 companies</small></p>
              </div>
              <p className="coverageNote">
                This is an evaluation filter: primary metrics include only future outcomes that met
                the prespecified deterministic verification criteria.
              </p>
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
            eyebrow="Explore a frozen assessment"
            title="One assessment. Every layer visible."
            copy="Use the tabs to inspect a bundled synthetic result, its evidence chain and decision paths. Nothing here is generated live; the example is frozen and UNCALIBRATED."
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
            {activeTab === "assurance" ? <AssurancePanel assurance={assessment.assurance} certificate={assessment.decision_certificate} /> : null}
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
            <Capability number="Hash-bound" title="Replay artifacts" copy="Inputs, versions and material evidence paths are retained for deterministic verification." />
          </div>
          <nav className="resourceLinks" aria-label="Project resources">
            <div>
              <small>CONTINUE EXPLORING</small>
              <p>Review the implementation, the complete E4 methods and the project documentation.</p>
            </div>
            <a href={PROJECT_URL}>View on GitHub <span aria-hidden="true">↗</span></a>
            <a href={VALIDATION_URL}>Read validation report <span aria-hidden="true">↗</span></a>
            <a href={DOCUMENTATION_URL}>Documentation <span aria-hidden="true">↗</span></a>
          </nav>
        </section>

        <footer className="showcaseFooter">
          <div>
            <b>FinRisk</b>
            <span>Evidence-grounded financial risk intelligence</span>
          </div>
          <p>
            v0.4.2 · Research prototype · Assurance policy is heuristic and UNCALIBRATED.<br />
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
