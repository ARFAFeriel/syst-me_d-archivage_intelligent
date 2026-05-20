// components/ui/AlertBadge.jsx
import { timeAgo } from '../../hooks/useApi';

const sevMap  = { critical: 'd', warning: 'w', info: 'i', success: 's' };
const iconMap = {
  critical: 'fa-radiation-alt',
  warning:  'fa-exclamation-circle',
  info:     'fa-info-circle',
  success:  'fa-check-circle',
};

export default function AlertBadge({ alert, onResolve }) {
  const cls  = sevMap[alert.severity]  || 'i';
  const icon = iconMap[alert.severity] || 'fa-info-circle';

  return (
    <div className={`al ${cls}`} style={alert.resolved ? { opacity: .5 } : {}}>
      <i className={`fas ${icon} al-ic`}></i>

      <div className="al-body">
        <p>{alert.title}</p>
        <span>{alert.message || ''}</span>
        {alert.aircraft_registration && (
          <span className="tag b" style={{ fontSize: 10, marginTop: 4, display: 'inline-block' }}>
            {alert.aircraft_registration}
          </span>
        )}
      </div>

      <span className="al-time">{timeAgo(alert.created_at)}</span>

      {onResolve && !alert.resolved && (
        <button
          className="btn btn-sm"
          style={{
            marginLeft: 8, flexShrink: 0,
            background: 'var(--bg2)', border: '1px solid var(--bdr)',
            color: 'var(--tx2)', borderRadius: 7, padding: '4px 10px',
            fontSize: 12, cursor: 'pointer', display: 'flex',
            alignItems: 'center', gap: 5,
          }}
          onClick={() => onResolve(alert.id)}
          title="Résoudre manuellement"
        >
          <i className="fas fa-wrench" style={{ fontSize: 11 }}></i>
          Résoudre
        </button>
      )}

      {alert.resolved && (
        <span style={{
          fontSize: 11, color: 'var(--acc)', marginLeft: 8,
          flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4,
        }}>
          <i className="fas fa-check-circle"></i> Résolu
        </span>
      )}
    </div>
  );
}