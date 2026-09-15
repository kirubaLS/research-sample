import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "node",
    // Dexie needs an IndexedDB. fake-indexeddb provides a real implementation of the spec
    // rather than a stub, so the page store is exercised through the same code path the
    // browser uses -- a mock would have let a wrong transaction pass.
    setupFiles: ["fake-indexeddb/auto"],
    include: ["lib/**/*.test.ts"],
  },
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
});
