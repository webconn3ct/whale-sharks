interface Props {
  size?: number;
  className?: string;
}

/** Small curled krill mark — KrillBot's icon, drawn in the accent color so it
 * sits naturally in the dark financial-terminal UI. */
export function KrillIcon({ size = 20, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="KrillBot"
    >
      {/* curled body */}
      <path
        d="M10 30
           C 6 24, 8 14, 17 10
           C 26 6, 36 10, 38 19
           C 39.5 26, 35 31, 28 31.5
           C 22.5 32, 18.5 28.5, 19.5 24
           C 20.3 20.5, 24 19, 27 21"
        stroke="var(--accent)"
        strokeWidth="3.4"
        strokeLinecap="round"
        fill="none"
      />

      {/* shell segment lines */}
      <g stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" opacity="0.55">
        <path d="M14 26 L 17.5 22.5" />
        <path d="M12 21 L 16 18.5" />
        <path d="M14.5 16 L 18.5 14.5" />
      </g>

      {/* tail fan */}
      <path
        d="M9 30 L 3 27 M9 30 L 3 32 M9 30 L 4 34"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.85"
      />

      {/* antennae */}
      <path d="M36 17 C 40 14, 43 10, 44 6" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" opacity="0.7" />
      <path d="M37.5 20.5 C 42 19, 46 17, 47.5 14" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" opacity="0.7" />

      {/* tiny legs */}
      <g stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" opacity="0.6">
        <path d="M22 24 L 20 28" />
        <path d="M26 25 L 25 29" />
        <path d="M30 24.5 L 30 28.5" />
      </g>

      {/* eye */}
      <circle cx="35" cy="16" r="2.2" fill="var(--accent)" />
    </svg>
  );
}
