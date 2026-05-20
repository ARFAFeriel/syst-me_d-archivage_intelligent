// components/ui/AlertBadge.jsx
import { timeAgo } from '../../hooks/useApi';

const sevMap = { critical: 'd', warning: 'w', info: 'i', success: 's' };
const iconMap = {
  critical: 'fa-radiation-alt',
  warning: 'fa-exclamation-circle',
  info: 'fa-info-circle',
  success: 'fa-check-circle',
};

export default function AlertBadge({ alert, onResolve }) {
  const cls = sevMap[alert.severity] || 'i';
  const icon = iconMap[alert.severity] || 'fa-info-circle';

  return (
    <div className={`al ${cls}`} style={alert.resolved ? { opacity: .5 } : {}}>
      <i className={`fas ${icon} al-ic`}></i>
      <div className="al-body">
        <p>{alert.title}</p>
        <span>{alert.message || ''}</span>
      </div>
      <span className="al-time">{timeAgo(alert.created_at)}</span>
      {onResolve && !alert.resolved && (
        <button
          className="btn btn-xs btn-out"
          style={{ marginLeft: 8, flexShrink: 0 }}
          onClick={() => onResolve(alert.id)}
        >
          <i className="fas fa-check"></i> Résoudre
        </button>
      )}
      {alert.resolved && (
        <span style={{ fontSize: 11, color: 'var(--acc)', marginLeft: 8, flexShrink: 0 }}>
          ✓ Résolu
        </span>
      )}
    </div>
  );
}
