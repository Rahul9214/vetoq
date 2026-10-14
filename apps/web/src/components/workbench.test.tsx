import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { Me } from "@/lib/contracts";
import { confirmationLabel, Workbench } from "./workbench";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", () => ({ api: vi.fn() }));

const identity: Me = {
  principal: "user_fixture",
  access: "active",
  workspaces: [
    {
      id: "00000000-0000-4000-8000-00000000000a",
      name: "Demo support",
      role: "reviewer",
      policy_revision: "support-triage/1",
    },
  ],
  template: {
    id: "support-triage/1",
    tool: "tickets.create",
    destination: "local-ticket-store",
    max_writes: 1,
    expires_minutes: 30,
  },
};

const formatLabels = [
  "Plain text",
  "JSON",
  "Markdown",
  "HTML",
  "Email (RFC822)",
] as const;

function mockIdentity() {
  vi.mocked(api).mockImplementation(async (path: string) => {
    if (path === "/me") return identity;
    if (path.startsWith("/runs?")) return { items: [] };
    throw new Error("unexpected_call");
  });
}

async function renderReady() {
  mockIdentity();
  render(<Workbench />);
  return screen.findByLabelText("Declared format");
}

describe("authenticated security workbench", () => {
  beforeEach(() => {
    push.mockReset();
    vi.mocked(api).mockReset();
  });

  it("renders only server-authorized workspace state", async () => {
    await renderReady();
    expect(
      screen.getByRole("heading", { name: "What this run may accomplish" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Authority granted for that goal" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Demo support").length).toBeGreaterThan(0);
    expect(screen.getByText("tickets.create")).toBeInTheDocument();
    expect(screen.getByText("local-ticket-store")).toBeInTheDocument();
    expect(screen.getByText("reviewer")).toBeInTheDocument();
    expect(screen.getByText("support-triage/1")).toBeInTheDocument();
  });

  it("keeps a verified but unprovisioned identity out of the workbench", async () => {
    vi.mocked(api).mockResolvedValue({
      ...identity,
      access: "not_provisioned",
      workspaces: [],
    });
    render(<Workbench />);
    expect(
      await screen.findByRole("heading", {
        name: "No VETOQ workspace membership",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Untrusted business content"),
    ).not.toBeInTheDocument();
  });

  it("surfaces persistence failure and does not accept source content", async () => {
    vi.mocked(api).mockRejectedValue(new Error("database_not_configured"));
    render(<Workbench />);
    expect(
      await screen.findByRole("heading", {
        name: "The authenticated workspace could not be opened.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("database_not_configured")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Untrusted business content"),
    ).not.toBeInTheDocument();
  });

  it("exposes exactly the five declared formats", async () => {
    const format = await renderReady();
    format.focus();
    expect(format).toHaveFocus();
    const options = within(format);
    for (const label of formatLabels) {
      expect(options.getByRole("option", { name: label })).toBeInTheDocument();
    }
    expect(options.getAllByRole("option")).toHaveLength(
      formatLabels.length + 1,
    );
    expect(
      options.queryByRole("option", {
        name: /PDF|DOCX|image|audio|URL|Auto detect/i,
      }),
    ).toBeNull();
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(
      screen.queryByText(/upload document|attach file|drop zone/i),
    ).toBeNull();
  });

  it("shows contextual guidance and keeps the source when the format changes", async () => {
    const format = await renderReady();
    const source = screen.getByLabelText("Untrusted business content");
    const sentinel = "KEEP_THIS_SOURCE";
    fireEvent.change(source, { target: { value: sentinel } });
    const guidance = [
      ["text/plain", "Ordinary pasted text."],
      [
        "application/json",
        "Strict JSON. Duplicate keys and malformed structures are rejected.",
      ],
      ["text/markdown", "Markdown stays untrusted text and is not rendered."],
      [
        "text/html",
        "HTML stays inert. Scripts and resources are not executed.",
      ],
      [
        "message/rfc822",
        "Paste raw RFC822 or MIME source. Unsupported attachments are rejected.",
      ],
    ] as const;
    for (const [value, text] of guidance) {
      fireEvent.change(format, { target: { value } });
      expect(screen.getByText(text)).toBeInTheDocument();
      expect(source).toHaveValue(sentinel);
    }
  });

  it("submits the exact confirmed contract and routes to the persisted run", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/me") return identity;
      if (path.startsWith("/runs?")) return { items: [] };
      if (path === "/runs") return { id: "run-persisted" };
      throw new Error("unexpected_call");
    });
    render(<Workbench />);
    const source = await screen.findByLabelText("Untrusted business content");
    fireEvent.change(await screen.findByLabelText("Declared format"), {
      target: { value: "text/plain" },
    });
    fireEvent.change(source, {
      target: { value: "Synthetic support request: cannot access the portal." },
    });
    expect(
      screen.getByRole("button", { name: /Start guarded analysis/ }),
    ).toBeDisabled();
    fireEvent.click(screen.getByLabelText(confirmationLabel));
    fireEvent.click(
      screen.getByRole("button", { name: /Start guarded analysis/ }),
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/runs/run-persisted"),
    );
    const submitCall = vi
      .mocked(api)
      .mock.calls.find(([path]) => path === "/runs");
    expect(submitCall?.[1]?.method).toBe("POST");
    expect(
      (submitCall?.[1]?.headers as Record<string, string>)["Idempotency-Key"],
    ).toBeTruthy();
    const body = JSON.parse(String(submitCall?.[1]?.body)) as Record<
      string,
      unknown
    >;
    expect(Object.keys(body).sort()).toEqual([
      "confirmed",
      "goal",
      "media_type",
      "source",
      "workspace_id",
    ]);
    expect(body.confirmed).toBe(true);
    expect(body.media_type).toBe("text/plain");
    expect(body.workspace_id).toBe(identity.workspaces[0]?.id);
    expect(body).not.toHaveProperty("sanitized");
    expect(body).not.toHaveProperty("template");
    expect(body).not.toHaveProperty("source_class");
    expect(body).not.toHaveProperty("trust");
    expect(body).not.toHaveProperty("parser_id");
    expect(body).not.toHaveProperty("parser_version");
    expect(body).not.toHaveProperty("channel");
  });

  it("stays disabled until a format is chosen and the submission is confirmed", async () => {
    await renderReady();
    const button = screen.getByRole("button", {
      name: /Start guarded analysis/,
    });
    expect(button).toBeDisabled();
    expect(
      screen.getByText("Choose a declared format to continue."),
    ).toBeInTheDocument();
    fireEvent.click(button);
    fireEvent.click(screen.getByLabelText(confirmationLabel));
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByLabelText(confirmationLabel));
    fireEvent.change(screen.getByLabelText("Declared format"), {
      target: { value: "text/plain" },
    });
    expect(button).toBeDisabled();
    expect(
      screen.getByText(
        "Confirm the goal, the authority, and this untrusted submission.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(confirmationLabel));
    expect(button).toBeEnabled();
    expect(screen.getByText("The submission can be sent.")).toBeInTheDocument();
    expect(vi.mocked(api).mock.calls.some(([path]) => path === "/runs")).toBe(
      false,
    );
  });

  it("shows Submitting while the request is in flight", async () => {
    let release: (value: { id: string }) => void = () => undefined;
    const pending = new Promise<{ id: string }>((resolve) => {
      release = resolve;
    });
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/me") return identity;
      if (path.startsWith("/runs?")) return { items: [] };
      if (path === "/runs") return pending;
      throw new Error("unexpected_call");
    });
    render(<Workbench />);
    fireEvent.change(await screen.findByLabelText("Declared format"), {
      target: { value: "text/plain" },
    });
    fireEvent.change(screen.getByLabelText("Untrusted business content"), {
      target: { value: "A note." },
    });
    fireEvent.click(screen.getByLabelText(confirmationLabel));
    fireEvent.click(
      screen.getByRole("button", { name: /Start guarded analysis/ }),
    );
    expect(
      await screen.findByRole("button", { name: "Submitting…" }),
    ).toBeDisabled();
    release({ id: "run-pending" });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/run-pending"));
  });

  it("keeps pasted HTML inert in the editor", async () => {
    const format = await renderReady();
    const markup = '<img src=x onerror="alert(1)"><script>bad()</script>';
    fireEvent.change(format, { target: { value: "text/html" } });
    fireEvent.change(screen.getByLabelText("Untrusted business content"), {
      target: { value: markup },
    });
    expect(screen.getByLabelText("Untrusted business content")).toHaveValue(
      markup,
    );
    expect(document.querySelector("img")).toBeNull();
    expect(
      screen.getByText(/Scripts and resources are not executed/),
    ).toBeInTheDocument();
  });

  it.each([
    ["malformed_content", "This content does not match the declared format."],
    [
      "unsupported_embedded_content",
      "An embedded part, charset, or transfer encoding in this message is not accepted.",
    ],
    [
      "idempotency_conflict",
      "This submission key was already used for a different goal, format, or content.",
    ],
  ])("shows %s without reflecting the source", async (code, message) => {
    const sentinel = `SENTINEL_${code}`;
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/me") return identity;
      if (path.startsWith("/runs?")) return { items: [] };
      if (path === "/runs") throw new Error(code);
      throw new Error("unexpected_call");
    });
    render(<Workbench />);
    fireEvent.change(await screen.findByLabelText("Declared format"), {
      target: { value: "application/json" },
    });
    fireEvent.change(screen.getByLabelText("Untrusted business content"), {
      target: { value: sentinel },
    });
    fireEvent.click(screen.getByLabelText(confirmationLabel));
    fireEvent.click(
      screen.getByRole("button", { name: /Start guarded analysis/ }),
    );
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).toHaveTextContent(code);
    expect(alert).not.toHaveTextContent(sentinel);
    expect(screen.getByLabelText("Untrusted business content")).toHaveValue(
      sentinel,
    );
    expect(push).not.toHaveBeenCalled();
  });
});
