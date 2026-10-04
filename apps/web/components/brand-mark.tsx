/**
 * ForkReason wordmark.
 *
 * Two repository nodes joined by a lineage path, with a divergence branch —
 * the product's core idea in one mark. Drawn with SVG so it inherits the
 * current colour and needs no network request.
 */
export function BrandMark({ size = 26 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="ForkReason"
      className="brand-mark"
    >
      <defs>
        <linearGradient id="fr-edge" x1="4" y1="4" x2="28" y2="28">
          <stop offset="0%" stopColor="var(--mint)" />
          <stop offset="55%" stopColor="var(--aqua)" />
          <stop offset="100%" stopColor="var(--signal)" />
        </linearGradient>
      </defs>

      {/* lineage path */}
      <path
        d="M7 23 C 12 23, 13 9, 19 9"
        stroke="url(#fr-edge)"
        strokeWidth="2.1"
        strokeLinecap="round"
        fill="none"
      />
      {/* divergence branch */}
      <path
        d="M19 9 C 23 9, 25 15, 25 20"
        stroke="var(--aqua)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeDasharray="2.4 2.4"
        fill="none"
        opacity="0.72"
      />

      {/* origin node */}
      <circle cx="6.5" cy="23.5" r="4.1" fill="var(--ink)" stroke="var(--mint)" strokeWidth="2" />
      <circle cx="6.5" cy="23.5" r="1.35" fill="var(--mint)" />

      {/* target node */}
      <circle cx="19.5" cy="9" r="4.1" fill="var(--ink)" stroke="var(--aqua)" strokeWidth="2" />
      <circle cx="19.5" cy="9" r="1.35" fill="var(--aqua)" />

      {/* shared-upstream candidate */}
      <circle cx="25.4" cy="21.6" r="2.5" fill="var(--ink)" stroke="var(--amber)" strokeWidth="1.7" />
    </svg>
  );
}