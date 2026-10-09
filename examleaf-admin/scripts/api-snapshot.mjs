// Saves the backend's OpenAPI schema as openapi.json (committed), the input of `npm run api:types`.
// Run it against a backend started from examleaf-web/ (README.md, "Regenerate the API types"). The text is kept as
// Django sends it: parsing it in JavaScript would round the schema's 64-bit integer limits.
import { writeFileSync } from "node:fs";

const base = process.env.API_INTERNAL_BASE ?? "http://localhost:8100";
const response = await fetch(`${base}/api/schema/?format=json`);
if (!response.ok) throw new Error(`${base}/api/schema/ answered ${response.status}`);
const text = await response.text();
writeFileSync("openapi.json", text.endsWith("\n") ? text : `${text}\n`);
console.log(`openapi.json saved from ${base}`);
