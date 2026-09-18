export const HSTS_VALUE: string;
export function isSecureRequest(proto: string | null | undefined): boolean;
export function hstsHeaderFor(proto: string | null | undefined): string | null;
