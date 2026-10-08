import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "VETOQ — Trust the Goal. Verify the Action.",
  description:
    "VETOQ application foundation. Security workflows are not yet available.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content" tabIndex={0}>
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
