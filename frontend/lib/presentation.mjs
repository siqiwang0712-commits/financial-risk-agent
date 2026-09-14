/**
 * Format the risk index.
 *
 * The index is a computed float, so `String(score)` could surface a binary
 * artefact ("42.699999999999996") next to a `toFixed(3)` coverage figure in the
 * same row. Rounding to two decimals and dropping trailing zeros keeps the
 * headline readable without inventing precision the index does not have.
 * Non-numeric input renders as 'N/A' rather than 'NaN' or 'undefined'.
 */
export function displayScore(score) {
  if (typeof score !== 'number' || !Number.isFinite(score)) return 'N/A';
  return String(Number(score.toFixed(2)));
}

/**
 * Format a 0-1 ratio to a fixed number of decimals.
 *
 * Anything that is not a finite number renders as 'N/A' rather than 'NaN',
 * 'undefined' or a blank cell, so a missing value is visible instead of silent.
 */
export function displayRatio(value, decimals = 3) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'N/A';
  return value.toFixed(decimals);
}

export function displayReliability(status, value) {
  if (status === 'UNCALIBRATED') return 'UNCALIBRATED — not a probability';
  return value === null || value === undefined ? status : `${status} ${value}`;
}

export function normalizeDecision(value) {
  return ['ABSTAIN', 'REVIEW', 'PASS', 'FLAG'].includes(value) ? value : 'REVIEW';
}

/**
 * Locate a quoted span: source · document · page.
 *
 * `page` is an `int` on the backend whose default is `0`, and `0` is its "no
 * page was recorded" sentinel - PDF pages are 1-based. The previous
 * `evidence.page ? ... : null` reached that conclusion by accident of
 * truthiness, so a legitimate `page: 0` and a missing page were indistinguishable
 * from a typo in the test. The sentinel is now explicit, and `evidence` itself is
 * optional so a partially-populated record cannot throw during render.
 */
export function evidenceLocator(evidence) {
  const page = evidence?.page;
  const locator = typeof page === 'number' && Number.isFinite(page) && page > 0 ? `page ${page}` : null;
  return [evidence?.source, evidence?.document, locator].filter(Boolean).join(' · ');
}

export async function safeApiJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}
