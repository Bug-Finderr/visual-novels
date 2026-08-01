import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

/* In-page animated confirm dialog, replacing window.confirm(). Usage:
 *   const confirm = useConfirm();
 *   if (await confirm({ title, message, confirmText, danger })) { ... }
 */
const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null);
  const resolver = useRef(null);

  const confirm = useCallback((opts) => new Promise((resolve) => {
    resolver.current = resolve;
    setState({ confirmText: 'Confirm', cancelText: 'Cancel', danger: false, ...opts });
  }), []);

  const close = useCallback((result) => {
    setState(null);
    if (resolver.current) { resolver.current(result); resolver.current = null; }
  }, []);

  useEffect(() => {
    if (!state) return undefined;
    // Escape cancels. Deliberately NO Enter-to-confirm, so a destructive
    // action always needs an explicit click on the (clearly labelled) button.
    const onKey = (e) => { if (e.key === 'Escape') close(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [state, close]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <div className="modal-backdrop" onClick={() => close(false)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            {state.title && <h3 className="modal-title">{state.title}</h3>}
            <p className="modal-message">{state.message}</p>
            <div className="modal-actions">
              {/* Cancel is focused by default so an errant Enter/click is safe. */}
              <button className="btn" onClick={() => close(false)} autoFocus>
                {state.cancelText}
              </button>
              <button
                className={`btn ${state.danger ? 'btn-danger-solid' : 'btn-primary'}`}
                onClick={() => close(true)}
              >
                {state.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm must be used within a ConfirmProvider');
  return ctx;
}
