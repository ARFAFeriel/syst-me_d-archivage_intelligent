// components/Sidebar.jsx
import { useState, useEffect, useRef } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useApi, apiFetch } from '../hooks/useApi';

const CHECK_META = {
  A: { label: 'Check A', color: '#059669', bg: '#d1fae5', icon: 'fa-circle-check', cls: 'g' },
  C: { label: 'Check C', color: '#2563eb', bg: '#dbeafe', icon: 'fa-circle-check', cls: 'b' },
  D: { label: 'Check D', color: '#d97706', bg: '#fef3c7', icon: 'fa-circle-check', cls: 'or' },
};

function NavItem({ to, icon, children, badge, badgeCls = '' }) {
  return (
    <NavLink to={to} className={({ isActive }) => `ni${isActive ? ' active' : ''}`}>
      <i className={`fas ${icon}`}></i>
      {children}
      {badge !== undefined && badge !== null && (
        <span className={`nb ${badgeCls}`}>{badge}</span>
      )}
    </NavLink>
  );
}

// Checks accordion - affiche uniquement le total de docs par type
function ChecksAccordion() {
  const navigate = useNavigate();
  const [open, setOpen]       = useState(false);
  const [grouped, setGrouped] = useState(null);
  const [loading, setLoading] = useState(false);
  const fetched = useRef(false);

  useEffect(() => {
    if (!open || fetched.current) return;
    fetched.current = true;
    setLoading(true);

    (async () => {
      try {
        const data = await apiFetch('/aircraft/checks/all');
        const checks = data || [];

        // Grouper par type de check : { A: { totalChecks, totalDocs }, C: {...}, D: {...} }
        const result = {
          A: { totalChecks: 0, totalDocs: 0 },
          C: { totalChecks: 0, totalDocs: 0 },
          D: { totalChecks: 0, totalDocs: 0 },
        };

        for (const c of checks) {
          const t = c.check_type?.match(/[ACD]/)?.[0];
          if (!t || !result[t]) continue;
          result[t].totalChecks += 1;
          result[t].totalDocs += c.total_documents || 0;
        }

        setGrouped(result);
      } catch {
        // silencieux
      }
      setLoading(false);
    })();
  }, [open]);

  const totalChecks = grouped
    ? Object.values(grouped).reduce((sum, v) => sum + v.totalChecks, 0)
    : null;

  return (
    <div>
      <div
        className={`ni${open ? ' active' : ''}`}
        style={{ cursor: 'pointer', userSelect: 'none', justifyContent: 'space-between' }}
        onClick={() => setOpen(o => !o)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
          <i className="fas fa-clipboard-check"></i>
          <span>Checks A/C</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          {totalChecks !== null && <span className="nb">{totalChecks}</span>}
          <i className={`fas fa-chevron-${open ? 'down' : 'right'}`}
            style={{ fontSize: 9, color: 'var(--tx3)', transition: 'transform .2s' }}></i>
        </div>
      </div>

      {open && (
        <div style={{
          background: 'var(--bg)',
          borderLeft: '3px solid var(--bdr)',
          marginLeft: 12,
          marginBottom: 2,
          borderRadius: '0 0 6px 6px',
          overflow: 'hidden',
        }}>
          {loading && (
            <div style={{ padding: '10px 14px', fontSize: 11, color: 'var(--tx3)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <i className="fas fa-spinner fa-spin" style={{ fontSize: 10 }}></i>
              Chargement...
            </div>
          )}

          {!loading && grouped && ['A', 'C', 'D'].map(type => {
            const meta = CHECK_META[type];
            const info = grouped[type];
            const hasData = info.totalChecks > 0;

            return (
              <div
                key={type}
                onClick={() => navigate('/checks', { state: { checkType: type } })}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 12px',
                  cursor: 'pointer',
                  borderTop: 'none',
                  transition: 'background .15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = meta.bg}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                {/* Indicateur couleur */}
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: meta.color, flexShrink: 0,
                }}></div>

                {/* Label */}
                <span style={{
                  fontSize: 11, fontWeight: 700,
                  color: meta.color, flex: 1,
                }}>
                  {meta.label}
                </span>

                {/* Stats */}
                
              </div>
            );
          })}

          {/* Lien vers page complète */}
          {!loading && grouped && (
            <div
              onClick={() => navigate('/checks')}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '7px 12px',
                cursor: 'pointer',
                borderTop: 'none',
                transition: 'background .1s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <i className="fas fa-external-link-alt" style={{ fontSize: 9, color: 'var(--tx3)' }}></i>
              <span style={{ fontSize: 10, color: 'var(--tx3)' }}>
  Voir tous les checks · {Object.values(grouped).reduce((s, v) => s + v.totalDocs, 0).toLocaleString()} docs
</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Sidebar principale
export default function Sidebar() {
  const { canAccess } = useAuth();
  const { data: kpis } = useApi('/analytics/kpis');

  const totalDocs     = kpis?.total_documents?.toLocaleString() ?? '--';
  const totalAircraft = kpis?.total_aircraft ?? '--';
  const activeAlerts  = kpis?.active_alerts  ?? '--';

  return (
    <aside id="sb">
      <div className="nsl">Navigation</div>
      <NavItem to="/dashboard" icon="fa-chart-bar">Tableau de Bord</NavItem>
      {canAccess('upload') && (
        <NavItem to="/upload" icon="fa-cloud-upload-alt">Upload Documents</NavItem>
      )}
      <NavItem to="/analyse-documents" icon="fa-robot">
        Analyse Documents
      </NavItem>
      <NavItem to="/documents" icon="fa-folder-open" badge={totalDocs}>
        Consultation
      </NavItem>
      <NavItem to="/search" icon="fa-search-plus">Recherche Documentaire</NavItem>

      <div className="sdiv"></div>
      <div className="nsl">Flotte</div>
      <NavItem to="/fleet" icon="fa-plane">Vue Flotte</NavItem>

      <ChecksAccordion />

      <NavItem to="/recent-uploads" icon="fa-history">Documents Uploades</NavItem>

      <div className="sdiv"></div>
      <div className="nsl">Intelligence</div>
      <NavLink
        to="/pipeline"
        className={({ isActive }) => `ni${isActive ? ' active' : ''}`}
        style={({ isActive }) => ({
          background: isActive
            ? 'linear-gradient(135deg, #e4ecff, #d6e4ff)'
            : 'linear-gradient(135deg, #f0f4ff, #e8eeff)',
          color: '#1e3a8a',
          borderLeftColor: isActive ? '#1e3a8a' : 'transparent',
          fontWeight: isActive ? 600 : 500,
        })}
      >
        <i className="fas fa-project-diagram"></i>
        Pipeline & Modéles IA
        <span className="nb" style={{ background: '#2563eb', color: '#fff', marginLeft: 'auto' }}>Live</span>
      </NavLink>
      <NavItem to="/pipeline-demo" icon="fa-play-circle">Simulation Pipeline</NavItem>
      {canAccess('monitoring') && (
        <NavItem to="/monitoring" icon="fa-shield-alt" badge={activeAlerts} badgeCls="r">
          Monitoring
        </NavItem>
      )}
      {canAccess('analytics') && (
        <NavItem to="/analytics" icon="fa-chart-line">Analytics</NavItem>
      )}

      <div className="sdiv"></div>
      <div className="nsl">Administration</div>
      {canAccess('admin') && (
        <NavItem to="/admin" icon="fa-users-cog" badge="Admin" badgeCls="g">
          Gestion Sessions
        </NavItem>
      )}
    </aside>
  );
}