export const dynamic = "force-static";

export default function manifest() {
  return {
    name: "Use Darwin",
    short_name: "Darwin",
    description:
      "Claim DRW, make a tiny first swap, and track live Darwin market activity across the public Base and Arbitrum testnet lanes.",
    start_url: "/",
    display: "standalone",
    background_color: "#f4efe5",
    theme_color: "#f4efe5",
    categories: ["finance", "utilities"],
    shortcuts: [
      {
        name: "Join Starter Cohort",
        short_name: "Join",
        url: "/join/",
      },
      {
        name: "Tiny Swap",
        short_name: "Trade",
        url: "/trade/?preset=tiny-sell",
      },
      {
        name: "Live Activity",
        short_name: "Activity",
        url: "/activity/",
      },
    ],
    icons: [
      {
        src: "/drw-logo.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
