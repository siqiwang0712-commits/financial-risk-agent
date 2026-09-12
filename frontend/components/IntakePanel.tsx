"use client";

import { FormEvent, useState } from "react";
import type { AnalyzeInput } from "../lib/api";

interface Props {
  busy: boolean;
  error: string | null;
  errorIsUpstream: boolean;
  onAnalyze: (input: AnalyzeInput) => void;
  onLoadSample: () => void;
  onDismissError: () => void;
}

/**
 * Two ways in, and the second one never fails:
 *
 *  - upload a filing and run the Agent against the live API (needs a tenant key)
 *  - load the bundled sample, which is a real pipeline output kept in the repo
 *
 * The sample path exists so a reviewer can see the whole Workbench without
 * running the backend, and so a demo never opens on an empty shell.
 */
export function IntakePanel({
  busy,
  error,
  errorIsUpstream,
  onAnalyze,
  onLoadSample,
  onDismissError,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [company, setCompany] = useState("");
  const [year, setYear] = useState(new Date().getFullYear() - 1);
  const [apiKey, setApiKey] = useState("");

  const ready = Boolean(file) && Boolean(company) && Boolean(apiKey) && !busy;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !ready) return;
    onAnalyze({ file, company, fiscalYear: year, apiKey });
  }

  return (
    <section className="panel intakePanel">
      <div className="panelHeading">
        <div>
          <p className="kicker">Supplemental evidence intake</p>
          <h2>Every material conclusion has a path back to evidence.</h2>
        </div>
      </div>

      <div className="intakeBody">
        <form onSubmit={submit} className="intakeForm">
          <label className="field">
            <span>Tenant API key</span>
            <input
              type="password"
              autoComplete="off"
              placeholder="X-API-Key"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              required
            />
          </label>

          <label className="field">
            <span>Company</span>
            <input
              placeholder="Legal issuer name"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              required
            />
          </label>

          <label className="field">
            <span>Fiscal year</span>
            <input
              type="number"
              min={1900}
              max={2100}
              value={year}
              onChange={(event) => setYear(Number(event.target.value))}
              required
            />
          </label>

          <label className="upload">
            <input
              type="file"
              accept="application/pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <b>{file ? file.name : "Choose an annual report"}</b>
            <small>PDF · validated magic bytes · size, page and text limits enforced</small>
          </label>

          <div className="intakeActions">
            <button type="submit" disabled={!ready}>
              {busy ? "Agent is analysing…" : "Run Agent analysis"}
            </button>
            <button type="button" className="ghost" onClick={onLoadSample} disabled={busy}>
              Load bundled sample
            </button>
          </div>

          <p className="intakeHint">
            The bundled sample is a real pipeline output for the repository&apos;s synthetic fixture.
            It needs no backend and is labelled as a sample everywhere it appears.
          </p>
        </form>

        <aside className="intakeAside">
          <h3>What the Agent will do</h3>
          <ol>
            <li>Normalise the filing and compute ratios and trends deterministically.</li>
            <li>Run the four traditional models behind explicit applicability checks.</li>
            <li>Evaluate the versioned rule set against the full fact set.</li>
            <li>Extract narrative claims and verify each quote against its cited page.</li>
            <li>Cross-check narrative against numeric evidence, then fuse and verify.</li>
          </ol>
          <p className="asideFoot">
            The language model only ever proposes text. It cannot compute a ratio, a score or a
            probability.
          </p>
        </aside>
      </div>

      {error ? (
        <div className="alert" role="alert">
          <b>Analysis could not be completed</b>
          <p>{error}</p>
          {errorIsUpstream ? (
            <p className="alertAction">
              <button type="button" className="ghost" onClick={onLoadSample}>
                Show the bundled sample instead
              </button>
            </p>
          ) : null}
          <button type="button" className="dismiss" onClick={onDismissError} aria-label="Dismiss">
            ×
          </button>
        </div>
      ) : null}
    </section>
  );
}
