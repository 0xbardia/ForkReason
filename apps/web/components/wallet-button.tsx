"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";

/**
 * Wallet button.
 *
 * Present in the nav on every page, because a write will eventually need it.
 * But nothing in the read path is gated on it: a visitor can trace, read a
 * report and explore without ever connecting.
 */
export function WalletButton() {
  return (
    <div className="wallet-button">
      <ConnectButton
        showBalance={false}
        chainStatus={{ smallScreen: "icon", largeScreen: "none" }}
        // GenLayer has no EIP-6963 chain metadata, so the wallet's own name is
        // the honest thing to show rather than a chain name it cannot resolve.
        accountStatus="address"
        label="Connect"
      />
    </div>
  );
}