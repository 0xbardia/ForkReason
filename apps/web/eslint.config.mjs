// ESLint flat config for the ForkReason frontend.
//
// This file existed only as a broken `lint` script: `next lint` had no config
// and no ESLint dependencies installed, so `npm run lint` failed with
// "Cannot find package '@eslint/js'" instead of reporting anything about the
// code. A lint command that cannot run is worse than none, because it looks
// like a gate.
//
// Scope is deliberately narrow. TypeScript already runs `tsc --noEmit`, which
// catches type errors; ESLint is here for the things types do not: unused
// values, unreachable code, and React hook mistakes.

import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "tsconfig.tsbuildinfo",
      "scripts/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Unused code is dead code. These are errors, not warnings: a value that
      // is never read is either a bug or leftover scaffolding, and both should
      // block a merge.
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
      "no-unused-vars": "off",
      "no-unreachable": "error",
      "no-constant-condition": ["error", { checkLoops: false }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-private-class-members": "error",
      eqeqeq: ["error", "smart"],
      "prefer-const": "error",
    },
  },
  {
    // This project fetches data in effects. That is a deliberate choice, not an
    // oversight: every read here is public, server-side, and dependent on
    // user-chosen filters (case id, page offset, search query, verdict), so
    // there is no router-level fetch boundary to move them to. React Query is
    // used for the wallet and chain layers, where the same argument does not
    // hold.
    //
    // The rule still fires on the pattern it is meant to catch — resetting
    // state synchronously because a prop changed, which is what causes
    // cascading renders — and the three genuine instances of that in this
    // codebase were rewritten to derive the value instead.
    files: ["**/*.{ts,tsx}"],
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
  {
    // Tests may assert on loosely-typed fixtures.
    files: ["**/*.test.ts", "**/*.test.tsx"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    // CommonJS build shim. Proxy traps legitimately ignore their arguments,
    // and `module` is a CommonJS global.
    files: ["lib/empty-module.js"],
    languageOptions: {
      sourceType: "commonjs",
      globals: { ...globals.node },
    },
    rules: {
      "@typescript-eslint/no-unused-vars": "off",
      "no-unused-vars": ["error", { args: "none" }],
    },
  },
);