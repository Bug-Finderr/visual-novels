import Legal, { CONTACT_EMAIL } from './Legal.jsx';

export default function Privacy() {
  return (
    <Legal eyebrow="Legal" title="Privacy policy">
      <p>
        This explains what StoryPlex collects, why, and what you can do about it.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>
          <b>Account details</b> — your name, email address and profile picture, received
          from Google when you sign in. We never receive your Google password.
        </li>
        <li>
          <b>Your stories</b> — the premises you write and the stories generated from them.
        </li>
        <li>
          <b>Billing records</b> — which credit pack you bought, the amount, a payment
          reference, and the mobile number you enter at checkout. <b>We do not receive or
          store your card, UPI or bank details</b> — those go directly to Cashfree.
        </li>
        <li>
          <b>Operational logs</b> — technical records of requests and errors, used to keep
          the service working.
        </li>
      </ul>

      <h2>Why we use it</h2>
      <p>
        To run your account, generate and store your stories, process payments and maintain
        your credit balance, and to diagnose faults. We do not sell your data, and we do not
        use it for advertising.
      </p>

      <h2>Who else sees it</h2>
      <ul>
        <li><b>Google</b> — sign-in, and Gemini, which generates story text and artwork.</li>
        <li><b>Cashfree Payments</b> — payment processing.</li>
        <li>
          <b>Our hosting and storage providers</b> — Render (application and database) and
          Google Cloud Storage (generated images and audio).
        </li>
      </ul>
      <p>
        The premises you write are sent to Google's Gemini API to generate your story. Don't
        put anything in a premise that you would not want processed by a third-party AI
        service.
      </p>

      <h2>Published stories</h2>
      <p>
        A story is private until you publish it. Publishing makes it, and your display name,
        visible to anyone on StoryPlex. Unpublishing removes it from public view.
      </p>

      <h2>Retention</h2>
      <p>
        Account and story data is kept while your account exists. Billing records are kept
        for as long as tax and accounting rules require, even after account deletion.
      </p>

      <h2>Your choices</h2>
      <p>
        You can delete any story from your library at any time, which removes its generated
        assets too. To delete your account and everything attached to it, email{' '}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> and we will action it within
        30 days. You can also ask us for a copy of what we hold about you.
      </p>

      <h2>Security</h2>
      <p>
        Traffic is encrypted in transit. Sign-in uses an opaque server-side session token
        stored as a secure, HTTP-only cookie — your Google tokens never reach your browser.
        No system is perfectly secure, but we take reasonable measures to protect your data.
      </p>

      <h2>Contact</h2>
      <p>
        Questions or complaints about privacy:{' '}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>
    </Legal>
  );
}
