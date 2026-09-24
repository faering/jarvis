// Shared ESLint flat config for every TS package: `extends: [base]` inside a config
// object that sets `files` (and any framework plugins / globals).
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default [js.configs.recommended, ...tseslint.configs.recommended];
