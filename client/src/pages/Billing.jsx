import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '../lib/api.js';
import { openCheckout } from '../lib/cashfree.js';
import { useCredits } from '../lib/credits.js';
import { useAuth } from '../auth/AuthContext.jsx';

const REASON_LABELS = {
  signup_grant: 'Welcome credits',
  purchase: 'Credits purchased',
  generation: 'Story woven',
  refund: 'Refunded',
  admin: 'Adjustment',
};

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

export default function Billing() {
  const { user, googleEnabled, login, loading } = useAuth();
  const [phone, setPhone] = useState('');
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');

  const packsQuery = useQuery({ queryKey: ['billing', 'packs'], queryFn: () => api.get('/billing/packs') });
  const account = useCredits(!!user);
  const ledger = useQuery({
    queryKey: ['billing', 'ledger'],
    queryFn: () => api.get('/billing/ledger?limit=25'),
    enabled: !!user,
    retry: false,
  });

  const buy = useMutation({
    mutationFn: (packId) => api.post('/billing/orders', { packId, phone }),
    onSuccess: async (order) => {
      // Redirects the tab to Cashfree's hosted page; we come back at
      // /billing/return, which settles and refreshes the balance.
      try {
        await openCheckout(order.paymentSessionId, order.mode);
      } catch (err) {
        setError(err.message || 'Could not open checkout.');
      }
    },
    onError: (err) => setError(err.message || 'Could not start the payment.'),
  });

  if (!loading && !user) {
    return (
      <div className="page page--narrow">
        <Link to="/" className="back-link">← Back</Link>
        <div className="page-head">
          <span className="eyebrow">Credits</span>
          <h1 className="display">Story credits</h1>
          <p>Sign in to see your balance and top up.</p>
        </div>
        <div className="panel" style={{ textAlign: 'center', padding: '2.5rem' }}>
          <button className="btn btn-primary btn-lg" onClick={login} disabled={!googleEnabled}>
            Sign in with Google
          </button>
        </div>
      </div>
    );
  }

  const packs = packsQuery.data?.packs || [];
  const billingEnabled = packsQuery.data?.billingEnabled;
  const checkoutReady = packsQuery.data?.checkoutReady;
  const mode = packsQuery.data?.mode;
  const balance = account.data?.balance;
  const phoneValid = phone.replace(/\D/g, '').length === 10;

  const onBuy = (packId) => {
    setError('');
    setSelected(packId);
    if (!phoneValid) {
      setError('Enter a 10-digit mobile number — the payment gateway requires one.');
      return;
    }
    buy.mutate(packId);
  };

  return (
    <div className="page page--narrow">
      <Link to="/" className="back-link">← Back</Link>
      <div className="page-head">
        <span className="eyebrow">Credits</span>
        <h1 className="display">Story credits</h1>
        <p>One credit weaves one complete story — cast, art, script, and voices.</p>
      </div>

      <div className="panel credit-balance">
        <div>
          <span className="eyebrow">Your balance</span>
          <div className="credit-balance__count">
            {account.isLoading ? '—' : balance}
            <span className="credit-balance__unit">{balance === 1 ? 'credit' : 'credits'}</span>
          </div>
        </div>
        <span className="nav-spacer" />
        <Link to="/create" className="btn btn-primary" disabled={!balance}>
          <span className="btn-icon">✦</span> Weave a tale
        </Link>
      </div>

      {!billingEnabled && (
        <div className="banner">
          <span className="badge badge-created">free</span>
          Credits aren't being charged yet — weaving is on the house while StoryPlex is in preview.
        </div>
      )}
      {billingEnabled && mode === 'sandbox' && (
        <div className="banner">
          <span className="badge badge-generating">test mode</span>
          Payments are in sandbox — use a test card or UPI id. No real money moves.
        </div>
      )}

      <div className="section-title">Top up <span className="rule" /></div>

      <div className="field">
        <label htmlFor="phone">Mobile number</label>
        <input
          id="phone" className="input" type="tel" inputMode="numeric"
          placeholder="10-digit mobile number"
          value={phone} onChange={(e) => setPhone(e.target.value)}
          maxLength={14}
        />
        <span className="char-count">Required by the payment gateway for your receipt.</span>
      </div>

      <div className="pack-grid">
        {packs.map((p) => (
          <div className={`panel pack ${selected === p.id ? 'pack--selected' : ''}`} key={p.id}>
            <div className="pack__name">{p.name}</div>
            <div className="pack__credits">{p.credits} {p.credits === 1 ? 'credit' : 'credits'}</div>
            <div className="pack__price">₹{p.amountRupees.toLocaleString('en-IN')}</div>
            <div className="pack__unit muted">₹{p.perCreditRupees} per story</div>
            <button
              className="btn btn-primary btn-block"
              disabled={!checkoutReady || !billingEnabled || buy.isPending}
              onClick={() => onBuy(p.id)}
            >
              {buy.isPending && selected === p.id ? 'Opening…' : 'Buy'}
            </button>
          </div>
        ))}
      </div>

      {!checkoutReady && billingEnabled && (
        <div className="banner">
          <span className="badge badge-error">setup</span>
          Payments aren't configured on the server yet.
        </div>
      )}
      {error && <div className="form-error">{error}</div>}

      <div className="section-title">History <span className="rule" /></div>
      {ledger.isLoading ? (
        <div className="empty"><div className="dots"><span /><span /><span /></div></div>
      ) : !ledger.data?.entries?.length ? (
        <div className="empty"><p>Nothing yet.</p></div>
      ) : (
        <div className="panel ledger">
          {ledger.data.entries.map((e, i) => (
            <div className="ledger__row" key={i}>
              <span className="ledger__reason">{REASON_LABELS[e.reason] || e.reason}</span>
              <span className="ledger__date muted">{formatDate(e.createdAt)}</span>
              <span className={`ledger__delta ${e.delta > 0 ? 'is-credit' : 'is-debit'}`}>
                {e.delta > 0 ? '+' : ''}{e.delta}
              </span>
              <span className="ledger__balance muted">{e.balanceAfter}</span>
            </div>
          ))}
        </div>
      )}

      <p className="muted" style={{ marginTop: '2rem', fontSize: '0.85rem' }}>
        Payments are processed by Cashfree. See our{' '}
        <Link to="/legal/refunds">refund policy</Link>,{' '}
        <Link to="/legal/terms">terms</Link>, and{' '}
        <Link to="/legal/privacy">privacy policy</Link>.
      </p>
    </div>
  );
}

export { REASON_LABELS };
