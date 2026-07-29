interface Props {
  size?: number;
  className?: string;
}

/** Whale shark side-profile silhouette: torpedo body, forked tail, dorsal +
 * pectoral fins, spot pattern. */
export function WhaleSharkLogo({ size = 40, className }: Props) {
  return (
    <svg
      width={size}
      height={size * 0.42}
      viewBox="0 0 260 110"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="Whale Sharks logo"
    >
      {/* tail fin, drawn first so the body overlaps its base */}
      <path d="M196 45 L 252 10 L 204 50 Z" fill="currentColor" />
      <path d="M196 57 L 252 92 L 204 52 Z" fill="currentColor" />

      {/* body */}
      <path
        d="M6 55
           C 6 34, 28 18, 62 16
           C 100 14, 150 17, 183 30
           C 192 34, 198 40, 202 45
           L 202 47
           C 198 48, 198 52, 202 53
           L 202 55
           C 198 60, 192 66, 183 70
           C 150 83, 100 86, 62 84
           C 28 82, 6 76, 6 55 Z"
        fill="currentColor"
      />

      {/* dorsal fin */}
      <path d="M104 17 C 108 -8, 134 -8, 138 17 Z" fill="currentColor" />
      {/* pectoral fin */}
      <path d="M96 62 C 76 80, 54 92, 40 90 C 56 74, 70 62, 90 54 Z" fill="currentColor" fillOpacity="0.85" />

      {/* eye */}
      <circle cx="26" cy="42" r="4.5" fill="var(--bg-page)" />

      {/* spot pattern, back half of the body */}
      <g fill="var(--bg-page)" fillOpacity="0.55">
        <circle cx="64" cy="28" r="3.2" />
        <circle cx="84" cy="24" r="2.4" />
        <circle cx="106" cy="27" r="3" />
        <circle cx="128" cy="24" r="2.2" />
        <circle cx="74" cy="40" r="2.2" />
        <circle cx="96" cy="42" r="2.8" />
        <circle cx="118" cy="39" r="2" />
        <circle cx="142" cy="32" r="2.6" />
        <circle cx="160" cy="40" r="2.2" />
        <circle cx="150" cy="52" r="2" />
        <circle cx="130" cy="55" r="2.4" />
        <circle cx="108" cy="58" r="2" />
      </g>
    </svg>
  );
}
