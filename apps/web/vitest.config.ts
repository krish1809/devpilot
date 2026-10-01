import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  // Next's tsconfig keeps JSX as-is ("preserve"); tests need it compiled.
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
  test: {
    // API-client tests run in node; component tests opt into jsdom per file.
    environment: "node",
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
