// src/components/ErrorBoundary.tsx
import React, { Component, ErrorInfo, ReactNode } from 'react';

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
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
          <div className="max-w-2xl w-full">
            <div className="bg-card border border-border rounded-lg shadow-xl p-8">
              <div className="text-center mb-6">
                <div className="text-6xl mb-4">💥</div>
                <h1 className="text-3xl font-bold text-foreground mb-2">
                  Something went wrong
                </h1>
                <p className="text-muted-foreground">
                  The application encountered an unexpected error.
                </p>
              </div>

              {this.state.error && (
                <div className="mb-6">
                  <details className="bg-secondary/50 rounded-lg p-4">
                    <summary className="cursor-pointer font-semibold text-card-foreground mb-2">
                      Error Details
                    </summary>
                    <div className="space-y-2 text-sm">
                      <div>
                        <strong className="text-foreground">Message:</strong>
                        <pre className="mt-1 p-2 bg-background rounded text-xs overflow-x-auto">
                          {this.state.error.message}
                        </pre>
                      </div>
                      {this.state.error.stack && (
                        <div>
                          <strong className="text-foreground">Stack Trace:</strong>
                          <pre className="mt-1 p-2 bg-background rounded text-xs overflow-x-auto">
                            {this.state.error.stack}
                          </pre>
                        </div>
                      )}
                    </div>
                  </details>
                </div>
              )}

              <div className="flex gap-4 justify-center">
                <button
                  onClick={() => window.location.reload()}
                  className="px-6 py-3 bg-secondary hover:bg-secondary/80 text-secondary-foreground font-semibold rounded-lg transition"
                >
                  Reload Page
                </button>
                <button
                  onClick={this.handleReset}
                  className="px-6 py-3 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-lg transition"
                >
                  Go to Home
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}