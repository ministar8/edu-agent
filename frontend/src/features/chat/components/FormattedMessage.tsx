import { memo, useMemo } from "react";
import katex from "katex";

type Block =
  | { type: "blank" }
  | { type: "h1" | "h2" | "h3" | "p" | "quote" | "li" | "oli"; text: string }
  | { type: "code"; text: string }
  | { type: "math"; text: string };

function parseBlocks(content: string): Block[] {
  const lines = content.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Blank line
    if (trimmed.length === 0) {
      blocks.push({ type: "blank" });
      i++;
      continue;
    }

    // Block-level LaTeX: $$...$$
    if (trimmed.startsWith("$$")) {
      const mathLines: string[] = [];
      // Single-line $$...$$
      if (trimmed.endsWith("$$") && trimmed.length > 4) {
        blocks.push({ type: "math", text: trimmed.slice(2, -2).trim() });
        i++;
        continue;
      }
      const opener = trimmed.length > 2 ? trimmed.slice(2).trim() : "";
      if (opener) mathLines.push(opener);
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("$$")) {
        mathLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing $$
      blocks.push({ type: "math", text: mathLines.join("\n").trim() });
      continue;
    }

    // Fenced code block
    if (trimmed.startsWith("```")) {
      const codeLines: string[] = [];
      i++; // skip opening fence
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing fence (if present)
      blocks.push({ type: "code", text: codeLines.join("\n") });
      continue;
    }

    // Headings
    if (trimmed.startsWith("### ")) {
      blocks.push({ type: "h3", text: trimmed.replace(/^###\s+/, "") });
      i++;
      continue;
    }
    if (trimmed.startsWith("## ")) {
      blocks.push({ type: "h2", text: trimmed.replace(/^##\s+/, "") });
      i++;
      continue;
    }
    if (trimmed.startsWith("# ")) {
      blocks.push({ type: "h1", text: trimmed.replace(/^#\s+/, "") });
      i++;
      continue;
    }

    // Blockquote
    if (trimmed.startsWith("> ")) {
      blocks.push({ type: "quote", text: trimmed.replace(/^>\s*/, "") });
      i++;
      continue;
    }

    // Unordered list
    if (/^[-*]\s+/.test(trimmed)) {
      blocks.push({ type: "li", text: trimmed.replace(/^[-*]\s+/, "") });
      i++;
      continue;
    }

    // Ordered list
    if (/^\d+[.、]\s*/.test(trimmed)) {
      blocks.push({ type: "oli", text: trimmed });
      i++;
      continue;
    }

    // Regular paragraph
    blocks.push({ type: "p", text: trimmed });
    i++;
  }

  return blocks;
}

function FormattedMessageComponent({ content }: { content: string }) {
  const blocks = parseBlocks(content);

  return (
    <div className="space-y-1 text-sm leading-7 text-slate-700">
      {blocks.map((block, index) => {
        const key = `${index}-${block.type}`;
        switch (block.type) {
          case "blank":
            return <div key={key} className="h-3" />;
          case "h1":
            return <h2 key={key} className="pt-2 text-lg font-semibold text-slate-900">{renderInline(block.text)}</h2>;
          case "h2":
            return <h3 key={key} className="pt-2 text-base font-semibold text-slate-900">{renderInline(block.text)}</h3>;
          case "h3":
            return <h4 key={key} className="pt-1 text-sm font-semibold text-slate-900">{renderInline(block.text)}</h4>;
          case "math":
            return <div key={key} className="my-2 overflow-x-auto"><LatexMath math={block.text} displayMode /></div>;
          case "code":
            return (
              <pre key={key} className="my-2 overflow-x-auto rounded-xl bg-slate-800 p-4 text-xs leading-5 text-slate-100">
                <code>{block.text}</code>
              </pre>
            );
          case "quote":
            return <blockquote key={key} className="border-l-3 border-slate-300 pl-3 text-slate-500 italic">{renderInline(block.text)}</blockquote>;
          case "li":
            return <div key={key} className="pl-4 text-slate-700">- {renderInline(block.text)}</div>;
          case "oli":
            return <div key={key} className="pl-4 text-slate-700">{renderInline(block.text)}</div>;
          default:
            return <p key={key}>{renderInline(block.text)}</p>;
        }
      })}
    </div>
  );
}

function renderInline(text: string) {
  // Split on $$...$$ (inline display), $...$ (inline), **bold**, `code`, and [links](url)
  const parts = text.split(/(\$\$[^$]+\$\$|\$[^$]+\$|\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, i) => {
    if (part.startsWith("$$") && part.endsWith("$$")) {
      return <LatexMath key={i} math={part.slice(2, -2).trim()} displayMode />;
    }
    if (part.startsWith("$") && part.endsWith("$") && !part.startsWith("$$")) {
      return <LatexMath key={i} math={part.slice(1, -1).trim()} />;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="rounded bg-slate-100 px-1 py-0.5 text-xs font-mono text-emerald-700">{part.slice(1, -1)}</code>;
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      const href = linkMatch[2];
      const isSafe = /^https?:\/\//i.test(href);
      if (!isSafe) return <span key={i} className="text-emerald-600">{linkMatch[1]}</span>;
      return <a key={i} href={href} className="text-emerald-600 underline" target="_blank" rel="noopener noreferrer">{linkMatch[1]}</a>;
    }
    return part;
  });
}

function LatexMath({ math, displayMode }: { math: string; displayMode?: boolean }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(math, {
        displayMode: !!displayMode,
        throwOnError: false,
        trust: false,
      });
    } catch {
      return null;
    }
  }, [math, displayMode]);
  if (!html) {
    return <span className="text-red-500">{math}</span>;
  }
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

export const FormattedMessage = memo(FormattedMessageComponent);
