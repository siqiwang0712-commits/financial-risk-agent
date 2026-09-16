/**
 * Data access for the Workbench.
 *
 * Two origins are possible and the UI always states which one is in play:
 *
 *   live          - the Next.js proxy reached the FastAPI upstream
 *   offline-sample - the bundled, real pipeline output for the repository's
 *                    synthetic fixture (see lib/demoFixture.ts)
 *
 * Falling back to the sample is deliberately limited to "the upstream is not
 * reachable" (proxy 502/503 or a network error). A validation, auth or server
 * error is surfaced as an error, never silently replaced with sample data.
 */

import { DEMO_FIXTURE } from "./demoFixture";
import type { AssessmentPayload, DataOrigin, Loaded, PilotPayload } from "./types";

export interface Failure {
  message: string;
  /** True when the upstream itself could not be reached. */
  upstreamUnavailable: boolean;
}

/** A load either succeeds with data, or fails with a reason the UI must show. */
export type LoadResult<T> =
  | { ok: true; loaded: Loaded<T> }
  | { ok: false; failure: Failure };

export const OFFLINE_NOTE = DEMO_FIXTURE.notice;

const PILOT_TIMEOUT_MS = 8000;
// Browser, proxy, and backend derive from one seconds-based setting. The
// browser keeps a four-second grace window so backend/proxy 504 contracts win
// over a local AbortError.
const configuredAnalysisSeconds = Number(
  process.env.NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS ?? 60,
);
const ANALYSIS_TIMEOUT_MS = (
  Number.isFinite(configuredAnalysisSeconds) && configuredAnalysisSeconds > 0
    ? configuredAnalysisSeconds
    : 60
) * 1_000 + 4_000;

function isUpstreamUnavailable(status: number): boolean {
  return status === 502 || status === 503;
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => ({}));
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return fallback;
}

/**
 * Minimal structural guard. A 200 response with a body that is not a pilot
 * payload (empty object, an HTML error page) used to reach `payload.rows.map`
 * and throw, blanking the page. The UI degrades instead.
 */
function isPilotPayload(body: unknown): body is PilotPayload {
  if (!body || typeof body !== "object") return false;
  const candidate = body as Partial<PilotPayload>;
  return Array.isArray(candidate.rows)
    && typeof candidate.snapshot === "string"
    && typeof candidate.benchmark_evidence_coverage === "number"
    && candidate.rows.every((row) => row && typeof row === "object"
      && typeof row.entity === "string" && typeof row.decision === "string"
      && (typeof row.score === "number" || row.score === null)
      && typeof row.reliability === "string" && typeof row.filing === "string");
}

export type EntityResult =
  | { ok: true; entityId: string }
  | { ok: false; failure: Failure };

/** Create a tenant-bound entity using the same credential used for analysis. */
export async function createEntity(apiKey: string, name: string): Promise<EntityResult> {
  let response: Response;
  try {
    response = await fetch("/api/v1/enterprise/entities", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ name }),
      signal: AbortSignal.timeout(PILOT_TIMEOUT_MS),
    });
  } catch {
    return { ok: false, failure: { message: "Could not reach the entity API.", upstreamUnavailable: true } };
  }
  const payload = await readJson(response);
  if (response.ok && payload && typeof payload === "object" && "id" in payload
      && typeof (payload as { id: unknown }).id === "string") {
    return { ok: true, entityId: (payload as { id: string }).id };
  }
  return {
    ok: false,
    failure: {
      message: detailOf(payload, `Entity creation failed (HTTP ${response.status}).`),
      upstreamUnavailable: isUpstreamUnavailable(response.status),
    },
  };
}

/**
 * Frozen v0.3.0 public pilot rows.
 *
 * The bundled sample is used only when the upstream is genuinely unreachable
 * (502/503, a network error, or a timeout). Validation, auth and server errors
 * are surfaced as failures, exactly as this module's contract promises; the
 * previous implementation silently returned sample data for all of them.
 */
export async function loadPilot(): Promise<LoadResult<PilotPayload>> {
  let response: Response;
  try {
    response = await fetch("/api/v1/public-pilot", {
      signal: AbortSignal.timeout(PILOT_TIMEOUT_MS),
    });
  } catch {
    return {
      ok: false,
      failure: {
        message: "The API upstream is unavailable. The bundled sample is still available.",
        upstreamUnavailable: true,
      },
    };
  }
  const body = await readJson(response);
  if (response.ok) {
    if (!isPilotPayload(body)) {
      return {
        ok: false,
        failure: {
          message: `Pilot data was not in the expected shape (HTTP ${response.status}).`,
          upstreamUnavailable: false,
        },
      };
    }
    return { ok: true, loaded: { payload: body, origin: "live" } };
  }
  const unavailable = isUpstreamUnavailable(response.status);
  return {
    ok: false,
    failure: {
      message: unavailable
        ? "The API upstream is unavailable. The bundled sample is still available."
        : detailOf(body, `Loading pilot data failed (HTTP ${response.status}).`),
      upstreamUnavailable: unavailable,
    },
  };
}

/** The bundled sample, requested explicitly by the user. */
export function loadSampleAssessment(): Loaded<AssessmentPayload> {
  return {
    payload: DEMO_FIXTURE.assessment,
    origin: "offline-sample",
    note: OFFLINE_NOTE,
  };
}

export interface AnalyzeInput {
  file: File;
  company: string;
  fiscalYear: number;
  apiKey: string;
  entityId: string;
}

