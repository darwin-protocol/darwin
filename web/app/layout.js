import Link from "next/link";
import { Fraunces, IBM_Plex_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
});

const accent = Fraunces({
  subsets: ["latin"],
  variable: "--font-accent",
  weight: ["600", "700"],
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://usedarwin.xyz";
const siteDescription =
  "Claim DRW, make a tiny first swap, and track live Darwin market activity across the public Base and Arbitrum testnet lanes.";
const socialImage = "/og-card.png";
const baseAppId = process.env.DARWIN_BASE_APP_ID || "";

export const metadata = {
  metadataBase: new URL(siteUrl),
  manifest: "/manifest.webmanifest",
  title: {
    default: "Use Darwin",
    template: "%s | Use Darwin",
  },
  description: siteDescription,
  applicationName: "Use Darwin",
  openGraph: {
    title: "Use Darwin",
    description: siteDescription,
    url: siteUrl,
    siteName: "Use Darwin",
    type: "website",
    images: [{ url: socialImage, width: 1200, height: 630, alt: "DRW coin and Darwin market lanes" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Use Darwin",
    description: siteDescription,
    images: [socialImage],
  },
  icons: {
    icon: "/drw-logo.svg",
    shortcut: "/drw-logo.svg",
    apple: "/drw-logo.svg",
  },
  other: baseAppId
    ? {
        "base:app_id": baseAppId,
      }
    : undefined,
};

export const viewport = {
  themeColor: "#f7f0e5",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${display.variable} ${accent.variable} ${mono.variable}`}>
      <body>
        <div className="site-chrome">
          <header className="site-header">
            <div className="site-header-inner">
              <Link className="site-brand" href="/">
                <img className="site-brand-mark" src="/drw-logo.svg" alt="Darwin logo" width="44" height="44" />
                <span className="site-brand-copy">
                  <strong>Use Darwin</strong>
                  <span>Public DRW market lanes</span>
                </span>
              </Link>

              <nav className="site-nav" aria-label="Primary">
                <Link href="/trade/">Market</Link>
                <Link href="/activity/">Activity</Link>
                <Link href="/epoch/">Epoch</Link>
                <Link href="/join/">Join</Link>
                <Link href="/search/">Search</Link>
              </nav>

              <div className="site-meta">
                <span className="site-pill">Base + Arbitrum testnet</span>
                <a
                  className="site-header-cta"
                  href="https://github.com/darwin-protocol/darwin"
                  target="_blank"
                  rel="noreferrer"
                >
                  GitHub
                </a>
              </div>
            </div>
          </header>

          <div className="site-main">{children}</div>

          <footer className="site-footer">
            <div className="site-footer-inner">
              <div className="site-footer-intro">
                <p className="eyebrow">DARWIN SURFACE</p>
                <h2>Make the first action obvious.</h2>
                <p>
                  Claim DRW, use a tiny preset, and verify the result on a public lane. Darwin is
                  still testnet alpha, but the surface is now shaped like a product instead of a raw
                  dashboard.
                </p>
              </div>

              <div className="site-footer-links">
                <span className="label">Surface</span>
                <Link href="/trade/">Trade DRW</Link>
                <Link href="/activity/">Live activity</Link>
                <Link href="/epoch/">Current epoch</Link>
              </div>

              <div className="site-footer-links">
                <span className="label">Docs</span>
                <a
                  href="https://github.com/darwin-protocol/darwin/blob/main/docs/DARWIN_NODE.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  Darwin node
                </a>
                <a
                  href="https://github.com/darwin-protocol/darwin/blob/main/docs/MARKET_BOOTSTRAP.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  Market bootstrap
                </a>
                <a
                  href="https://github.com/darwin-protocol/darwin/blob/main/LIVE_STATUS.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  Live status
                </a>
              </div>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
