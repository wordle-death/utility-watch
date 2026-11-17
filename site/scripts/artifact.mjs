// Turn the single-file build into a page fragment for a private preview:
// the preview host supplies its own <html>, <head> and <body>.
import { readFileSync, writeFileSync } from "node:fs";
const html = readFileSync(new URL("../dist-preview/index.html", import.meta.url), "utf8");
const pick = (re) => (html.match(re) || []).join("\n");
const out = [
  pick(/<title>[\s\S]*?<\/title>/),
  '<meta name="claude:viewport-fit-sides" content="cover">',
  pick(/<link rel="stylesheet"[^>]*>/g),
  pick(/<style[\s\S]*?<\/style>/g),
  '<div id="root"></div>',
  pick(/<script[\s\S]*?<\/script>/g),
].join("\n");
writeFileSync(new URL("../dist-preview/preview.html", import.meta.url), out);
console.log("preview.html", out.length, "bytes");
