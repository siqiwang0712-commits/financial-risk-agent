"use client";

/**
 * Route-level error boundary.
 *
 * The workbench renders whatever the API returned, so a single unexpected field
 * on one response used to throw during render and unmount the whole tree: the
 * user saw a blank page with no way to recover and no indication of what broke.
 * Next.js only renders a boundary if one exists, so this file is the difference
 * between "a tab crashed" and "the app is down".
 *
 * The message is shown verbatim: it is the one lead a user can report, and it
 * comes from the browser, not from the server.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main>
      <h1>
        This view could not be <span>rendered</span>
      </h1>
      <p className="muted">
        The assessment data did not match what the interface expected, so the page
        stopped rendering rather than showing something misleading.
      </p>
      <div className="notice">
        <b>{error.name || "Error"}</b>
        <p>{error.message || "Unknown rendering error."}</p>
        {error.digest ? <p className="muted">digest: {error.digest}</p> : null}
      </div>
      <button type="button" onClick={() => reset()}>
        Try again
      </button>
    </main>
  );
}
