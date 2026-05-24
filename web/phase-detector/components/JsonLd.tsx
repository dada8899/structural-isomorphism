// W12-B (session #10, 2026-05-15): JSON-LD structured data helper.
//
// Renders a single <script type="application/ld+json"> tag containing the
// provided schema.org object. The component is server-renderable; we use
// `dangerouslySetInnerHTML` (the canonical Next.js pattern for JSON-LD)
// instead of stringifying via children so React doesn't HTML-escape the
// quotes inside the JSON.
//
// Usage:
//   <JsonLd
//     schema={{
//       "@context": "https://schema.org",
//       "@type": "WebSite",
//       name: "Phase Detector",
//       url: "https://phase.bytedance.city",
//     }}
//   />
//
// To embed multiple schema graphs on a single page, pass an array, or call
// the component multiple times. Schema.org also supports `@graph` for a
// single object containing multiple nested types.

import type { ReactElement } from "react";

// Loose typing: schema.org has hundreds of types and no single TS upstream
// surface that we want to take a dep on. We accept any JSON-serializable
// object/array and trust authors.
export type JsonLdSchema = Record<string, unknown> | Array<Record<string, unknown>>;

export interface JsonLdProps {
  schema: JsonLdSchema;
  /**
   * Optional id for the <script> tag — useful when a page emits multiple
   * structured-data graphs and you want to inspect/override one.
   */
  id?: string;
}

/**
 * Stable JSON serialization for structured data. We do NOT include the
 * `</script>` escape trick used by some libraries since schema.org content
 * is never user-controlled here; all fields come from server-side curated
 * data. If that assumption changes, swap this for a safer serializer.
 */
function serialize(schema: JsonLdSchema): string {
  return JSON.stringify(schema).replace(/</g, "\\u003c");
}

export default function JsonLd({ schema, id }: JsonLdProps): ReactElement {
  return (
    <script
      id={id}
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: serialize(schema) }}
    />
  );
}
