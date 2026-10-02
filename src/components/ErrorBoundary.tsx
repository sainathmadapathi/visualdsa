import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';

/**
 * Keeps one failure (a lazily loaded editor that cannot be fetched after a server restart,
 * or a rendering error) from unmounting the whole studio into a blank page.
 */
export default class ErrorBoundary extends Component<{ children: ReactNode; title: string; detail: string; full?: boolean }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(error, info.componentStack); }
  render() {
    if (!this.state.failed) return this.props.children;
    // A failed module import is cached by the browser, so a reload is the reliable retry.
    return <div className={`load-failure ${this.props.full ? 'load-failure-full' : ''}`} role="alert">
      <strong>{this.props.title}</strong><p>{this.props.detail}</p>
      <button className="outline-button" onClick={() => window.location.reload()}><RotateCcw size={14}/> Reload</button>
    </div>;
  }
}
