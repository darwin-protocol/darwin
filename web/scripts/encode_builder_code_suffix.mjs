#!/usr/bin/env node
import { Attribution } from "ox/erc8021";

const rawCodes = process.argv[2]?.trim();

if (!rawCodes) {
  console.error("usage: node web/scripts/encode_builder_code_suffix.mjs <builder-code[,builder-code...]>");
  process.exit(1);
}

const codes = rawCodes
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

if (!codes.length) {
  console.error("missing builder code");
  process.exit(1);
}

process.stdout.write(`${Attribution.toDataSuffix({ codes })}\n`);
