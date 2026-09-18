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
import * as guards from "./guards.mjs";
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
// The shape logic itself lives in `lib/guards.mjs` so `node --test` can exercise it;
// these wrappers keep the TypeScript type predicates the call sites rely on.
function isPilotPayload(body: unknown): body is PilotPayload {
  return guards.isPilotPayload(body);
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

// The shape logic itself lives in `lib/guards.mjs` so `node --test` can exercise it
// without a TypeScript toolchain; these wrappers keep the type predicates the call
// sites rely on.
function isAssessmentPayload(body: unknown): body is AssessmentPayload {
  return guards.isAssessmentPayload(body);
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
