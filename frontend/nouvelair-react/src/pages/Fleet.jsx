// pages/Fleet.jsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../hooks/useApi';

// ── Données statiques flotte NouvelAir (18 aéronefs confirmés) ─────────────
const FLEET_DATA = [
  { reg: 'TS-INB', msn: '3312',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INC', msn: '1744',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-IND', msn: '5016',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INE', msn: '5310',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INF', msn: '5867',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-ING', msn: '5878',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INH', msn: '4623',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INI', msn: '3508',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INJ', msn: '13178', type: 'NEO', variant: 'A320-251N', engine: 'CFM LEAP-1A26' },
  { reg: 'TS-INK', msn: '4564',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INL', msn: '12280', type: 'NEO', variant: 'A320-251N', engine: 'CFM LEAP-1A26' },
  { reg: 'TS-INM', msn: '12308', type: 'NEO', variant: 'A320-251N', engine: 'CFM LEAP-1A26' },
  { reg: 'TS-INO', msn: '6285',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INP', msn: '1597',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INQ', msn: '2158',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INR', msn: '3487',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INT', msn: '3798',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
  { reg: 'TS-INU', msn: '3827',  type: 'CEO', variant: 'A320-214',  engine: 'CFM56-5B4'    },
];

// ── Silhouette A320 top-view (SVG inline) ───────────────────────────────────
function PlaneIcon({ neo }) {
  const wing   = neo ? '#059669' : '#2563eb';
  const body   = neo ? '#064e3b' : '#1e3a8a';
  const engine = neo ? '#047857' : '#1d4ed8';
  return (
    <svg viewBox="0 0 56 56" fill="none" style={{ width: 40, height: 40, flexShrink: 0 }}>
      {/* fuselage */}
      <ellipse cx="28" cy="28" rx="3.5" ry="20" fill={body} opacity=".9" />
      {/* wings */}
      <path d="M28 30 L4 40 L7 42 L28 34 L49 42 L52 40 Z" fill={wing} opacity=".8" />
      {/* winglets NEO */}
      {neo && (
        <>
          <rect x="3"  y="39" width="3" height="5" rx="1" fill={wing} transform="rotate(-12 4 41)" />
          <rect x="50" y="39" width="3" height="5" rx="1" fill={wing} transform="rotate(12 52 41)" />
        </>
      )}
      {/* horizontal stabilizers */}
      <path d="M28 48 L19 53 L21 54 L28 50 L35 54 L37 53 Z" fill={wing} opacity=".65" />
      {/* engines */}
      <ellipse cx="13" cy="35" rx="3" ry="1.8" fill={engine} opacity=".9" />
      <ellipse cx="43" cy="35" rx="3" ry="1.8" fill={engine} opacity=".9" />
      {/* cockpit glare */}
      <ellipse cx="28" cy="9"  rx="2.5" ry="1.5" fill="#bfdbfe" opacity=".4" />
    </svg>
  );
}

// ── Carte aéronef ─────────────────────────────────────────────────────────
function AircraftCard({ ac, docCount, checkCount, selected, onSelect }) {
  const navigate = useNavigate();
  const neo      = ac.type === 'NEO';
  const accent   = neo ? '#059669' : '#2563eb';
  const accentBg = neo ? '#d1fae5' : '#dbeafe';
  const isActive = (docCount ?? 0) > 0;

  return (
    <div
      onClick={() => onSelect(selected ? null : ac.reg)}
      style={{
        background: selected ? accentBg : '#ffffff',
        border: `1.5px solid ${selected ? accent : 'var(--bdr)'}`,
        borderRadius: 12,
        padding: '14px 16px',
        cursor: 'pointer',
        transition: 'all .18s',
        position: 'relative',
        overflow: 'hidden',
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.borderColor = accent + '88'; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.borderColor = 'var(--bdr)'; }}
    >
      {/* Badge NEO */}
      {neo && (
        <span style={{
          position: 'absolute', top: 0, right: 0,
          background: '#059669', color: '#fff',
          fontSize: 9, fontWeight: 700, letterSpacing: '.08em',
          padding: '3px 10px 3px 12px',
          borderRadius: '0 12px 0 12px',
        }}>NEO</span>
      )}

      {/* Ligne principale */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <PlaneIcon neo={neo} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 15, fontWeight: 700,
            color: selected ? accent : 'var(--tx)',
            letterSpacing: '.04em',
          }}>{ac.reg}</div>
          <div style={{ fontSize: 10, color: 'var(--tx3)', marginTop: 1 }}>{ac.variant}</div>
        </div>
        {/* Indicateur actif */}
        <div style={{
          width: 7, height: 7, borderRadius: '50%',
          background: isActive ? '#059669' : '#d1d5db',
          boxShadow: isActive ? '0 0 6px #05966966' : 'none',
          flexShrink: 0,
        }} title={isActive ? 'Documents archivés' : 'Aucun document'} />
      </div>

      {/* MSN pill */}
      <div style={{
        background: 'var(--bg)',
        border: '1px solid var(--bdr)',
        borderRadius: 7,
        padding: '5px 10px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 8,
      }}>
        <span style={{ fontSize: 10, color: 'var(--tx3)', letterSpacing: '.06em' }}>MSN</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: accent, letterSpacing: '.04em' }}>
          {ac.msn}
        </span>
      </div>

      {/* Stats inline */}
      <div style={{ display: 'flex', gap: 6 }}>
        <span style={{
          flex: 1, textAlign: 'center', fontSize: 10,
          background: docCount ? accentBg : 'var(--bg)',
          color: docCount ? accent : 'var(--tx3)',
          border: `1px solid ${docCount ? accent + '33' : 'var(--bdr)'}`,
          borderRadius: 6, padding: '3px 0',
        }}>
          <i className="fas fa-file-alt" style={{ marginRight: 4 }} />
          {docCount ?? '—'} docs
        </span>
        <span style={{
          flex: 1, textAlign: 'center', fontSize: 10,
          background: checkCount ? '#fef3c7' : 'var(--bg)',
          color: checkCount ? '#d97706' : 'var(--tx3)',
          border: `1px solid ${checkCount ? '#d9770633' : 'var(--bdr)'}`,
          borderRadius: 6, padding: '3px 0',
        }}>
          <i className="fas fa-clipboard-check" style={{ marginRight: 4 }} />
          {checkCount ?? '—'} checks
        </span>
      </div>

      {/* Détail expandable */}
      {selected && (
        <div style={{
          marginTop: 12, paddingTop: 12,
          borderTop: `1px solid ${accent}33`,
          animation: 'fadeIn .15s ease',
        }}>
          {[
            ['Immatriculation', ac.reg],
            ['MSN',             ac.msn],
            ['Modèle',          ac.variant],
            ['Motorisation',    ac.engine],
            ['Génération',      ac.type],
            ['Opérateur',       'NouvelAir Tunisie'],
            ['Autorité',        'DGAC Tunisie / EASA'],
          ].map(([k, v]) => (
            <div key={k} style={{
              display: 'flex', justifyContent: 'space-between',
              fontSize: 11, padding: '4px 0',
              borderBottom: '1px solid var(--bdr)',
            }}>
              <span style={{ color: 'var(--tx3)' }}>{k}</span>
              <span style={{ color: accent, fontWeight: 600 }}>{v}</span>
            </div>
          ))}

          <div style={{ display: 'flex', gap: 7, marginTop: 10 }}>
            <button
              onClick={e => {
                e.stopPropagation();
                navigate('/documents', { state: { aircraft: ac.reg } });
              }}
              style={{
                flex: 1, padding: '7px 0',
                background: accentBg,
                border: `1px solid ${accent}`,
                borderRadius: 7, color: accent,
                fontSize: 11, cursor: 'pointer', fontWeight: 600,
              }}
            >
              <i className="fas fa-folder-open" style={{ marginRight: 5 }} />
              Documents
            </button>
            <button
              onClick={e => {
                e.stopPropagation();
                navigate('/checks', { state: { aircraft: ac.reg } });
              }}
              style={{
                flex: 1, padding: '7px 0',
                background: 'var(--bg)',
                border: '1px solid var(--bdr)',
                borderRadius: 7, color: 'var(--tx2)',
                fontSize: 11, cursor: 'pointer', fontWeight: 500,
              }}
            >
              <i className="fas fa-clipboard-check" style={{ marginRight: 5 }} />
              Checks
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page principale ────────────────────────────────────────────────────────
export default function Fleet() {
  const [filter,    setFilter]    = useState('ALL');
  const [selected,  setSelected]  = useState(null);
  const [docCounts, setDocCounts] = useState({});   // { 'TS-INP': 862, ... }
  const [checkCounts, setCheckCounts] = useState({}); // { 'TS-INP': 2, ... }
  const [loading,   setLoading]   = useState(true);

  // ── Fetch doc counts + check counts depuis l'API ─────────────────────────
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        // 1. Récupérer la liste des avions (avec doc_count si dispo)
        const aircraftList = await apiFetch('/aircraft/');
        if (aircraftList) {
          const dc = {};
          const cc = {};
          for (const a of aircraftList) {
            if (a.doc_count   !== undefined) dc[a.registration] = a.doc_count;
            if (a.check_count !== undefined) cc[a.registration] = a.check_count;
          }
          setDocCounts(dc);
          setCheckCounts(cc);
        }
      } catch {
        // API indisponible — on affiche quand même la flotte statique
      }
      setLoading(false);
    })();
  }, []);

  const filtered = filter === 'ALL'
    ? FLEET_DATA
    : FLEET_DATA.filter(a => a.type === filter);

  const neoCount = FLEET_DATA.filter(a => a.type === 'NEO').length;
  const ceoCount = FLEET_DATA.filter(a => a.type === 'CEO').length;
  const totalDocs = Object.values(docCounts).reduce((s, n) => s + n, 0);
  const withDocs  = FLEET_DATA.filter(a => (docCounts[a.reg] ?? 0) > 0).length;

  return (
    <div className="page-content" style={{ padding: '24px 28px' }}>

      {/* ── En-tête ───────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 22, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--tx)', marginBottom: 4 }}>
            <i className="fas fa-plane" style={{ marginRight: 10, color: 'var(--nv)' }} />
            Vue Flotte NouvelAir
          </h1>
          <p style={{ fontSize: 12, color: 'var(--tx3)' }}>
            Flotte Airbus A320 Family
          </p>
        </div>


        {/* KPI pills */}
        <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
          {[
            { icon: 'fa-plane',      val: FLEET_DATA.length, label: 'Aéronefs',      color: '#2563eb', bg: '#dbeafe' },
            { icon: 'fa-file-alt',   val: loading ? '…' : totalDocs.toLocaleString(), label: 'Documents', color: '#059669', bg: '#d1fae5' },
            { icon: 'fa-database',   val: loading ? '…' : `${withDocs}/${FLEET_DATA.length}`, label: 'Avec docs', color: '#d97706', bg: '#fef3c7' },
          ].map(k => (
            <div key={k.label} style={{
              background: k.bg, border: `1px solid ${k.color}33`,
              borderRadius: 10, padding: '8px 16px',
              display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <i className={`fas ${k.icon}`} style={{ color: k.color, fontSize: 16 }} />
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: k.color, lineHeight: 1 }}>{k.val}</div>
                <div style={{ fontSize: 10, color: k.color, opacity: .7, letterSpacing: '.05em' }}>{k.label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Filtres ───────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 18 }}>
        {[
          { key: 'ALL', label: `Tous (${FLEET_DATA.length})` },
          { key: 'NEO', label: `NEO (${neoCount})` },
          { key: 'CEO', label: `CEO (${ceoCount})` },
        ].map(f => (
          <button
            key={f.key}
            onClick={() => { setFilter(f.key); setSelected(null); }}
            style={{
              padding: '6px 18px', borderRadius: 20,
              fontSize: 12, fontWeight: 500,
              cursor: 'pointer',
              border: filter === f.key ? '1.5px solid var(--nv)' : '1px solid var(--bdr)',
              background: filter === f.key ? '#dbeafe' : 'var(--bg)',
              color: filter === f.key ? 'var(--nv)' : 'var(--tx2)',
              transition: 'all .15s',
            }}
          >{f.label}</button>
        ))}
      </div>

      {/* ── Grille ────────────────────────────────────────────── */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--tx3)', fontSize: 13 }}>
          <i className="fas fa-spinner fa-spin" style={{ marginRight: 8 }} />
          Chargement de la flotte...
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: 12,
        }}>
          {filtered.map(ac => (
            <AircraftCard
              key={ac.reg}
              ac={ac}
              docCount={docCounts[ac.reg]}
              checkCount={checkCounts[ac.reg]}
              selected={selected === ac.reg}
              onSelect={setSelected}
            />
          ))}
        </div>
      )}

      {/* ── Footer info ───────────────────────────────────────── */}
      <div style={{
        marginTop: 24, padding: '12px 16px',
        background: 'var(--bg2)', border: '1px solid var(--bdr)', borderRadius: 10,
        display: 'flex', alignItems: 'center', gap: 10, fontSize: 11, color: 'var(--tx3)',
      }}>
       
       
      </div>
    </div>
  );
}