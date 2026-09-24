#!/usr/bin/env node
/**
 * Generate src/api/generated.ts from the committed JSON Schema contract.
 *
 *   npm run gen:types
 *
 * Source: packages/schemas/document-intelligence.v1.schema.json (exported from the backend's
 * Pydantic models by scripts/export_schemas.py). Every definition in `$defs` is emitted, named
 * after its `$defs` key. Property-level `title`s (Pydantic adds one per field) are dropped so
 * they do not turn into dozens of meaningless type aliases.
 */
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const schemaPath = resolve(here, "../../../packages/schemas/document-intelligence.v1.schema.json");
const outPath = resolve(here, "../src/api/generated.ts");

const raw = JSON.parse(await readFile(schemaPath, "utf8"));

const BANNER = `/* eslint-disable */
/**
 * Generated — do not edit.
 *
 * Source: packages/schemas/document-intelligence.v1.schema.json
 * ${raw.description}
 * Regenerate with \`npm run gen:types\` (apps/web) after the backend contract changes.
 */`;

/** Remove `title` keywords from every schema node except the named `$defs` entries. */
function stripPropertyTitles(node, isDefinition = false) {
  if (Array.isArray(node)) return node.map((item) => stripPropertyTitles(item));
  if (node === null || typeof node !== "object") return node;
  const out = {};
  for (const [key, value] of Object.entries(node)) {
    if (key === "title" && !isDefinition) continue;
    if (key === "properties" || key === "$defs") {
      out[key] = Object.fromEntries(
        Object.entries(value).map(([name, sub]) => [
          name,
          stripPropertyTitles(sub, key === "$defs"),
        ]),
      );
    } else {
      out[key] = stripPropertyTitles(value);
    }
  }
  return out;
}

const { $defs } = stripPropertyTitles(raw);

// The bundle's root is only a container for `$defs`; its (empty) interface is dropped below.
const ROOT_NAME = "DocumentIntelligenceContracts";
const root = { title: ROOT_NAME, type: "object", additionalProperties: false, $defs };

const compiled = await compile(root, ROOT_NAME, {
  bannerComment: BANNER,
  unreachableDefinitions: true,
  additionalProperties: false,
  strictIndexSignatures: true,
  unknownAny: true,
  format: true,
  style: { printWidth: 100, singleQuote: false, trailingComma: "all" },
});

const emptyRoot = `export interface ${ROOT_NAME} {}\n`;
if (!compiled.includes(emptyRoot)) {
  throw new Error(`Expected an empty ${ROOT_NAME} interface in the generated output.`);
}
await writeFile(outPath, compiled.replace(emptyRoot, ""), "utf8");
console.log(`Wrote ${outPath}`);
