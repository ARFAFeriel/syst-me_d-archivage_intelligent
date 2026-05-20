// App.jsx — Routeur principal
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect, useState, useCallback } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ToastProvider, useToast } from './contexts/ToastContext';
import { useApi } from './hooks/useApi';
import { useDocumentWatcher } from './hooks/useDocumentWatcher';

import Header from './components/Header';
import Sidebar from './components/Sidebar';
import NewDocumentBanner from './components/NewDocumentBanner';

import Login         from './pages/Login';
import Dashboard     from './pages/Dashboard';
import Upload        from './pages/Upload';
import Documents     from './pages/Documents';
import Search        from './pages/Search';
import Fleet         from './pages/Fleet';
import Checks        from './pages/Checks';
import RecentUploads from './pages/RecentUploads';
import Pipeline      from './pages/Pipeline';
import PipelineDemo  from './pages/PipelineDemo';
import Monitoring    from './pages/Monitoring';
import Analytics     from './pages/Analytics';
import Admin         from './pages/Admin';

import './styles/global.css';

// ── Layout protégé (Header + Sidebar + contenu) ──
function Layout({ children }) {
  const { data: pipelineStatus } = useApi('/pipeline/status');
  const { data: kpis }           = useApi('/analytics/kpis');
  return (
    <>
      <Header alertCount={kpis?.active_alerts || 0} />
      <Sidebar agentStatus={pipelineStatus} />
      <main id="main">{children}</main>
    </>
  );
}

// ── Guard de route ──
function Protected({ children, droit }) {
  const { session, canAccess } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  if (droit && !canAccess(droit)) return <Navigate to="/dashboard" replace />;
  return children;
}

// ── Watcher WebSocket — surveille les nouveaux documents ──
// ── Watcher WebSocket — surveille les nouveaux documents ──
function DocumentWatcher() {
  const [newDoc, setNewDoc] = useState(null);
  const toast = useToast(); // ✅ toast est directement la fonction

  const handleNewDocument = useCallback((data) => {
    // Afficher la bannière
    setNewDoc(data);

    // ✅ Appel correct selon ton ToastContext
    toast(
      `📄 Nouveau document archivé : ${data.filename}`,
      'ok'
    );

    // Masquer la bannière après 6 secondes
    setTimeout(() => setNewDoc(null), 6000);

  }, [toast]);

  useDocumentWatcher(handleNewDocument);

  return (
    <NewDocumentBanner
      doc={newDoc}
      onClose={() => setNewDoc(null)}
    />
  );
}

// ── App ──
function AppRoutes() {
  const { session } = useAuth();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 1000);
    return () => clearTimeout(t);
  }, []);

  if (loading) {
    return (
      <div id="loader">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 8 }}>
          <div style={{ width: 48, height: 48, background: 'rgba(255,255,255,.15)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <i className="fas fa-plane-departure" style={{ color: '#fff', fontSize: 22 }}></i>
          </div>
          <div>
            <div style={{ color: '#fff', fontFamily: "'Barlow Condensed',sans-serif", fontSize: 22, fontWeight: 700, letterSpacing: 2 }}>Système d'archivage intelligent</div>
            <div style={{ color: 'rgba(255,255,255,.5)', fontSize: 10, letterSpacing: 2, textTransform: 'uppercase' }}>NouvelAir MRO</div>
          </div>
        </div>
        <div className="spin"></div>
        <p style={{ color: 'rgba(255,255,255,.7)', fontSize: 14, letterSpacing: 1 }}>Initialisation du système...</p>
      </div>
    );
  }

  return (
    <BrowserRouter>
      {/* ✅ Bannière temps réel — active sur toutes les pages */}
      {session && <DocumentWatcher />}

      <Routes>
        <Route path="/login" element={session ? <Navigate to="/dashboard" replace /> : <Login />} />

        <Route path="/dashboard"      element={<Protected><Layout><Dashboard /></Layout></Protected>} />
        <Route path="/upload"         element={<Protected droit="upload"><Layout><Upload /></Layout></Protected>} />
        <Route path="/documents"      element={<Protected><Layout><Documents /></Layout></Protected>} />
        <Route path="/search"         element={<Protected><Layout><Search /></Layout></Protected>} />
        <Route path="/fleet"          element={<Protected><Layout><Fleet /></Layout></Protected>} />
        <Route path="/checks"         element={<Protected><Layout><Checks /></Layout></Protected>} />
        <Route path="/recent-uploads" element={<Protected><Layout><RecentUploads /></Layout></Protected>} />
        <Route path="/pipeline"       element={<Protected><Layout><Pipeline /></Layout></Protected>} />
        <Route path="/pipeline-demo"  element={<Protected><Layout><PipelineDemo /></Layout></Protected>} />
        <Route path="/monitoring"     element={<Protected droit="monitoring"><Layout><Monitoring /></Layout></Protected>} />
        <Route path="/analytics"      element={<Protected droit="analytics"><Layout><Analytics /></Layout></Protected>} />
        <Route path="/admin"          element={<Protected droit="admin"><Layout><Admin /></Layout></Protected>} />

        <Route path="*" element={<Navigate to={session ? "/dashboard" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </AuthProvider>
  );
}