import type { Metadata } from "next";
import { JetBrains_Mono, Manrope, Source_Sans_3 } from "next/font/google";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

// Manrope, not the old serif (Spectral): a premium EdTech dashboard reads as friendly and
// modern with a clean sans throughout, headings included -- a serif display face is the
// one thing that would make this look like a print report rather than a product.
const display = Manrope({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-display",
  display: "swap",
});
const body = Source_Sans_3({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-body",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Yaadhum",
  description: "Assessment diagnostics for CBSE schools",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>
        <div className="shell">
          <SiteHeader />
          {children}
          <footer className="sitefooter">
            <div className="inner">
              <span>Yaadhum · assessment diagnostics</span>
              <span className="mono">CBSE Class X · Tamil Nadu</span>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
