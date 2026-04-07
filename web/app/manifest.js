export const dynamic = "force-static";

export default function manifest() {
  return {
    name: "Use Darwin",
    short_name: "Darwin",
    description:
      "Claim DRW, use a tiny first swap, and follow live DARWIN contract activity across the public Darwin lanes.",
    start_url: "/",
    display: "standalone",
    background_color: "#f4efe5",
    theme_color: "#f4efe5",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
