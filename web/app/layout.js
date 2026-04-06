import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://darwin-protocol.github.io/darwin";

export const metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Darwin Protocol",
    template: "%s | Darwin Protocol",
  },
  description:
    "Peer-to-peer market infrastructure with a live Base Sepolia DRW token, faucet, and reference pool.",
  openGraph: {
    title: "Darwin Protocol",
    description:
      "Peer-to-peer market infrastructure with a live Base Sepolia DRW token, faucet, and reference pool.",
    url: siteUrl,
    siteName: "Darwin Protocol",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Darwin Protocol",
    description:
      "Peer-to-peer market infrastructure with a live Base Sepolia DRW token, faucet, and reference pool.",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
