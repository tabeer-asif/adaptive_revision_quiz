import { InlineMath, BlockMath } from "react-katex";
import "katex/dist/katex.min.css";

/**
 * Renders a string that may contain LaTeX math delimiters:
 *   \\(...\\)  → inline math (preferred)
 *   \\[...\\]  → display/block math (preferred)
 *
 * Everything else is rendered as plain text spans.
 */
export default function MathText({ text }) {
  if (!text) return null;

  const value = String(text);
  const tokenRegex = /(\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\))/g;
  const parts = value.split(tokenRegex);

  const renderInline = (math, key, fallback) => (
    <InlineMath
      key={key}
      math={math}
      renderError={() => <span>{fallback}</span>}
    />
  );

  const renderBlock = (math, key, fallback) => (
    <BlockMath
      key={key}
      math={math}
      renderError={() => <span>{fallback}</span>}
    />
  );

  return (
    <>
      {parts.map((part, i) => {
        if (!part) return null;

        if (part.startsWith("\\[") && part.endsWith("\\]")) {
          const expr = part.slice(2, -2).trim();
          return renderBlock(expr, i, part);
        }
        if (part.startsWith("\\(") && part.endsWith("\\)")) {
          const expr = part.slice(2, -2).trim();
          return renderInline(expr, i, part);
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}
