export const dynamic = "force-static";

export default function robots() {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://darwin-protocol.github.io/darwin";
  return {
    rules: {
      userAgent: "*",
      allow: "/",
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
