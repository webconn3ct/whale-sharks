interface Props {
  size?: number;
  className?: string;
}

const VIEW_RATIO = 165 / 310;

/** Whale shark side-profile mark: swept dorsal fin, forked tail, red gill
 * slashes, white belly and spot pattern on a navy-to-black gradient body. */
export function WhaleSharkLogo({ size = 40, className }: Props) {
  return (
    <svg
      width={size}
      height={size * VIEW_RATIO}
      viewBox="0 -30 310 165"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="Whale Sharks logo"
    >
      <defs>
        <linearGradient id="ws-body" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1c3a63" />
          <stop offset="55%" stopColor="#0f1f38" />
          <stop offset="100%" stopColor="#050508" />
        </linearGradient>
        <linearGradient id="ws-fin" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#14284a" />
          <stop offset="100%" stopColor="#020204" />
        </linearGradient>
      </defs>

      {/* tail fin, drawn first so the body overlaps its base */}
      <path d="M214 50 L 296 6 L 224 55 Z" fill="url(#ws-fin)" />
      <path d="M214 65 L 296 108 L 224 60 Z" fill="url(#ws-fin)" />

      {/* body: tapered, pointed snout */}
      <path
        d="M4 58
           C 4 40, 20 24, 48 19
           C 92 11, 160 12, 205 28
           C 216 32, 222 40, 226 49
           L 226 51
           C 220 52, 220 55, 226 56
           L 226 58
           C 222 67, 216 75, 205 79
           C 160 95, 92 96, 48 88
           C 20 83, 4 76, 4 58 Z"
        fill="url(#ws-body)"
      />

      {/* white belly crescent */}
      <path
        d="M14 66
           C 40 82, 100 90, 160 87
           C 130 91, 70 90, 34 78
           C 22 74, 15 70, 14 66 Z"
        fill="#f2f4f7"
        fillOpacity="0.9"
      />

      {/* dorsal fin: swept-back, sharp apex */}
      <path d="M110 20 C 112 4, 116 -14, 123 -27 C 135 -15, 147 2, 156 20 Z" fill="url(#ws-fin)" />
      {/* pectoral fin */}
      <path
        d="M108 68 C 84 92, 56 106, 38 102 C 58 82, 76 68, 100 58 Z"
        fill="url(#ws-fin)"
        fillOpacity="0.92"
      />

      {/* red gill slashes */}
      <g stroke="#c81c2a" strokeWidth="3" strokeLinecap="round">
        <path d="M40 40 L 34 54" />
        <path d="M47 38 L 42 54" />
        <path d="M54 37 L 50 54" />
      </g>

      {/* eye */}
      <circle cx="22" cy="46" r="5" fill="#050508" />
      <circle cx="20.5" cy="44.5" r="1.4" fill="#c81c2a" />

      {/* spot pattern */}
      <g fill="#f2f4f7" fillOpacity="0.5">
        <circle cx="72" cy="30" r="3.4" />
        <circle cx="94" cy="25" r="2.6" />
        <circle cx="118" cy="28" r="3.2" />
        <circle cx="142" cy="24" r="2.4" />
        <circle cx="82" cy="42" r="2.4" />
        <circle cx="106" cy="44" r="3" />
        <circle cx="130" cy="41" r="2.2" />
        <circle cx="158" cy="33" r="2.8" />
        <circle cx="178" cy="42" r="2.4" />
        <circle cx="166" cy="55" r="2.2" />
        <circle cx="144" cy="58" r="2.6" />
        <circle cx="120" cy="62" r="2.2" />
        <circle cx="188" cy="30" r="2" />
        <circle cx="196" cy="45" r="2.2" />
      </g>
    </svg>
  );
}
