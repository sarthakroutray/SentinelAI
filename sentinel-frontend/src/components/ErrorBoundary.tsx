"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  /** Optional section label displayed in the error card. */
  section?: string;
}

interface State {
  hasError: boolean;
  message: string | null;
}

/**
 * React class-based error boundary.
 * Catches rendering exceptions within a subtree and shows an isolated
 * error card instead of crashing the entire dashboard.
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: null };
  }

  static getDerivedStateFromError(error: unknown): State {
    const message =
      error instanceof Error ? error.message : "An unexpected error occurred.";
    return { hasError: true, message };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error(
      `[ErrorBoundary${this.props.section ? ` – ${this.props.section}` : ""}]`,
      error,
      info.componentStack,
    );
  }

  handleRetry = () => {
    this.setState({ hasError: false, message: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <p className="font-medium">
            {this.props.section
              ? `${this.props.section} failed to render`
              : "A section failed to render"}
          </p>
          {this.state.message && (
            <p className="mt-1 font-mono text-xs opacity-70">
              {this.state.message}
            </p>
          )}
          <button
            type="button"
            onClick={this.handleRetry}
            className="mt-2 rounded border border-red-500/40 px-2 py-1 text-xs transition-colors hover:bg-red-500/20"
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
