import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { SourceMapConsumer } = require("source-map-js");

const map = { version: 3, sources: ["input.js"], names: [], mappings: "AAAA" };
const indexed = (line, column) => ({
  version: 3,
  sections: [{ offset: { line, column }, map }],
});

test("untrusted indexed-map offsets cannot cause unbounded flattening work", () => {
  for (const [line, column] of [
    [1_000_000_000_000, 0], [Infinity, 0], [NaN, 0], [-1, 0],
    [0.5, 0], [0, -1], [0, Infinity], ["10", 0],
  ]) {
    assert.throws(() => new SourceMapConsumer(indexed(line, column)), /offset/i);
  }
});

test("ordinary indexed maps retain their original source position", () => {
  const consumer = new SourceMapConsumer(indexed(3, 0));
  const mappings = [];
  consumer.eachMapping((mapping) => mappings.push(mapping));
  assert.equal(mappings.length, 1);
  assert.equal(mappings[0].generatedLine, 4);
  assert.equal(mappings[0].generatedColumn, 0);
  assert.equal(mappings[0].source, "input.js");
  assert.equal(mappings[0].originalLine, 1);
});
