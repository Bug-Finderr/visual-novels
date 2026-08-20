import { Link } from 'react-router-dom';
import Legal, { CONTACT_EMAIL } from './Legal.jsx';

export default function Contact() {
  return (
    <Legal eyebrow="Support" title="Contact us">
      <p>
        StoryPlex is a small operation. Email is the fastest way to reach a person.
      </p>

      <h2>Email</h2>
      <p>
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        <br />
        We aim to reply within 3 working days.
      </p>

      <h2>What to include</h2>
      <ul>
        <li>The email address on your StoryPlex account.</li>
        <li>
          For a billing question, the order reference from your{' '}
          <Link to="/billing">credits page</Link>.
        </li>
        <li>For a story problem, the story's title or link.</li>
      </ul>

      <h2>Common questions</h2>
      <ul>
        <li>
          <b>A story failed and my credit is gone.</b> Email us — we keep a ledger of every
          credit movement and will restore it. See the{' '}
          <Link to="/legal/refunds">refund policy</Link>.
        </li>
        <li>
          <b>I paid but my balance didn't change.</b> Give it a minute and reload — payment
          confirmation can lag. If it still hasn't appeared, email us with the order
          reference and we'll settle it by hand.
        </li>
        <li>
          <b>I want my account deleted.</b> Email us and we'll action it within 30 days.
        </li>
      </ul>
    </Legal>
  );
}
