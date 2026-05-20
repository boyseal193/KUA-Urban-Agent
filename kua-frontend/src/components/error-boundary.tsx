"use client";

import * as React from "react";
import Link from "next/link";
import { AlertOctagon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: (props: { error: Error; reset: () => void }) => React.ReactNode;
}

/**
 * Class-based ErrorBoundary because React 19 still has no hooks-only API
 * for catching render errors. Use sparingly — only wrap surfaces that
 * actually render data that may be malformed.
 */
export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    if (typeof window !== "undefined") {
      console.error("[ErrorBoundary]", error, info.componentStack);
    }
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback({
          error: this.state.error,
          reset: this.reset,
        });
      }
      return <DefaultFallback error={this.state.error} reset={this.reset} />;
    }
    return this.props.children;
  }
}

export function DefaultFallback({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="panel-strong relative z-10 mx-auto my-10 max-w-xl p-10 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-destructive/40 bg-destructive/10">
        <AlertOctagon className="h-5 w-5 text-destructive" />
      </div>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-destructive">
        COMPONENT FAULT
      </p>
      <h1 className="mt-2 font-display text-2xl font-semibold tracking-tight">
        Render error contained
      </h1>
      <p className="mt-2 break-words text-sm text-muted-foreground">
        {error.message || "An unexpected error occurred."}
      </p>
      <div className="mt-6 flex items-center justify-center gap-2">
        <Button variant="default" onClick={reset}>
          Retry component
        </Button>
        <Link href="/dashboard">
          <Button variant="ghost">Return to Command</Button>
        </Link>
      </div>
    </div>
  );
}
