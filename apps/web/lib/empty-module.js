/**
 * Stub for payment/account SDKs that RainbowKit's connector barrel imports but
 * ForkReason never uses.
 *
 * `@wagmi/connectors` -> `@base-org/account` -> `@coinbase/cdp-sdk` -> `@x402/*`.
 * The `@x402/*` packages are declared *optional* peers of cdp-sdk, so they are
 * not installed, but their imports are still resolved at build time and the
 * build fails without them.
 *
 * Rather than installing four payment packages ForkReason would never call, the
 * resolver is pointed here. Any real access throws immediately rather than
 * failing silently, so an accidental dependency is loud rather than latent.
 */

function makeGuard(name) {
  return function guarded() {
    throw new Error(
      name +
        " is not available in ForkReason. ForkReason connects through a browser " +
        "wallet on a GenLayer chain; it does not use Coinbase smart accounts or " +
        "x402 payments.",
    );
  };
}

const handler = {
  get(_target, property) {
    if (property === "__esModule") return true;
    if (property === "default") return {};
    if (property === "then") return undefined;
    return new Proxy(makeGuard, {
      get: (_fn, nested) => makeGuard(`${String(property)}.${String(nested)}`),
      apply: (_fn, _this, args) => makeGuard(`${String(property)}(...)`)(),
    });
  },
};

module.exports = new Proxy({}, handler);