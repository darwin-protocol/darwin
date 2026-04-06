import Link from "next/link";
import BrandMark from "./BrandMark";

export default function SiteHeader({ compact = false }) {
  return (
    <header className={`site-header${compact ? " compact" : ""}`}>
      <Link className="brand-lockup" href="/">
        <BrandMark className="brand-mark" title="Use Darwin" />
        <div>
          <strong>Use Darwin</strong>
          <span>Live Base Sepolia DRW market</span>
        </div>
      </Link>
      <nav className="site-nav" aria-label="Primary">
        <Link className="nav-link" href="/">
          Home
        </Link>
        <Link className="nav-link" href="/trade/">
          Trade
        </Link>
        <a
          className="nav-link"
          href="https://github.com/darwin-protocol/darwin/blob/main/LIVE_STATUS.md"
          target="_blank"
          rel="noreferrer"
        >
          Live status
        </a>
        <a
          className="nav-link"
          href="https://github.com/darwin-protocol/darwin"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>
      </nav>
    </header>
  );
}
