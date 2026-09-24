import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "AVAI, Board-ready school intelligence",
  description:
    "AVAI turns every school test into board-ready intelligence: where each class is losing marks, which students need attention now, and what to teach next. For principals, teachers and students.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