export type AnalyzeResult =
  | { ok: true; loaded: Loaded<AssessmentPayload> }
  | { ok: false; failure: Failure };

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function evidence(value: unknown): boolean {
  if (!record(value)) return false;
  return typeof value.document === "string"
    && (finite(value.page) || value.page === null)
    && finite(value.confidence)
    && typeof value.verification_status === "string";
}

function decisionPath(value: unknown): boolean {
  if (!record(value) || !record(value.fusion_contribution) || !record(value.input_provenance)) return false;
  return typeof value.reason_code === "string"
    && typeof value.evidence_path_status === "string"
    && finite(value.coverage) && finite(value.disagreement)
    && strings(value.required_inputs) && strings(value.path)
    && Array.isArray(value.source_evidence) && value.source_evidence.every(evidence)
    && Object.values(value.input_provenance).every(
      (refs) => Array.isArray(refs) && refs.every(evidence),
    )
    && typeof value.fusion_contribution.method === "string"
    && typeof value.fusion_contribution.role === "string";
}

function agentPayload(value: unknown): boolean {
  if (!record(value) || !record(value.decision_trace) || !record(value.fusion)) return false;
  const trace = value.decision_trace;
  return typeof value.status === "string"
    && Array.isArray(value.plan) && value.plan.every((item) => record(item)
      && typeof item.id === "string" && typeof item.phase === "string"
      && typeof item.tool === "string" && typeof item.purpose === "string")
    && Array.isArray(value.trace) && value.trace.every((item) => record(item)
      && typeof item.step_id === "string" && typeof item.phase === "string"
      && typeof item.tool === "string" && typeof item.status === "string"
      && typeof item.summary === "string" && finite(item.latency_ms))
    && Array.isArray(value.conclusions) && value.conclusions.every((item) =>
      record(item) && typeof item.claim === "string" && typeof item.reason === "string"
      && typeof item.tool === "string" && typeof item.rationale === "string"
      && finite(item.confidence) && Array.isArray(item.evidence)
      && item.evidence.every(evidence))
    && Array.isArray(value.component_telemetry) && value.component_telemetry.every((item) =>
      record(item) && typeof item.component === "string" && typeof item.status === "string"
      && (finite(item.risk_before) || item.risk_before === null)
      && (finite(item.risk_after) || item.risk_after === null)
      && finite(item.coverage_before) && finite(item.coverage_after)
      && finite(item.disagreement_before) && finite(item.disagreement_after)
      && finite(item.estimated_cost_usd) && typeof item.decision_changed === "boolean")
    && strings(trace.decision_reason_codes)
    && finite(trace.material_path_count) && finite(trace.verified_path_count)
    && finite(trace.proof_coverage)
    && Array.isArray(trace.paths) && trace.paths.every(decisionPath)
    && strings(value.fusion.reason_codes);
}

function isAssessmentPayload(body: unknown): body is AssessmentPayload {
  if (!record(body)) return false;
  const candidate = body as Record<string, unknown>;
  const dimensions = candidate.dimensions;
  const confidenceComponents = candidate.confidence_components;
  const failure = candidate.failure_state;
  return (
    typeof candidate.company === "string"
    && typeof candidate.reporting_period === "string"
    && (finite(candidate.overall_score) || candidate.overall_score === null)
    && typeof candidate.risk_level === "string"
    && finite(candidate.confidence)
    && finite(candidate.evidence_coverage)
    && candidate.evidence_coverage >= 0 && candidate.evidence_coverage <= 1
    && record(dimensions) && Object.values(dimensions).every((dimension) =>
      record(dimension) && (finite(dimension.score) || dimension.score === null)
      && finite(dimension.coverage) && strings(dimension.key_drivers))
    && Array.isArray(candidate.models)
    && Array.isArray(candidate.triggered_rules)
    && Array.isArray(candidate.missing_information)
    && record(confidenceComponents) && Object.values(confidenceComponents).every(finite)
    && record(failure) && typeof failure.degraded === "boolean"
    && strings(failure.blocking_failures) && strings(failure.review_failures)
    && agentPayload(candidate.agent)
  );
}

/** Upload a PDF and run the Agent. */
export async function analyzeDocument(input: AnalyzeInput): Promise<AnalyzeResult> {
  const body = new FormData();
  body.append("company", input.company);
  body.append("fiscal_year", String(input.fiscalYear));
  body.append("entity_id", input.entityId);
  body.append("file", input.file);

  let response: Response;
  try {
    response = await fetch("/api/v1/documents/analyze", {
      method: "POST",
      body,
      headers: { "X-API-Key": input.apiKey },
      signal: AbortSignal.timeout(ANALYSIS_TIMEOUT_MS),
    });
  } catch {
    return {
      ok: false,
      failure: {
        message:
          "Could not reach the Workbench API route. The bundled sample is still available.",
        upstreamUnavailable: true,
      },
    };
  }

  const payload = await readJson(response);

  if (response.ok) {
    if (!isAssessmentPayload(payload)) {
      return {
        ok: false,
        failure: { message: "Analysis response was not in the expected shape.", upstreamUnavailable: false },
      };
    }
    return {
      ok: true,
      loaded: { payload, origin: "live" },
    };
  }

  const unavailable = isUpstreamUnavailable(response.status);
  return {
    ok: false,
    failure: {
      message: unavailable
        ? detailOf(payload, "The API upstream is unavailable. The bundled sample is still available.")
        : detailOf(payload, `Analysis failed (HTTP ${response.status}).`),
      upstreamUnavailable: unavailable,
    },
  };
}
