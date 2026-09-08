import React, { Component, Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';
const App = lazy(() => import('./App.jsx'));
class ErrorBoundary extends Component {
  state = { error: false };
  static getDerivedStateFromError() { return { error: true }; }
  render() {
    if (this.state.error) return (
      <main className="loading-screen" role="alert">
        <span className="brand-kicker">JP MARKET VIS</span>
        <h1>データを読み込めませんでした</h1>
        <p>通信状況を確認して、もう一度お試しください。</p>
        <button onClick={() => window.location.reload()}>再読み込み</button>
      </main>
    );
    return this.props.children;
  }
}
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary>
    <Suspense fallback={<main className="loading-screen" role="status">
      <span className="brand-kicker">JP MARKET VIS</span>
      <h1>日本の企業のつながりを、ひとつの地図に。</h1>
      <p>企業・関係データを読み込んでいます。初回は約34MBのデータを取得します。</p>
      <div className="loading-line" />
    </main>}><App /></Suspense>
  </ErrorBoundary></React.StrictMode>,
);
