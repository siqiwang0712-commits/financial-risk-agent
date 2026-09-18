export const ALLOWED_METHODS: Set<string>;
export const FORWARDED_REQUEST_HEADERS: string[];
export const FORWARDED_RESPONSE_HEADERS: string[];
export const SEGMENT_PATTERN: RegExp;
export const DEFAULT_UPLOAD_BYTES: number;
export const DEFAULT_TIMEOUT_SECONDS: number;
export const CORRELATION_ID_PATTERN: RegExp;

export function normalizeCorrelationId(
  raw: string | null | undefined,
  generate?: () => string,
): string;
export function resolveUpstream(env: Record<string, string | undefined>): URL | null;
export function rebuildTarget(base: URL, segments: string[], search: string): URL | null;
export function uploadLimit(env: Record<string, string | undefined>): number;
export const MULTIPART_OVERHEAD_BYTES: number;
export function uploadEnvelopeLimit(env: Record<string, string | undefined>): number;
export function upstreamTimeoutMs(
  env: Record<string, string | undefined>,
  graceMs?: number,
): number;
