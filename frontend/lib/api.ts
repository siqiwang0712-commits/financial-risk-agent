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
import { isAssessmentPayload, isPilotPayload } from "./guards.mjs";
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
/**
 * Uploading a filing and running the Agent is a long request by design (PDF
 * parsing, extraction, verification), so the ceiling is generous - but it must
 * exist. Without it a hung upstream left `loadingAnalysis` true forever and the
 * submit button permanently disabled, with no error and no way back.
 */
const ANALYZE_TIMEOUT_MS = 120_000;

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
}

export type AnalyzeResult =
  | { ok: true; loaded: Loaded<AssessmentPayload> }
  | { ok: false; failure: Failure };

/** Upload a PDF and run the Agent. */
export async function analyzeDocument(input: AnalyzeInput): Promise<AnalyzeResult> {
  const body = new FormData();
  body.append("company", input.company);
  body.append("fiscal_year", String(input.fiscalYear));
  body.append("file", input.file);

  let response: Response;
  try {
    response = await fetch("/api/v1/documents/analyze", {
      method: "POST",
      body,
      headers: { "X-API-Key": input.apiKey },
      signal: AbortSignal.timeout(ANALYZE_TIMEOUT_MS),
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
    // `loadPilot` has always validated its payload; this path did not, so an
    // HTTP 200 carrying `{}` or an HTML error page was handed to the panels as
    // an `AssessmentPayload` and threw during render. A shape mismatch is a
    // failure to report, not a reason to show the sample.
    if (!isAssessmentPayload(payload)) {
      return {
        ok: false,
        failure: {
          message: `The analysis response was not in the expected shape (HTTP ${response.status}).`,
          upstreamUnavailable: false,
        },
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
