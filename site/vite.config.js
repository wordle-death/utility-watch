import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// SINGLE_FILE=1 builds one self-contained HTML file, used for private previews.
// SITE_URL (the public address) fills in the share-preview tags on the live build.
// CF_BEACON is Cloudflare Web Analytics' site token; without it no analytics script is added.
const siteUrl = (process.env.SITE_URL || "").replace(/\/$/, "");
const beacon = process.env.CF_BEACON || "";

function headTags() {
  return {
    name: "head-tags",
    transformIndexHtml() {
      const tags = [];
      if (siteUrl) {
        tags.push(
          { tag: "meta", attrs: { property: "og:url", content: `${siteUrl}/` }, injectTo: "head" },
          { tag: "meta", attrs: { property: "og:image", content: `${siteUrl}/share.png` }, injectTo: "head" },
          { tag: "meta", attrs: { name: "twitter:image", content: `${siteUrl}/share.png` }, injectTo: "head" },
        );
      }
      if (beacon) {
        // Counts visits without cookies or tracking individuals.
        tags.push({
          tag: "script",
          attrs: { defer: true, src: "https://static.cloudflareinsights.com/beacon.min.js",
                   "data-cf-beacon": JSON.stringify({ token: beacon }) },
          injectTo: "body",
        });
      }
      return tags;
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), headTags(), ...(process.env.SINGLE_FILE ? [viteSingleFile()] : [])],
});
