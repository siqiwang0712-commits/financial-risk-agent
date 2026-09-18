import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";

// The frontend shipped no linter at all: `next build` only type-checks, and CI ran
// `npm audit`/`typecheck`/`test` without a single static rule. This wires up the
// Next.js recommended set (correctness-oriented: hooks rules, unsafe DOM APIs,
// unused bindings) without pulling in a formatter, so existing style is untouched.
const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals"),
];

export default config;
