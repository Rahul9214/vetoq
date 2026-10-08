export default function Home() {
  return (
    <div className="app-frame flex min-h-svh flex-col">
      <header className="shell-container flex flex-wrap items-center justify-between gap-4 border-b border-line py-6">
        <p className="brand" aria-label="VETOQ">
          VETOQ<span aria-hidden="true">/</span>
        </p>
        <p className="eyebrow">Application foundation</p>
      </header>
      <main
        id="main-content"
        tabIndex={-1}
        className="shell-container flex flex-1 flex-col justify-center py-16 sm:py-24"
      >
        <p className="eyebrow mb-6">Trust &amp; execution</p>
        <h1 className="headline">
          Trust the Goal.
          <br />
          <span className="text-jade">Verify the Action.</span>
        </h1>
        <p className="intro mt-8">
          A considered foundation for accountable AI actions.
        </p>
        <section
          aria-labelledby="foundation-title"
          className="foundation-note mt-12"
        >
          <h2 id="foundation-title" className="text-base font-semibold">
            Foundation only
          </h2>
          <p className="mt-2 text-muted">
            Security workflows are not available in this build.
          </p>
        </section>
      </main>
      <footer className="shell-container flex flex-wrap justify-between gap-3 border-t border-line py-6 text-sm text-muted">
        <p>VETOQ</p>
        <p>Trust the Goal. Verify the Action.</p>
      </footer>
    </div>
  );
}
