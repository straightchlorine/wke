import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../../backend/api/openapi.yaml",
  output: "src/api/generated",
  parser: {
    filters: {
      tags: {
        exclude: ["internal"],
      },
    },
  },
});
