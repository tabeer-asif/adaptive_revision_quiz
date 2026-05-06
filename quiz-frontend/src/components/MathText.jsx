import { InlineMath, BlockMath } from "react-katex";
import "katex/dist/katex.min.css";

/**
 * Renders a string that may contain LaTeX math delimiters:
 *   $$...$$ → display / block math (centred)
 *   $...$   → inline math
 *
 * Everything else is rendered as plain text spans.
 */
export default function MathText({ text }) {
  if (!text) return null;

  // Split on $$...$$ first, then $...$ — order matters so $$ isn't consumed as two $.
  const parts = String(text).split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g);

  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("$$") && part.endsWith("$$")) {
          return <BlockMath key={i} math={part.slice(2, -2)} />;
        }
        if (part.startsWith("$") && part.endsWith("$")) {
          return <InlineMath key={i} math={part.slice(1, -1)} />;
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}
