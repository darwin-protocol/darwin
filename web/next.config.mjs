const rawDomain = (process.env.DARWIN_SITE_DOMAIN || "").trim();
const rawBasePath = (process.env.DARWIN_SITE_BASE_PATH || "").trim();
const isProd = process.env.NODE_ENV === "production";

function normalizeBasePath(value) {
  if (!value || value === "/") return "";
  return value.startsWith("/") ? value.replace(/\/$/, "") : `/${value.replace(/\/$/, "")}`;
}

const basePath = !isProd ? "" : rawDomain ? "" : normalizeBasePath(rawBasePath || "/darwin");
const siteUrl = rawDomain
  ? `https://${rawDomain}`
  : `https://darwin-protocol.github.io${basePath || "/darwin"}`;

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  basePath,
  assetPrefix: basePath || undefined,
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
    NEXT_PUBLIC_SITE_URL: siteUrl,
  },
};

export default nextConfig;
