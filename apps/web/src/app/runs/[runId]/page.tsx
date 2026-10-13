import { AppHeader } from "@/components/app-header";
import { RunView } from "@/components/run-view";

export default async function RunPage({ params }: PageProps<"/runs/[runId]">) {
  const { runId } = await params;
  return (
    <div className="console-frame">
      <AppHeader mode="console" />
      <main id="main-content" tabIndex={-1} className="detail-main page-shell">
        <RunView runId={runId} />
      </main>
      <footer className="console-footer page-shell">
        <span>VETOQ</span>
        <span>Persistent security evidence</span>
      </footer>
    </div>
  );
}
