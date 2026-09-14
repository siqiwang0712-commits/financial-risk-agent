export function displayScore(score: number | null | undefined): string;
export function displayRatio(value: number | null | undefined, decimals?: number): string;
export function displayReliability(status: string, value: number | null | undefined): string;
export function normalizeDecision(value: string): 'ABSTAIN' | 'REVIEW' | 'PASS' | 'FLAG';
export function evidenceLocator(evidence: {
  source?: string | null;
  document?: string | null;
  page?: number | null;
} | null | undefined): string;
export function safeApiJson(response: Response): Promise<unknown>;
