"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Local error boundary for a single panel.
 *
 * `app/error.tsx` catches a failure for the whole route, which replaces the page
 * with an error notice. That is too coarse here: the workbench renders six
 * independent panels from one payload, and a missing field in any one of them
 * used to take the entire page down. This boundary keeps the failure inside the
 * panel, so the rest of the assessment stays readable.
 */
export class PanelBoundary extends Component<
  { children: ReactNode; label: string },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`FinRisk-Agent panel failed: ${this.props.label}`, error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="panel" role="alert">
        <p className="muted">
          The <b>{this.props.label}</b> panel could not be rendered from this
          response. The remaining panels and the decision summary are unaffected.
        </p>
      </section>
    );
  }
}
