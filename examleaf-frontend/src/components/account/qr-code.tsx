// A QR code drawn as SVG from its text (lean-qr, 3.5 KB, no image service: the authenticator app's otpauth:// link
// holds a secret): the dark runs of each row as one path, 4 modules of quiet zone on white. Server or client alike.
import { generate } from "lean-qr";

export function QrCode({ text, label, size = 176 }: { text: string; label: string; size?: number }) {
  const code = generate(text);
  let path = "";
  for (let y = 0; y < code.size; y++) {
    for (let x = 0; x < code.size; x++) {
      if (!code.get(x, y)) continue;
      const start = x;
      while (x + 1 < code.size && code.get(x + 1, y)) x++;
      path += `M${start} ${y}h${x - start + 1}v1h-${x - start + 1}z`;
    }
  }
  const side = code.size + 8;
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`-4 -4 ${side} ${side}`}
      width={size}
      height={size}
      shapeRendering="crispEdges"
      className="flex-none border border-border bg-white"
    >
      <path d={path} fill="#000" />
    </svg>
  );
}
