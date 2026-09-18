import type { AssessmentPayload, PilotPayload } from "./types";

export function isEvidence(value: unknown): boolean;
export function isDecisionPath(value: unknown): boolean;
export function isAgentPayload(value: unknown): boolean;
export function isAssessmentPayload(body: unknown): body is AssessmentPayload;
export function isPilotPayload(body: unknown): body is PilotPayload;
