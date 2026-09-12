import type { PlanStep, TraceStep } from "../lib/types";

interface Props {
  plan: PlanStep[];
  trace: TraceStep[];
  status: string;
}

const PHASE_LABEL: Record<string, string> = {
  analyze: "Analyse",
  collect: "Collect",
  cross_check: "Cross-check",
  synthesize: "Synthesise",
  verify: "Verify",
  tool: "Tool",
};

/**
 * The declared plan next to the steps that actually ran.
 *
 * Only structured execution metadata is shown: step, tool, status, result
 * summary and latency. No hidden reasoning is stored or displayed, which is why
 * there is no "thinking" panel here.
 */
export function AgentTrace({ plan, trace, status }: Props) {
  const executed = new Set(trace.map((step) => step.step_id));

  return (
    <div className="traceLayout">
      <div className="traceColumn">
        <h3>Declared plan</h3>
        <ol className="planList">
          {plan.map((step, index) => (
            <li key={step.id} className={executed.has(step.id) ? "ran" : "skipped"}>
              <span className="planIndex">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <b>{step.tool}</b>
                <small>{PHASE_LABEL[step.phase] ?? step.phase}</small>
                <p>{step.purpose}</p>
              </div>
              <em>{executed.has(step.id) ? "ran" : "skipped"}</em>
            </li>
          ))}
        </ol>
      </div>

      <div className="traceColumn">
        <h3>
          Executed steps
          <span className={`terminalStatus ${status.toLowerCase()}`}>{status}</span>
        </h3>
        <ol className="execList">
          {trace.map((step, index) => (
            <li key={`${step.step_id}-${index}`} className={step.status === "success" ? "ok" : "failed"}>
              <span className="execIndex">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <b>{step.tool}</b>
                <small>
                  {step.phase} · {step.status} · {step.latency_ms} ms
                </small>
                <p>{step.summary}</p>
                {step.error ? <p className="execError">{step.error}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
