/**
 * Transport-security decision helpers.
 *
 * `Strict-Transport-Security` only means anything when the response actually arrives
 * over TLS: a browser ignores the header on a plain-HTTP response, and a header that
 * claims a year of HTTPS-only for a deployment that is not even serving HTTPS is a
 * statement the app cannot back up. It was previously emitted unconditionally from
 * `next.config.ts` — including on the local HTTP stack — so it advertised a guarantee
 * that did not exist. It is now derived from the request instead.
 *
 * Kept as a pure module so `node --test` covers the decision without booting Next.
 */

export const HSTS_VALUE = "max-age=31536000; includeSubDomains";

/** True when the request reached the app over TLS (directly or via a TLS terminator). */
export function isSecureRequest(proto) {
  // `x-forwarded-proto` is a bare scheme ("https"); `request.nextUrl.protocol` carries
  // the URL delimiter ("https:"). Accept both.
  const normalized = String(proto ?? "").trim().toLowerCase().replace(/:$/, "");
  return normalized === "https" || normalized === "wss";
}

/** The HSTS header value for this request, or null when it must not be sent. */
export function hstsHeaderFor(proto) {
  return isSecureRequest(proto) ? HSTS_VALUE : null;
}
