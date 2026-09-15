"use client";

/**
 * Last-resort boundary for failures in the root layout itself.
 *
 * `app/error.tsx` cannot catch an error thrown by `app/layout.tsx`, because the
 * boundary is rendered *inside* that layout. This file replaces the whole
 * document in that case. Styles are inlined deliberately: if the layout failed,
 * its stylesheet import may not have run either.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          padding: "28px",
          background: "#f5f1e8",
          color: "#13251f",
          fontFamily: "Inter, Arial, sans-serif",
          lineHeight: 1.55,
        }}
      >
        <div
          role="alert"
          style={{
            background: "#fff0eb",
            borderLeft: "4px solid #d45b3e",
            padding: "16px",
            maxWidth: "720px",
            fontSize: "14px",
          }}
        >
          <b>FinRisk-Agent could not start.</b>
          <p style={{ margin: "8px 0" }}>
            The application shell failed to load. The failure may have occurred
            during server or browser rendering; use the reference below to find
            the corresponding log entry.
          </p>
          <button type="button" onClick={() => reset()}>
            Retry
          </button>
          {error.digest ? (
            <p style={{ margin: "8px 0 0", color: "#59635f", fontSize: "12px" }}>
              Reference: {error.digest}
            </p>
          ) : null}
        </div>
      </body>
    </html>
  );
}
