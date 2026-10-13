// src/components/layout/PageBackground.tsx

/** The grid and glow behind every page; content goes above it (relative z-10) */
export function PageBackground(): JSX.Element {
  return (
    <>
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
    </>
  );
}
