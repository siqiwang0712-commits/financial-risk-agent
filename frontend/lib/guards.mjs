/**
 * Structural guards for API responses.
 *
 * These live in a plain `.mjs` module rather than inside `api.ts` for one
 * reason: the browser bundle and `node --test` must share exactly one
 * implementation. A guard that only exists inside a Next/React module cannot be
 * exercised by the test runner, and an untested guard is precisely how an
 * HTTP 200 carrying `{}` (or an HTML error page) reached the renderer and
 * blanked the page.
 *
 * `lib/presentation.mjs` follows the same split, with `presentation.d.mts`
 * supplying the types.
 */

/** A JSON object: not `null`, not an array, not a primitive. */
export function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A finite number, i.e. one that can be formatted or compared. */
export function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * The frozen public-pilot payload.
 *
 * `annotation_status` is part of the check because the table renders it as
 * literal text: without it a response missing the field displayed the string
 * "annotation: undefined" instead of failing loudly.
 */
export function isPilotPayload(body) {
  if (!isRecord(body)) return false;
  return (
    Array.isArray(body.rows) &&
    typeof body.snapshot === "string" &&
    typeof body.annotation_status === "string"
  );
}

/**
 * The assessment payload the Workbench renders.
 *
 * Deliberately shallow: it asserts the *containers* every panel iterates over
 * (`dimensions`, `confidence_components`, `missing_information`) and the two
 * strings used as labels. Scalar values inside those containers are the
 * components' own responsibility, so a single missing metric degrades one row
 * rather than rejecting the whole response. This is the second layer of defence
 * behind the components' own guards - both are needed: the guard catches a
 * wrong-shaped response, the components catch a wrong-shaped field.
 */
export function isAssessmentPayload(body) {
  if (!isRecord(body)) return false;
  return (
    typeof body.company === "string" &&
    typeof body.risk_level === "string" &&
    isRecord(body.dimensions) &&
    isRecord(body.confidence_components) &&
    Array.isArray(body.missing_information)
  );
}
