export function displayScore(score: number | null | undefined): string;
export function displayReliability(status: string, value: number | null | undefined): string;
export function normalizeDecision(value: string): 'ABSTAIN' | 'REVIEW' | 'PASS' | 'FLAG';
export function evidenceLocator(evidence: {source?: string; document?: string; page?: number | null}): string;
export function safeApiJson(response: Response): Promise<unknown>;
