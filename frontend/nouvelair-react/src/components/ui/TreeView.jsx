// components/ui/TreeView.jsx
// Arborescence documentaire NouvelAir — NEO (Standard List A–H + BOCA) / CEO (A–K)
import { useState } from 'react';

// ── Tags origine ──────────────────────────────────────────────────────────────
const ORIGIN_TAG = {
  BOCA:       { label: 'BOCA',       cls: 'tag or' },
  AIRBUS_LBT: { label: 'Airbus LBT', cls: 'tag c'  },
  MRO:        { label: 'MRO',        cls: 'tag b'  },
  GECAS:      { label: 'GECAS',      cls: 'tag p'  },
};

// ── Arborescences statiques par type d'avion ──────────────────────────────────
const NEO_TREE = [
  {
    id: 'boca', label: 'Dossier BOCA — BOC Aviation', origin: 'BOCA', icon: 'fa-briefcase',
    children: [
      { id: 'boca-corporate', label: 'Corporate Documents',   origin: 'BOCA', icon: 'fa-building',
        children: [
          { id: 'b001', label: "001. Officer's Certificate",       origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b005', label: '005. Process Agent',               origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b027', label: '027. Bringdown Certificate',       origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b045', label: '045. BOC Aviation Certificate',    origin: 'BOCA', icon: 'fa-file-alt' },
        ]
      },
      { id: 'boca-lease', label: 'Lease Agreement', origin: 'BOCA', icon: 'fa-file-contract',
        children: [
          { id: 'b008', label: '008. Aircraft Lease Agreement',    origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b041', label: '041. Rent Invoice',               origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b042', label: '042. Security Deposit Invoice',   origin: 'BOCA', icon: 'fa-file-alt' },
        ]
      },
      { id: 'boca-delivery', label: 'Delivery Documents', origin: 'BOCA', icon: 'fa-box-open',
        children: [
          { id: 'b009', label: '009. Lessee Acceptance Certificate', origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b010', label: '010. Deregistration POA',            origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b012', label: '012. Airframe Warranties',           origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b013', label: '013. AWA Initial Notice',            origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b024', label: '024. Letter Engine Manufacturer',    origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b025', label: '025. Eurocontrol Letter',            origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b031', label: '031. Emissions Monitoring Plan',     origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b037', label: '037. AMP Evidence',                  origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b048', label: '048. Bill of Sale',                  origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b049', label: '049. Certificate of Acceptance',     origin: 'BOCA', icon: 'fa-file-alt' },
        ]
      },
      { id: 'boca-insurance', label: 'Insurance', origin: 'BOCA', icon: 'fa-shield-alt',
        children: [
          { id: 'b018', label: '018. Assignment of Insurance',         origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b043', label: '043. Certificate of Insurance',        origin: 'BOCA', icon: 'fa-file-alt' },
          { id: 'b044', label: '044. Letter Central Bank',             origin: 'BOCA', icon: 'fa-file-alt' },
        ]
      },
    ]
  },
  {
    id: 'airbus', label: 'Dossier Airbus — Standard List', origin: 'AIRBUS_LBT', icon: 'fa-plane-departure',
    children: [
      { id: 'sec-a', label: 'A — AIRBUS AIRCRAFT LOGBOOK', origin: 'AIRBUS_LBT', icon: 'fa-book',
        children: [
          { id: 'a1', label: '1.  Aircraft Certificates',              origin: 'AIRBUS_LBT', icon: 'fa-certificate' },
          { id: 'a2', label: '2.  AD Compliance List',                 origin: 'AIRBUS_LBT', icon: 'fa-list-check' },
          { id: 'a3', label: '3.  Modification List',                  origin: 'AIRBUS_LBT', icon: 'fa-wrench' },
          { id: 'a4', label: '4.  Aircraft Inspection Report',         origin: 'AIRBUS_LBT', icon: 'fa-search' },
          { id: 'a5', label: '5.  Weighing Report',                    origin: 'AIRBUS_LBT', icon: 'fa-balance-scale' },
          { id: 'a6', label: '6.  Additional Documentation',           origin: 'AIRBUS_LBT', icon: 'fa-folder-plus' },
        ]
      },
      { id: 'sec-b', label: 'B — LOG BOOKS',              origin: 'AIRBUS_LBT', icon: 'fa-book-open' },
      { id: 'sec-d', label: 'D — SET OF KEYS',            origin: 'AIRBUS_LBT', icon: 'fa-key' },
      { id: 'sec-e', label: 'E — COMPLIANCE DOCUMENTS',   origin: 'AIRBUS_LBT', icon: 'fa-check-double' },
      { id: 'sec-f', label: 'F — OTHER DOC (Buyer)',      origin: 'AIRBUS_LBT', icon: 'fa-file' },
      { id: 'sec-g', label: 'G — OTHER DOC (Operator)',   origin: 'AIRBUS_LBT', icon: 'fa-file' },
      { id: 'sec-h', label: 'H — OTHER DOC (Seller)',     origin: 'AIRBUS_LBT', icon: 'fa-file' },
    ]
  },
];

const CEO_TREE = [
  {
    id: 'ceo-a', label: 'A) Certificates', origin: 'MRO', icon: 'fa-certificate',
    children: [
      { id: 'a001', label: 'A001 — Certificate of Airworthiness',    origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a002', label: 'A002 — Certificate of Registration',      origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a003', label: 'A003 — Airworthiness Review Certificate', origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a004', label: 'A004 — Noise Certificate',                origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a005', label: 'A005 — Radio Station License',            origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a006', label: 'A006 — Aircraft De-registration',         origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a007', label: 'A007 — Burns Certificates',               origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a008', label: 'A008 — Certificate of Sanitary Construction', origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a009', label: 'A009 — Air Operators Certificate',        origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a010', label: 'A010 — Export Certificate of Airworthiness', origin: 'MRO', icon: 'fa-file-alt' },
      { id: 'a011', label: 'A011 — Insurance Certificate',            origin: 'MRO', icon: 'fa-file-alt' },
    ]
  },
  {
    id: 'ceo-b', label: 'B) Maintenance Status', origin: 'MRO', icon: 'fa-tools',
    children: [
      { id: 'b001', label: 'B001 — Current Time In Service',          origin: 'MRO', icon: 'fa-clock' },
      { id: 'b002', label: 'B002 — Status of AD',                     origin: 'MRO', icon: 'fa-exclamation-triangle' },
      { id: 'b003', label: 'B003 — Status of SB (Historic)',          origin: 'MRO', icon: 'fa-list' },
      { id: 'b004', label: 'B004 — Status of non-SB Modifications',   origin: 'MRO', icon: 'fa-wrench' },
      { id: 'b005', label: 'B005 — SSI Status',                       origin: 'MRO', icon: 'fa-layer-group' },
      { id: 'b006', label: 'B006 — CPCP Status',                      origin: 'MRO', icon: 'fa-layer-group' },
      { id: 'b007', label: 'B007 — HT Components List',               origin: 'MRO', icon: 'fa-list' },
      { id: 'b008', label: 'B008 — OCCM List',                        origin: 'MRO', icon: 'fa-list' },
      { id: 'b009', label: 'B009 — Check History',                    origin: 'MRO', icon: 'fa-history' },
      { id: 'b010', label: 'B010 — Maintenance Requirements',         origin: 'MRO', icon: 'fa-tasks' },
    ]
  },
  {
    id: 'ceo-c', label: 'C) Maintenance Records', origin: 'MRO', icon: 'fa-clipboard-list',
    children: [
      { id: 'c001', label: 'C001 — Technical Logs (2001–2010+)',       origin: 'MRO', icon: 'fa-book' },
      { id: 'c020', label: 'C020 — DFPs courants',                    origin: 'MRO', icon: 'fa-file-medical' },
    ]
  },
  {
    id: 'ceo-ad', label: 'AD / Airworthiness Directives', origin: 'MRO', icon: 'fa-exclamation-circle',
    children: [
      { id: 'ad-easa', label: 'EASA ADs (par année)',   origin: 'MRO', icon: 'fa-folder' },
      { id: 'ad-faa',  label: 'FAA ADs (par année)',    origin: 'MRO', icon: 'fa-folder' },
      { id: 'ad-dfp',  label: 'AD DFPs',               origin: 'MRO', icon: 'fa-folder' },
    ]
  },
];

// ── Composant noeud récursif ──────────────────────────────────────────────────
function TreeNode({ node, depth = 0, originFilter }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = node.children?.length > 0;
  const origin = ORIGIN_TAG[node.origin] || ORIGIN_TAG.MRO;

  // Filtre par origine
  if (originFilter && originFilter !== 'ALL' && node.origin !== originFilter) {
    // Garder si un enfant matche
    const anyChildMatches = (n) =>
      n.origin === originFilter ||
      n.children?.some(c => anyChildMatches(c));
    if (!anyChildMatches(node)) return null;
  }

  return (
    <div style={{ paddingLeft: depth > 0 ? 16 : 0 }}>
      <div
        className="tree-node"
        style={{
          display: 'flex', alignItems: 'center', gap: 7,
          padding: '5px 8px', borderRadius: 6, cursor: hasChildren ? 'pointer' : 'default',
          transition: '.12s', marginBottom: 2,
        }}
        onClick={() => hasChildren && setOpen(o => !o)}
      >
        {/* Toggle arrow */}
        <span style={{ width: 14, flexShrink: 0, color: 'var(--tx3)', fontSize: 10 }}>
          {hasChildren ? (open ? '▼' : '▶') : ''}
        </span>

        {/* Icon */}
        <i
          className={`fas ${node.icon || 'fa-file'}`}
          style={{
            fontSize: 11, flexShrink: 0, width: 14, textAlign: 'center',
            color: node.origin === 'BOCA' ? '#c2410c'
                 : node.origin === 'AIRBUS_LBT' ? '#0e7490'
                 : 'var(--nv)',
          }}
        />

        {/* Label */}
        <span style={{
          fontSize: 12, color: hasChildren ? 'var(--tx)' : 'var(--tx2)',
          fontWeight: hasChildren ? 600 : 400, flex: 1,
        }}>
          {node.label}
        </span>

        {/* Origin tag — seulement sur les racines */}
        {depth === 0 && (
          <span className={origin.cls} style={{ fontSize: 9 }}>{origin.label}</span>
        )}
      </div>

      {/* Enfants */}
      {hasChildren && open && (
        <div style={{ borderLeft: '1px solid var(--bdr)', marginLeft: 19, paddingLeft: 4 }}>
          {node.children.map(child => (
            <TreeNode key={child.id} node={child} depth={depth + 1} originFilter={originFilter} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Export principal ──────────────────────────────────────────────────────────
export default function TreeView({ aircraftType = 'CEO', originFilter = 'ALL' }) {
  const tree = aircraftType === 'NEO' ? NEO_TREE : CEO_TREE;

  return (
    <div style={{ padding: '4px 0' }}>
      {tree.map(node => (
        <TreeNode key={node.id} node={node} depth={0} originFilter={originFilter} />
      ))}
    </div>
  );
}