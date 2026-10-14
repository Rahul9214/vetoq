import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SkipLink } from "@/components/skip-link";
import "./globals.css";
import "./vetoq.css";
import "./public-experience.css";

export const metadata: Metadata = {
  title: {
    default: "VETOQ — Trust the Goal. Verify the Action.",
    template: "%s · VETOQ",
  },
  description:
    "Execution security that binds AI-proposed actions to confirmed user authority.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ClerkProvider
          appearance={{
            variables: {
              colorPrimary: "#6d28a8",
              colorBackground: "#fcfaf6",
              colorForeground: "#1c1917",
              colorMutedForeground: "#645e56",
              colorInput: "#ffffff",
              colorInputForeground: "#1c1917",
              colorDanger: "#be123c",
              colorNeutral: "#f7f4ec",
              borderRadius: "12px",
              fontFamily: '"Segoe UI Variable", "Segoe UI", sans-serif',
            },
            elements: {
              rootBox: "vetoq-clerk-root",
              cardBox: "vetoq-clerk-card-box",
              card: "vetoq-clerk-card",
              headerTitle: "vetoq-clerk-title",
              headerSubtitle: "vetoq-clerk-subtitle",
              socialButtonsBlockButton: "vetoq-clerk-social",
              socialButtonsBlockButtonText: "vetoq-clerk-social-text",
              dividerLine: "vetoq-clerk-divider",
              dividerText: "vetoq-clerk-divider-text",
              formFieldInput: "vetoq-clerk-input",
              formButtonPrimary: "vetoq-clerk-primary",
              footer: "vetoq-clerk-footer",
              footerActionLink: "vetoq-clerk-link",
            },
          }}
        >
          <SkipLink />
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
