import React, { Component, Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';
const App = lazy(() => import('./App.jsx'));

// ロード画面（Issue #24）: 白地に小さなインジケーターだけを置く。件数・容量・技術的な説明は表示しない。
// 支援技術には role="status" と視覚的に隠した「読み込み中」で状態を伝える。
// 低速時の目安として、CSS で数秒後にだけ小さな「読み込み中」を表示する（reduced-motion では即時表示）。
function LoadingScreen() {
  return (
    <main className="loading-screen" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="loading-text">読み込み中</span>
    </main>
  );
}

// 読み込み失敗（データ取得・モジュール読み込みの失敗）: 無限ローディングにせず、簡潔な文言と再試行を出す
class ErrorBoundary extends Component {
  state = { error: false };
  static getDerivedStateFromError() { return { error: true }; }
  render() {
    if (this.state.error) return (
      <main className="loading-screen" role="alert">
        <p className="loading-error">データを読み込めませんでした</p>
        <button type="button" className="btn" onClick={() => window.location.reload()}>再試行</button>
      </main>
    );
    return this.props.children;
  }
}
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary>
    <Suspense fallback={<LoadingScreen />}><App /></Suspense>
  </ErrorBoundary></React.StrictMode>,
);
