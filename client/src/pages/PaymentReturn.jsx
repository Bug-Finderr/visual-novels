import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api.js';
import { useRefreshCredits } from '../lib/credits.js';

// A card/UPI payment can still be settling when the browser gets redirected
// back, so a "pending" answer isn't final — re-check a few times before
// telling the user anything discouraging. The webhook is the backstop if they
// close the tab during this.
const MAX_POLLS = 6;
const POLL_MS = 2000;

export default function PaymentReturn() {
  const [params] = useSearchParams();
  const orderId = params.get('order_id');
  const refreshCredits = useRefreshCredits();

  const [state, setState] = useState({ phase: 'checking' });
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    if (!orderId) {
      setState({ phase: 'error', message: 'No order reference came back from the gateway.' });
      return undefined;
    }

    let attempt = 0;
    async function check() {
      if (cancelled.current) return;
      try {
        const result = await api.post(`/billing/orders/${orderId}/verify`, {});
        if (cancelled.current) return;

        if (result.status === 'paid') {
          refreshCredits();
          setState({ phase: 'paid', credits: result.credits, balance: result.balance });
          return;
        }
        if (result.status === 'amount_mismatch') {
          setState({
            phase: 'error',
            message: 'The amount paid didn\'t match the order. Nothing was credited — '
              + 'contact us and we\'ll sort it out.',
          });
          return;
        }
        if (['expired', 'terminated'].includes(result.status)) {
          setState({ phase: 'failed', message: 'That payment didn\'t go through.' });
          return;
        }

        attempt += 1;
        if (attempt >= MAX_POLLS) {
          setState({
            phase: 'pending',
            message: 'Your payment is still being confirmed. Credits appear automatically '
              + 'once it clears — no need to pay again.',
          });
          return;
        }
        setTimeout(check, POLL_MS);
      } catch (err) {
        if (!cancelled.current) {
          setState({ phase: 'error', message: err.message || 'Could not confirm the payment.' });
        }
      }
    }
    check();
    return () => { cancelled.current = true; };
  }, [orderId]);

  const { phase } = state;

  return (
    <div className="page page--narrow">
      <div className="page-head">
        <span className="eyebrow">Payment</span>
        <h1 className="display">
          {phase === 'checking' && 'Confirming your payment…'}
          {phase === 'paid' && 'Credits added'}
          {phase === 'pending' && 'Almost there'}
          {phase === 'failed' && 'Payment not completed'}
          {phase === 'error' && 'Something went wrong'}
        </h1>
      </div>

      <div className="panel" style={{ padding: '2.5rem', textAlign: 'center' }}>
        {phase === 'checking' && (
          <div className="empty"><div className="dots"><span /><span /><span /></div></div>
        )}

        {phase === 'paid' && (
          <>
            <div className="credit-balance__count" style={{ justifyContent: 'center' }}>
              {state.balance}
              <span className="credit-balance__unit">
                {state.balance === 1 ? 'credit' : 'credits'}
              </span>
            </div>
            <p className="muted">
              {state.credits} {state.credits === 1 ? 'credit' : 'credits'} added to your account.
            </p>
            <div className="form-actions" style={{ justifyContent: 'center' }}>
              <Link to="/create" className="btn btn-primary btn-lg">
                <span className="btn-icon">✦</span> Weave a tale
              </Link>
            </div>
          </>
        )}

        {phase !== 'checking' && phase !== 'paid' && (
          <>
            <p>{state.message}</p>
            <div className="form-actions" style={{ justifyContent: 'center' }}>
              <Link to="/billing" className="btn">Back to credits</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
