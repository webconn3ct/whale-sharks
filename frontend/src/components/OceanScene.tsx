interface Critter {
  top: string;
  size: number;
  duration: number;
  delay: number;
  reverse?: boolean;
  kind: "shark" | "fish";
}

// Deliberately plain silhouettes — these read as shadows deep in the water,
// not a second logo, so no gradients/texture/detail here on purpose.
function SharkShape() {
  return (
    <svg viewBox="0 0 220 55" width="100%" height="100%">
      <path d="M2 27C2 14 22 4 58 3C98 1 145 9 182 24C188 26 188 28 182 30C145 45 98 53 58 51C22 50 2 40 2 27Z" />
      <path d="M182 24L220 5L186 26L220 47L182 30Z" />
      <path d="M70 3L78 -14L92 3Z" />
    </svg>
  );
}

function FishShape() {
  return (
    <svg viewBox="0 0 26 12" width="100%" height="100%">
      <path d="M0 6C0 2.5 4 0 10 0C15 0 19 2.5 20 6L26 0L21 6L26 12L20 6C19 9.5 15 12 10 12C4 12 0 9.5 0 6Z" />
    </svg>
  );
}

// A handful of sharks each trailed by a small scatter of fish — suggests the
// whale sharks are feeding as they cross, without literally animating a bite.
// Plus extra loose fish/schools scattered at other depths for more life.
const CRITTERS: Critter[] = [
  { kind: "shark", top: "12%", size: 260, duration: 46, delay: -6, reverse: false },
  { kind: "fish", top: "13.5%", size: 34, duration: 46, delay: -6 },
  { kind: "fish", top: "10.5%", size: 28, duration: 46, delay: -4.5 },
  { kind: "shark", top: "62%", size: 190, duration: 58, delay: -20, reverse: true },
  { kind: "fish", top: "63%", size: 26, duration: 58, delay: -20 },
  { kind: "fish", top: "60%", size: 22, duration: 58, delay: -18.5 },
  { kind: "shark", top: "38%", size: 140, duration: 70, delay: -35, reverse: false },
  { kind: "fish", top: "39%", size: 20, duration: 70, delay: -35 },
  { kind: "shark", top: "82%", size: 220, duration: 52, delay: -10, reverse: true },
  { kind: "fish", top: "83%", size: 30, duration: 52, delay: -10 },
  { kind: "fish", top: "80.5%", size: 24, duration: 52, delay: -8.5 },
  // extra loose fish/schools, independent of the sharks
  { kind: "fish", top: "5%", size: 18, duration: 40, delay: -2, reverse: true },
  { kind: "fish", top: "7%", size: 16, duration: 40, delay: -3.5, reverse: true },
  { kind: "fish", top: "24%", size: 22, duration: 64, delay: -12 },
  { kind: "fish", top: "26%", size: 18, duration: 64, delay: -14 },
  { kind: "fish", top: "27.5%", size: 15, duration: 64, delay: -16 },
  { kind: "fish", top: "48%", size: 24, duration: 50, delay: -25, reverse: true },
  { kind: "fish", top: "50%", size: 19, duration: 50, delay: -27, reverse: true },
  { kind: "fish", top: "70%", size: 20, duration: 60, delay: -5 },
  { kind: "fish", top: "72%", size: 17, duration: 60, delay: -7 },
  { kind: "fish", top: "90%", size: 26, duration: 44, delay: -30, reverse: true },
  { kind: "fish", top: "92%", size: 20, duration: 44, delay: -32, reverse: true },
  { kind: "fish", top: "94%", size: 16, duration: 44, delay: -33.5, reverse: true },
];

export function OceanScene() {
  return (
    <div className="ocean-scene" aria-hidden="true">
      {CRITTERS.map((c, i) => (
        <div
          key={i}
          className="ocean-critter"
          style={{
            top: c.top,
            width: c.size,
            height: c.size * (c.kind === "shark" ? 55 / 220 : 12 / 26),
            animationDuration: `${c.duration}s`,
            animationDelay: `${c.delay}s`,
            animationName: c.reverse ? "swim-across-reverse" : "swim-across",
          }}
        >
          {c.kind === "shark" ? <SharkShape /> : <FishShape />}
        </div>
      ))}
    </div>
  );
}
