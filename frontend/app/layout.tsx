import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Yaadhum",
  description: "Assessment diagnostics for CBSE schools",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
