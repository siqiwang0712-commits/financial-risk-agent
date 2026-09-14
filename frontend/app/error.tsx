"use client";

import { useEffect } from "react";

/**
 * Route-level error boundary.
 *
 * Without this file a throw anywhere in the page tree unmounted the whole app
 * and the user saw a blank document with no explanation. The boundary keeps the
 * failure local: the shell (header, nav) stays, the panel explains what
 * happened, and the user can retry without a full reload.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surfaces in the browser console and in the hosting provider's log
    // pipeline. The digest is the server-side correlation id, not the message,
    // so no upstream detail is leaked into the UI.
    console.error("FinRisk-Agent render failed", error);
  }, [error]);

  return (
    <main>
      <div className="notice" role="alert">
        <b>This panel could not be rendered.</b>
        <p>
          A rendering error was caught before it could blank the page. The
          underlying assessment is unaffected — retry to re-render, or reload to
          start a fresh request.
        </p>
        <div className="intakeActions">
          <button type="button" onClick={() => reset()}>
            Retry
          </button>
          <a className="footnote" href="/">
            Reload the workbench
          </a>
        </div>
        {error.digest ? (
          <p className="mono muted footnote">Reference: {error.digest}</p>
        ) : null}
      </div>
    </main>
  );
}
