export function displayScore(score) {
  return score === null || score === undefined ? 'N/A' : String(score);
}

export function displayReliability(status, value) {
  if (status === 'UNCALIBRATED') return 'UNCALIBRATED — not a probability';
  return value === null || value === undefined ? status : `${status} ${value}`;
}

export function normalizeDecision(value) {
  return ['ABSTAIN', 'REVIEW', 'PASS', 'FLAG'].includes(value) ? value : 'REVIEW';
}

export function evidenceLocator(evidence) {
  return [evidence.source, evidence.document, evidence.page ? `page ${evidence.page}` : null]
    .filter(Boolean)
    .join(' · ');
}

export async function safeApiJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}
