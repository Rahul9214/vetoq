import { AppHeader } from "@/components/app-header";
import { TicketView } from "@/components/ticket-view";

export default async function TicketPage({
  params,
}: PageProps<"/tickets/[ticketId]">) {
  const { ticketId } = await params;
  return (
    <div className="console-frame">
      <AppHeader mode="console" />
      <main id="main-content" tabIndex={-1} className="detail-main page-shell">
        <TicketView ticketId={ticketId} />
      </main>
      <footer className="console-footer page-shell">
        <span>VETOQ</span>
        <span>Verified local outcome</span>
      </footer>
    </div>
  );
}
