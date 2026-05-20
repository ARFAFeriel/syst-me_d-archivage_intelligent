// contexts/ToastContext.jsx
import { createContext, useContext, useState, useCallback } from 'react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const toast = useCallback((msg, type = 'ok', dur = 3500) => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, msg, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), dur);
  }, []);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div id="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast-item ${t.type}`}>{t.msg}</div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
