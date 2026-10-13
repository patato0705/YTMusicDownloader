// src/components/ErrorBoundary.tsx
import { Component, ErrorInfo, ReactNode } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { PageBackground } from './layout/PageBackground';
import { Button } from './ui/Button';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** What replaces the app when it crashes while rendering */
function ErrorScreen({ error }: { error: Error }): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <PageBackground />

      <div className="relative max-w-3xl w-full glass rounded-2xl shadow-2xl p-8 md:p-12">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-red-100 to-orange-100 dark:from-red-950/40 dark:to-orange-950/40 mb-6">
            <span className="text-5xl" aria-hidden="true">💥</span>
          </div>
          <h1 className="text-4xl font-bold mb-3">
            <span className="text-gradient">{t('errorBoundary.title')}</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-md mx-auto">
            {t('errorBoundary.description')}
          </p>
        </div>

        <details className="glass rounded-xl p-4 mb-8">
          <summary className="cursor-pointer font-semibold text-foreground mb-3 hover:text-blue-600 dark:hover:text-red-400 transition-colors">
            {t('errorBoundary.details')}
          </summary>
          <p className="font-mono text-sm text-foreground break-words mb-3">{error.message}</p>
          {error.stack && (
            <pre className="p-3 bg-slate-100 dark:bg-zinc-900 rounded-lg text-xs overflow-x-auto max-h-64 border border-slate-200 dark:border-white/10">
              {error.stack}
            </pre>
          )}
        </details>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Button variant="secondary" size="lg" onClick={() => window.location.reload()}>
            {t('errorBoundary.reload')}
          </Button>
          <Button variant="primary" size="lg" onClick={() => window.location.assign('/')}>
            {t('errorBoundary.home')}
          </Button>
        </div>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    return this.state.error ? <ErrorScreen error={this.state.error} /> : this.props.children;
  }
}
