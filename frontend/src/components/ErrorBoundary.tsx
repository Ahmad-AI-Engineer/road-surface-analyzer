import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Last-resort safety net for a live demo: if any component throws during
 * render, show a recoverable screen instead of a blank white page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('Unhandled UI error', error, info.componentStack);
  }

  private reset = () => {
    this.setState({ error: null });
    window.location.assign('/');
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-ink-900 px-6 text-center text-slate-100">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="max-w-md text-sm text-slate-400">
          The interface hit an unexpected error. Your data and processing jobs
          are unaffected — try returning to the home page.
        </p>
        <button
          type="button"
          onClick={this.reset}
          className="btn-primary"
        >
          Back to home
        </button>
      </div>
    );
  }
}
