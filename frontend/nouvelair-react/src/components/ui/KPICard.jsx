// components/ui/KPICard.jsx
export default function KPICard({ value, label, icon, color = 'b', delta, deltaUp = true }) {
  return (
    <div className="kpi">
      <div className={`kic ${color}`}>
        <i className={`fas ${icon}`}></i>
      </div>
      <div>
        <div className="kval">{value ?? '—'}</div>
        <div className="klbl">{label}</div>
        {delta && (
          <div className={`kd ${deltaUp ? 'up' : 'dn'}`}>
            <i className={`fas fa-arrow-${deltaUp ? 'up' : 'down'}`} style={{ fontSize: 9 }}></i>
            {delta}
          </div>
        )}
      </div>
    </div>
  );
}
