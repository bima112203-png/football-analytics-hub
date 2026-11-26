export default function DesignSystemPage() {
  return (
    <div className="space-y-8">
      <div className="border-b border-[var(--border-subtle)] pb-4">
        <h1 className="text-xl font-bold tracking-tight">Design System — Formetric</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Token tipografi (IBM Plex Sans + tabular-nums), palet netral dengan satu aksen tegas, dan komponen status.
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-muted)]">Palet &amp; Token Warna</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
            <div className="h-8 rounded bg-[var(--bg-canvas)] border border-[var(--border-subtle)]" />
            <div className="mt-2 text-xs font-medium">--bg-canvas</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
            <div className="h-8 rounded bg-[var(--accent)]" />
            <div className="mt-2 text-xs font-medium">--accent (Tunggal)</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
            <div className="h-8 rounded bg-[var(--form-win)]" />
            <div className="mt-2 text-xs font-medium">--form-win</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
            <div className="h-8 rounded bg-[var(--form-loss)]" />
            <div className="mt-2 text-xs font-medium">--form-loss</div>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-muted)]">Tipografi &amp; Tabular Nums</h2>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 space-y-2">
          <div className="text-lg font-semibold">Heading Utama Pertandingan (18px Semibold)</div>
          <div className="tabular-nums text-sm">Skor &amp; Probabilitas: 2 - 1 | 58.4% / 23.1% / 18.5%</div>
        </div>
      </section>
    </div>
  );
}
