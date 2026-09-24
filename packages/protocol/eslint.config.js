import base from "@jarvis/config/eslint";
import { defineConfig } from "eslint/config";

export default defineConfig([
  {
    files: ["**/*.ts"],
    extends: [base],
  },
]);
