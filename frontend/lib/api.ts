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

export const OFFLINE_NOTE = DEMO_FIXTURE.notice;

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

/** Frozen v0.3.0 public pilot rows. Falls back to the bundled copy. */
export async function loadPilot(): Promise<Loaded<PilotPayload>> {
  try {
    const response = await fetch("/api/v1/public-pilot");
    if (response.ok) {
      return { payload: (await response.json()) as PilotPayload, origin: "live" };
    }
    if (isUpstreamUnavailable(response.status)) {
      return { payload: DEMO_FIXTURE.pilot, origin: "offline-sample", note: OFFLINE_NOTE };
    }
  } catch {
    return { payload: DEMO_FIXTURE.pilot, origin: "offline-sample", note: OFFLINE_NOTE };
  }
  return { payload: DEMO_FIXTURE.pilot, origin: "offline-sample", note: OFFLINE_NOTE };
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
    return {
      ok: true,
      loaded: { payload: payload as AssessmentPayload, origin: "live" },
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
