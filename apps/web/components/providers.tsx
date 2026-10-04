/**
 * Wallet provider boundary.
 *
 * This is the single place where a wallet can exist in the tree. Reads never
 * require it; only writes do, and they check it first.
 *
 * RainbowKit needs a wagmi `config` with a chain list. There is no GenLayer
 * chain in viem's registry, so the chains are supplied explicitly — and only
 * the configured GenLayer network is offered, because switching a user's wallet
 * to an unintended chain is a real cost with no benefit here.
 */

"use client";

import "@rainbow-me/rainbowkit/styles.css";

import { RainbowKitProvider, darkTheme, type Theme } from "@rainbow-me/rainbowkit";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { WagmiProvider, http, type Config } from "wagmi";
import { createConfig } from "wagmi";

import { chainForNetwork, isSupportedNetwork, rpcForNetwork } from "@/lib/genlayer";

const NETWORK = process.env.NEXT_PUBLIC_GENLAYER_NETWORK ?? "studionet";
const RPC_URL = rpcForNetwork(NETWORK);
const CONNECT_PROJECT_ID = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID ?? "";

/**
 * RainbowKit theme mapped onto ForkReason's tokens so the wallet modal does not
 * look bolted on.
 *
 * Keys below are exactly the members of the installed 2.2.11 `Theme` type, read
 * from the package's own `darkTheme.d.ts`. That type uses `accentColor*` rather
 * than `primary`, a flat `fonts.body`, and a five-key `radii`; guessing these
 * names produces a type error at build time.
 */
const base = darkTheme();

const theme: Theme = {
  ...base,
  colors: {
    ...base.colors,
    accentColor: "#12E6A7",
    accentColorForeground: "#04100D",

    modalBackground: "rgba(11,24,21,0.94)",
    modalBorder: "rgba(244,255,250,0.16)",
    modalText: "#EAF7F1",
    modalTextSecondary: "#A8C3BA",
    modalTextDim: "#94AAA3",
    modalBackdrop: "rgba(4,11,10,0.72)",

    connectButtonBackground: "rgba(244,255,250,0.08)",
    connectButtonBackgroundError: "rgba(255,102,85,0.16)",
    connectButtonInnerBackground: "rgba(244,255,250,0.06)",
    connectButtonText: "#EAF7F1",
    connectButtonTextError: "#FF6655",

    actionButtonBorder: "rgba(244,255,250,0.18)",
    actionButtonBorderMobile: "rgba(244,255,250,0.18)",
    actionButtonSecondaryBackground: "rgba(244,255,250,0.07)",

    menuItemBackground: "rgba(244,255,250,0.06)",
    profileAction: "rgba(244,255,250,0.07)",
    profileActionHover: "rgba(19,207,244,0.16)",
    profileForeground: "#EAF7F1",

    closeButton: "#94AAA3",
    closeButtonBackground: "rgba(244,255,250,0.07)",

    generalBorder: "rgba(244,255,250,0.16)",
    generalBorderDim: "rgba(244,255,250,0.08)",
    selectedOptionBorder: "rgba(18,230,167,0.44)",
    connectionIndicator: "#12E6A7",
    standby: "#FFC857",
    error: "#FF6655",
  },
  fonts: {
    body: "var(--font-instrument), ui-sans-serif, system-ui, sans-serif",
  },
  radii: {
    actionButton: "999px",
    connectButton: "999px",
    menuButton: "10px",
    modal: "20px",
    modalMobile: "16px",
  },
};

export function Providers({ children }: { children: ReactNode }) {
  const config = useMemo<Config>(() => {
    const chain = chainForNetwork(NETWORK);
    const projectId = CONNECT_PROJECT_ID;
    return createConfig({
      chains: [chain],
      connectors: projectId
        ? // WalletConnect needs a project id. With none configured, RainbowKit
          // still offers injected and WalletConnect-created (in-wallet) options.
          []
        : [],
      transports: {
        [chain.id]: http(RPC_URL),
      },
      ssr: true,
    });
  }, []);

  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Analysis progress is polled; a short stale window keeps the UI
            // honest without hammering the API.
            staleTime: 2_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
    [],
  );

  return (
    <WagmiProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider theme={theme} showRecentTransactions={false}>
          {children}
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}

export { NETWORK as GENLAYER_NETWORK, isSupportedNetwork };