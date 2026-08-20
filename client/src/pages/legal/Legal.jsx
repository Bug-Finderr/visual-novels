import { Link } from 'react-router-dom';

export const CONTACT_EMAIL = 'support@storyplex.app';
export const LAST_UPDATED = '20 August 2026';

/** Shared chrome for the policy pages. These exist because Cashfree requires
 *  published terms, privacy, refund and contact pages before a merchant
 *  account can be activated — and keeps the account active. */
export default function Legal({ eyebrow, title, children }) {
  return (
    <div className="page page--narrow legal">
      <Link to="/" className="back-link">← Back</Link>
      <div className="page-head">
        <span className="eyebrow">{eyebrow}</span>
        <h1 className="display">{title}</h1>
        <p className="legal__updated muted">Last updated {LAST_UPDATED}</p>
      </div>
      {children}
    </div>
  );
}
