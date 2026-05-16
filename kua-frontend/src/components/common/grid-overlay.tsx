export function GridOverlay() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 grid-bg mask-fade-b opacity-40"
    />
  );
}

export function RadialGlow() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 bg-radial-glow"
    />
  );
}
