import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// SINGLE_FILE=1 builds one self-contained HTML file, used for private previews.
export default defineConfig({
  plugins: [react(), tailwindcss(), ...(process.env.SINGLE_FILE ? [viteSingleFile()] : [])],
});
