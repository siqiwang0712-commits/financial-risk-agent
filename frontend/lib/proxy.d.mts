export const ALLOWED_METHODS: readonly string[];
export const FORWARDED_REQUEST_HEADERS: readonly string[];
export const FORWARDED_RESPONSE_HEADERS: readonly string[];
export const DEFAULT_UPSTREAM_TIMEOUT_MS: number;
export const ANALYSIS_UPSTREAM_TIMEOUT_MS: number;
export function upstreamTimeoutMs(segments: unknown): number;

export function selectRequestHeaders(headers: Headers | null | undefined): Record<string, string>;
export function selectResponseHeaders(
  headers: Headers | null | undefined,
  options: { bodyIsUnchanged: boolean },
): Record<string, string>;
export function isValidSegment(segment: unknown): boolean;
