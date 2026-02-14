// src/components/ErrorBoundary.tsx
import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Button } from './ui/Button';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({
      error,
      errorInfo,
    });
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-background px-4">
          {/* Background effects */}
          <div className="fixed inset-0 bg-grid opacity-20 pointer-events-none" />
          <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
          
          <div className="relative z-10 max-w-3xl w-full">
            <div className="glass rounded-2xl border-slate-200 dark:border-white/10 shadow-2xl p-8 md:p-12">
              <div className="text-center mb-8">
                <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-red-100 to-orange-100 dark:from-red-950/40 dark:to-orange-950/40 mb-6">
                  <span className="text-5xl">💥</span>
                </div>
                <h1 className="text-4xl font-bold mb-3">
                  <span className="text-gradient">Something went wrong</span>
                </h1>
                <p className="text-lg text-muted-foreground max-w-md mx-auto">
                  The application encountered an unexpected error. Don't worry, we've logged it.
                </p>
              </div>

              {this.state.error && (
                <div className="mb-8">
                  <details className="glass rounded-xl p-4 border-slate-200 dark:border-white/10">
                    <summary className="cursor-pointer font-semibold text-foreground mb-3 flex items-center gap-2 hover:text-blue-600 dark:hover:text-red-400 transition-colors">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Error Details
                    </summary>
                    <div className="space-y-3 text-sm">
                      <div>
                        <strong className="text-foreground block mb-2">Message:</strong>
                        <pre className="p-3 bg-slate-100 dark:bg-zinc-900 rounded-lg text-xs overflow-x-auto border border-slate-200 dark:border-white/10">
                          {this.state.error.message}
                        </pre>
                      </div>
                      {this.state.error.stack && (
                        <div>
                          <strong className="text-foreground block mb-2">Stack Trace:</strong>
                          <pre className="p-3 bg-slate-100 dark:bg-zinc-900 rounded-lg text-xs overflow-x-auto border border-slate-200 dark:border-white/10 max-h-64">
                            {this.state.error.stack}
                          </pre>
                        </div>
                      )}
                    </div>
                  </details>
                </div>
              )}

              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button
                  variant="secondary"
                  size="lg"
                  onClick={() => window.location.reload()}
                  className="gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Reload Page
                </Button>
                <Button
                  variant="primary"
                  size="lg"
                  onClick={this.handleReset}
                  className="gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                  </svg>
                  Go to Home
                </Button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}