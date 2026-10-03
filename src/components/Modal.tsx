import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
export default function Modal({ title, onClose, children, wide = false, className = '' }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); return () => { ref.current?.close(); }; }, []);
  return <dialog ref={ref} className={`modal ${wide ? 'wide-modal' : ''} ${className}`} onCancel={onClose} onClick={e => { if (e.target === ref.current) onClose(); }}><div className="modal-header"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={19}/></button></div><div className="modal-content">{children}</div></dialog>;
}
