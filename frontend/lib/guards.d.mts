import type { AssessmentPayload, PilotPayload } from "./types";

export function isRecord(value: unknown): value is Record<string, unknown>;
export function isFiniteNumber(value: unknown): value is number;
export function isPilotPayload(body: unknown): body is PilotPayload;
export function isAssessmentPayload(body: unknown): body is AssessmentPayload;
