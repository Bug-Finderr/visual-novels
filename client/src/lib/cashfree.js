// Cashfree JS SDK v3 loader.
//
// Injected on demand rather than bundled: the SDK is only needed by the
// billing page, and pulling it into the main bundle would cost every visitor
// a third-party script they'll probably never use.
const SDK_URL = 'https://sdk.cashfree.com/js/v3/cashfree.js';

let loading = null;

function loadSdk() {
  if (window.Cashfree) return Promise.resolve(window.Cashfree);
  if (loading) return loading;

  loading = new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = SDK_URL;
    el.async = true;
    el.onload = () => (window.Cashfree
      ? resolve(window.Cashfree)
      : reject(new Error('Cashfree SDK loaded but did not initialise.')));
    el.onerror = () => {
      loading = null; // allow a retry
      reject(new Error('Could not load the payment SDK. Check your connection and retry.'));
    };
    document.head.appendChild(el);
  });
  return loading;
}

/**
 * Hand a payment session to Cashfree's hosted checkout.
 * `mode` is 'sandbox' or 'production' and must match the credentials the
 * backend used to mint the session — a mismatch fails with an opaque error.
 * Redirects the tab; on return the browser lands on /billing/return.
 */
export async function openCheckout(paymentSessionId, mode = 'sandbox') {
  const Cashfree = await loadSdk();
  const cashfree = Cashfree({ mode });
  return cashfree.checkout({ paymentSessionId, redirectTarget: '_self' });
}
