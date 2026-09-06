import type { Metadata } from "next";
import { JetBrains_Mono, Source_Sans_3, Spectral } from "next/font/google";
import { SiteHeader } from "@/components/SiteHeader";
import { Tilt3D } from "@/components/Tilt3D";
import "./globals.css";

const display = Spectral({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
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
          <Tilt3D />
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
