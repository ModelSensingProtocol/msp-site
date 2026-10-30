# Versioning: protocol revisions and schema

Three different things are versioned in this project, and confusing them is the fastest way to an
interop bug. Keep them apart:

| What | Where | Changes when |
|---|---|---|
| **protocol revision** | `schema/<revision>/` in the main repository | normative behaviour changes |
| **wire schema** | inside that revision: `msp.yaml` → generated JSON Schema | a field, type, or enum changes |
| **package version** | `msp-py 0.1.0a1` | a release of one implementation |

## What a revision means

`2026-10-10` is a date, not a semantic version. It identifies the normative text plus the schema that
go with it. Two implementations claiming the same revision must interoperate on the bytes; two
implementations on different revisions may not.

The current revision is also the one the docs are pinned to — `/docs/` serves the `2026-10-10`
snapshot, and unreleased edits live at `/docs/next/`.

## The compatibility rules that matter

- **Eight top-level fields are fixed.** A signal always has `type`, `source`, `pattern`, `target`,
  `path`, `reqid`, `payload`, `timestamp` — absent values are `null`, never omitted.
- **Unknown fields survive.** An unknown top-level key is preserved in `extras` and echoed back. That
  is what lets a peer ignore a feature it does not know about, and it is why adding a field is not a
  breaking change for a tolerant reader.
- **Strict expiry, lenient reading.** Expiry is `now - timestamp > stale_after` (strictly greater); a
  declaration with no `timestamp` never expires, for backward compatibility with hand-written files.

## Schema generation is not hand-written

```bash
python tools/gen_schema.py     # schema/<revision>/msp.yaml → msp.schema.json + field-index.json
```

The YAML is the source; the JSON Schema and the field index are generated. Never edit the generated
files — they will be overwritten, and a hand-edited schema is how implementations silently disagree.

## Adding a revision

1. Copy `schema/2026-10-10/` to the new date and edit the YAML.
2. Regenerate the schema and field index.
3. Update the spec text, marking new requirements **MUST** / **SHOULD** explicitly — the spec's own
   convention, so an implementation knows what it can skip.
4. For the docs: snapshot the site with `npm run version <new-date>` (see the site README), so
   `/docs/` starts serving the new revision and the old one stays reachable.
5. Write down what breaks. A revision whose diff is not described is a revision nobody can implement.

## Checking a claim of compatibility

"Compatible with MSP" is not a statement you can verify from a badge. What you can check:

- the eight fields, byte for byte, on a captured frame;
- handshake (`HELLO` → `ACK`) against a reference node;
- that unknown top-level fields are preserved rather than dropped;
- the expiry boundary: a declaration 29 s old is valid, 31 s is not.

The `msp-ts` test suite does exactly these against a live Python node — see
[Testing a node](testing.md).

## See also

- [`spec/schema.md`](pathname:///msp-site/docs/spec/schema/) — the normative field list
- [`spec/versioning.md`](https://github.com/hxh230802/MSP/blob/master/docs/spec/README.md) — how the
  revision identifier is carried
- [Positioning](why-not-mcp.md) — why the protocol stays small enough to keep these rules in one head
