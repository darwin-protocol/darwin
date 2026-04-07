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

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://usedarwin.xyz";
const siteDescription =
  "Claim testnet DRW and start with a tiny first swap on the live Base Sepolia DARWIN reference pool.";
const socialImage = "/og-card.png";

export const metadata = {
  metadataBase: new URL(siteUrl),
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
    images: [{ url: socialImage, width: 1200, height: 630, alt: "Use Darwin DRW market" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Use Darwin",
    description: siteDescription,
    images: [socialImage],
  },
  icons: {
    icon: "/icon.svg",
    shortcut: "/icon.svg",
    apple: "/icon.svg",
  },
};

export const viewport = {
  themeColor: "#f4efe5",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
