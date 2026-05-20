// components/Sidebar.jsx
import { useState, useEffect, useRef } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useApi, apiFetch } from '../hooks/useApi';

// ── Couleurs par type de check ────────────────────────────────────────────
const CHECK_META = {
  A: { label: 'Check A', color: '#059669', bg: '#d1fae5', icon: 'fa-circle-check', cls: 'g' },
  C: { label: 'Check C', color: '#2563eb', bg: '#dbeafe', icon: 'fa-circle-check', cls: 'b' },
  D: { label: 'Check D', color: '#d97706', bg: '#fef3c7', icon: 'fa-circle-check', cls: 'or' },
};

function NavItem({ to, icon, children, badge, badgeCls = '' }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => `ni${isActive ? ' active' : ''}`}
    >
      <i className={`fas ${icon}`}></i>
      {children}
      {badge !== undefined && badge !== null && (
        <span className={`nb ${badgeCls}`}>{badge}</span>
      )}
    </NavLink>
  );
}

// ── Composant accordéon Checks A/C ────────────────────────────────────────
function ChecksAccordion() {
  const navigate = useNavigate();
  const [open, setOpen]         = useState(false);
  const [openType, setOpenType] = useState({}); // { A: true, C: false, D: false }
  const [grouped, setGrouped]   = useState(null); // { A: { 'TS-INP': [...checks] }, C: {...}, D: {...} }
  const [loading, setLoading]   = useState(false);
  const fetched = useRef(false);

  // Lazy-fetch au premier clic
  useEffect(() => {
    if (!open || fetched.current) return;
    fetched.current = true;
    setLoading(true);

    (async () => {
      const aircraftList = await apiFetch('/aircraft/');
      if (!aircraftList) { setLoading(false); return; }

      const active = aircraftList
        .filter(a => (a.doc_count || 0) > 0)
        .map(a => a.registration);

      const all = [];
      for (const reg of active) {
        const data = await apiFetch(`/aircraft/${reg}/checks`);
        if (data?.length) data.forEach(c => all.push({ ...c, aircraft: reg }));
      }

      // Dédupliquer sur es_reference
      const seen = {};
      const deduped = all.filter(c => {
        const key = (c.es_reference || '').toUpperCase().replace(/^ES/, '');
        if (!key || seen[key]) return false;
        seen[key] = true;
        return true;
      });

      // Grouper par type (A / C / D) puis par avion
      const result = { A: {}, C: {}, D: {} };
      for (const c of deduped) {
        const t = c.check_type?.match(/[ACD]/)?.[0];
        if (!t || !result[t]) continue;
        if (!result[t][c.aircraft]) result[t][c.aircraft] = [];
        result[t][c.aircraft].push(c);
      }

      setGrouped(result);
      // Ouvrir automatiquement les types qui ont des données
      const autoOpen = {};
      for (const t of ['A', 'C', 'D']) {
        if (Object.keys(result[t]).length > 0) autoOpen[t] = true;
      }
      setOpenType(autoOpen);
      setLoading(false);
    })();
  }, [open]);

  const totalChecks = grouped
    ? Object.values(grouped).reduce((sum, byAc) =>
        sum + Object.values(byAc).reduce((s2, arr) => s2 + arr.length, 0), 0)
    : null;

  return (
    <div>
      {/* ── Entrée principale ─────────────────────────────── */}
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
          {totalChecks !== null && (
            <span className="nb">{totalChecks}</span>
          )}
          <i
            className={`fas fa-chevron-${open ? 'down' : 'right'}`}
            style={{ fontSize: 9, color: 'var(--tx3)', transition: 'transform .2s' }}
          ></i>
        </div>
      </div>

      {/* ── Panneau accordéon ─────────────────────────────── */}
      {open && (
        <div style={{
          background: 'var(--bg)',
          borderLeft: '3px solid var(--bdr)',
          marginLeft: 12,
          marginBottom: 2,
          borderRadius: '0 0 6px 6px',
          overflow: 'hidden',
          animation: 'fadeIn .15s ease',
        }}>
          {loading && (
            <div style={{ padding: '10px 14px', fontSize: 11, color: 'var(--tx3)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <i className="fas fa-spinner fa-spin" style={{ fontSize: 10 }}></i>
              Chargement des checks...
            </div>
          )}

          {!loading && grouped && ['A', 'C', 'D'].map(type => {
            const meta    = CHECK_META[type];
            const byAc    = grouped[type];
            const hasData = Object.keys(byAc).length > 0;
            const isOpen  = openType[type];
            const totalByType = Object.values(byAc).reduce((s, arr) => s + arr.length, 0);

            return (
              <div key={type}>
                {/* ── Header du type (Check A / C / D) ── */}
                <div
                  onClick={() => setOpenType(p => ({ ...p, [type]: !p[type] }))}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    padding: '7px 12px',
                    cursor: 'pointer',
                    background: isOpen ? meta.bg : 'transparent',
                    borderTop: '1px solid var(--bdr)',
                    transition: 'background .15s',
                  }}
                >
                  <i
                    className={`fas fa-chevron-${isOpen ? 'down' : 'right'}`}
                    style={{ fontSize: 8, color: meta.color, width: 10, flexShrink: 0 }}
                  ></i>
                  <span style={{
                    fontSize: 11, fontWeight: 700,
                    color: meta.color,
                    letterSpacing: .3,
                    flex: 1,
                  }}>
                    {meta.label}
                  </span>
                  {hasData ? (
                    <span style={{
                      fontSize: 9, fontWeight: 700,
                      background: meta.bg, color: meta.color,
                      border: `1px solid ${meta.color}33`,
                      borderRadius: 10, padding: '1px 6px',
                    }}>
                      {totalByType}
                    </span>
                  ) : (
                    <span style={{ fontSize: 9, color: 'var(--tx3)' }}>—</span>
                  )}
                </div>

                {/* ── Avions + checks ── */}
                {isOpen && hasData && Object.entries(byAc).map(([reg, checks]) => (
                  <div key={reg}>
                    {/* Sous-titre avion */}
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '5px 12px 5px 28px',
                      background: 'var(--bg2)',
                      borderTop: '1px solid var(--bdr)',
                    }}>
                      <i className="fas fa-plane" style={{ fontSize: 9, color: 'var(--nv)' }}></i>
                      <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--nv)', letterSpacing: .5 }}>
                        {reg}
                      </span>
                      <span style={{ fontSize: 9, color: 'var(--tx3)', marginLeft: 'auto' }}>
                        {checks.length} check{checks.length > 1 ? 's' : ''}
                      </span>
                    </div>

                    {/* Liste des checks de cet avion */}
                    {checks.map((c, i) => (
                      <div
                        key={i}
                        onClick={() => navigate('/documents', {
                          state: { aircraft: reg, category: `Check ${type}` }
                        })}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 6,
                          padding: '6px 12px 6px 36px',
                          cursor: 'pointer',
                          borderTop: '1px solid rgba(208,221,232,.2)',
                          transition: 'background .1s',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = meta.bg}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        {/* Indicateur doc count */}
                        <div style={{
                          width: 5, height: 5, borderRadius: '50%',
                          background: meta.color, flexShrink: 0, opacity: .7,
                        }}></div>

                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{
                            fontSize: 10, fontWeight: 600,
                            color: 'var(--tx)',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {c.es_reference}
                          </div>
                          {c.start_date && (
                            <div style={{ fontSize: 9, color: 'var(--tx3)' }}>
                              {c.start_date.split('T')[0]}
                            </div>
                          )}
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, flexShrink: 0 }}>
                          <span style={{
                            fontSize: 9, fontWeight: 600,
                            color: meta.color,
                            background: meta.bg,
                            border: `1px solid ${meta.color}33`,
                            borderRadius: 8, padding: '0px 4px',
                          }}>
                            {c.total_documents || 0} docs
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}

                {isOpen && !hasData && (
                  <div style={{ padding: '8px 12px 8px 28px', fontSize: 10, color: 'var(--tx3)', fontStyle: 'italic' }}>
                    Aucun check {meta.label} trouvé
                  </div>
                )}
              </div>
            );
          })}

          {/* Lien vers la page complète */}
          {!loading && grouped && (
            <div
              onClick={() => navigate('/checks')}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '7px 12px',
                cursor: 'pointer',
                borderTop: '1px solid var(--bdr)',
                background: 'transparent',
                transition: 'background .1s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <i className="fas fa-external-link-alt" style={{ fontSize: 9, color: 'var(--tx3)' }}></i>
              <span style={{ fontSize: 10, color: 'var(--tx3)' }}>Voir tous les checks →</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sidebar principale ────────────────────────────────────────────────────
export default function Sidebar() {
  const { canAccess } = useAuth();
  const { data: kpis } = useApi('/analytics/kpis');

  const totalDocs     = kpis?.total_documents?.toLocaleString() ?? '—';
  const totalAircraft = kpis?.total_aircraft ?? '—';
  const activeAlerts  = kpis?.active_alerts  ?? '—';

  return (
    <aside id="sb">
      <div className="nsl">Navigation</div>
      <NavItem to="/dashboard" icon="fa-chart-bar">Tableau de Bord</NavItem>
      {canAccess('upload') && (
        <NavItem to="/upload" icon="fa-cloud-upload-alt">Upload Documents</NavItem>
      )}
      <NavItem to="/documents" icon="fa-folder-open" badge={totalDocs}>
        Consultation
      </NavItem>
      <NavItem to="/search" icon="fa-search-plus">Recherche Documentaire</NavItem>

      <div className="sdiv"></div>
      <div className="nsl">Flotte</div>
      <NavItem to="/fleet" icon="fa-plane" badge={totalAircraft}>Vue Flotte</NavItem>

      {/* ── Checks A/C avec accordéon ── */}
      <ChecksAccordion />

      <NavItem to="/recent-uploads" icon="fa-history">Documents Uploadés</NavItem>

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
        Pipeline Agents IA
        <span className="nb" style={{ background: '#2563eb', color: '#fff', marginLeft: 'auto' }}>Live</span>
      </NavLink>
      <NavItem to="/pipeline-demo" icon="fa-play-circle">
        Simulation Pipeline
      </NavItem>
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