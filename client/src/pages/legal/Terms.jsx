import { Link } from 'react-router-dom';
import Legal, { CONTACT_EMAIL } from './Legal.jsx';

export default function Terms() {
  return (
    <Legal eyebrow="Legal" title="Terms of service">
      <p>
        These terms govern your use of StoryPlex at storyplex.app. By signing in or buying
        credits you agree to them.
      </p>

      <h2>The service</h2>
      <p>
        StoryPlex generates visual novels from a premise you supply, using third-party AI
        models. Output is produced automatically and is not reviewed by a person before you
        see it. Stories vary in quality and are not guaranteed to match your expectations.
      </p>

      <h2>Accounts</h2>
      <p>
        You sign in with Google. You are responsible for activity on your account. One
        person, one account — creating additional accounts to collect the free credit grant
        more than once is not permitted, and we may reclaim credits obtained that way.
      </p>

      <h2>Credits and payment</h2>
      <ul>
        <li>Credits are prepaid, priced in Indian Rupees, and do not expire.</li>
        <li>A credit is consumed when a story begins generating.</li>
        <li>Prices are shown inclusive of applicable taxes at the time of purchase.</li>
        <li>
          Payments are processed by Cashfree Payments. We never see or store your card or
          UPI details.
        </li>
        <li>Refunds are governed by our <Link to="/legal/refunds">refund policy</Link>.</li>
      </ul>

      <h2>Your content</h2>
      <p>
        You keep ownership of the premises you write. You grant us the licence needed to
        run the service — to process your input through AI models, store the result, and
        display it back to you. If you publish a story, you allow other users to read it on
        StoryPlex; you can unpublish it at any time from your library.
      </p>

      <h2>Acceptable use</h2>
      <p>Don't use StoryPlex to generate or publish:</p>
      <ul>
        <li>Sexual content involving minors, or content that sexualises real people.</li>
        <li>Content that harasses, defames, or incites violence against real people.</li>
        <li>Content that infringes someone else's copyright or trademarks.</li>
        <li>Anything unlawful under Indian law.</li>
      </ul>
      <p>
        We may remove content and suspend accounts that break these rules. Where we suspend
        an account for abuse, unspent credits are not refunded.
      </p>

      <h2>Availability</h2>
      <p>
        StoryPlex is offered as-is. We do not guarantee uninterrupted availability, and we
        depend on third-party AI providers whose outages we cannot control. If an outage
        costs you a credit, our <Link to="/legal/refunds">refund policy</Link> covers it.
      </p>

      <h2>Liability</h2>
      <p>
        To the extent permitted by law, our total liability to you for any claim is limited
        to the amount you paid us in the 12 months before it arose. We are not liable for
        indirect or consequential loss.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms. Material changes will be announced on the site before
        they take effect. Continuing to use StoryPlex after that means you accept them.
      </p>

      <h2>Governing law and contact</h2>
      <p>
        These terms are governed by the laws of India, and the courts of India have
        exclusive jurisdiction. Questions:{' '}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>
    </Legal>
  );
}
