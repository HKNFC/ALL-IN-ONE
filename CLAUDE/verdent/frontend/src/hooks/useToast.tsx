/**
 * useToast — lightweight toast notification system.
 * Usage:
 *   const { toast } = useToast();
 *   toast.success('Backtest started');
 *   toast.error('Something went wrong');
 *   toast.warning('Check parameters');
 */
import { useState, useCallback, useRef } from 'react';
import { CheckCircle2, XCircle, AlertTriangle, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning';

interface ToastItem {
  id:      string;
  type:    ToastType;
  message: string;
}

const ICONS = {
  success: <CheckCircle2 size={15} color="#00D084" />,
  error:   <XCircle     size={15} color="#FF4757" />,
  warning: <AlertTriangle size={14} color="#FFA502" />,
};

export function useToast() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const show = useCallback((type: ToastType, message: string, duration = 3500) => {
    const id = `toast-${++counter.current}`;
    setItems(prev => [...prev, { id, type, message }]);
    setTimeout(() => {
      setItems(prev => prev.filter(t => t.id !== id));
    }, duration);
  }, []);

  const dismiss = useCallback((id: string) => {
    setItems(prev => prev.filter(t => t.id !== id));
  }, []);

  const toast = {
    success: (msg: string, dur?: number) => show('success', msg, dur),
    error:   (msg: string, dur?: number) => show('error',   msg, dur),
    warning: (msg: string, dur?: number) => show('warning', msg, dur),
  };

  const ToastContainer = () => (
    <div className="toast-container">
      {items.map(t => (
        <div key={t.id} className={`toast ${t.type}`}>
          <span className="toast-icon">{ICONS[t.type]}</span>
          <span className="toast-msg">{t.message}</span>
          <button className="toast-close" onClick={() => dismiss(t.id)}>
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  );

  return { toast, ToastContainer };
}
