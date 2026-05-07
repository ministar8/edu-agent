import { memo } from "react";

function FormattedMessageComponent({ content }: { content: string }) {
  const lines = content.split("\n").filter((line) => line.trim().length > 0);

  return (
    <div className="space-y-2 text-sm leading-7 text-slate-700">
      {lines.map((line, index) => {
        const text = line.trim();
        const key = `${index}-${text.slice(0, 20)}`;

        if (text.startsWith("### ")) {
          return <h4 key={key} className="pt-1 text-sm font-semibold text-slate-900">{text.replace(/^###\s+/, "")}</h4>;
        }
        if (text.startsWith("## ")) {
          return <h3 key={key} className="pt-2 text-base font-semibold text-slate-900">{text.replace(/^##\s+/, "")}</h3>;
        }
        if (text.startsWith("# ")) {
          return <h2 key={key} className="pt-2 text-lg font-semibold text-slate-900">{text.replace(/^#\s+/, "")}</h2>;
        }
        if (/^[-*]\s+/.test(text)) {
          return <div key={key} className="pl-4 text-slate-700">- {renderInlineBold(text.replace(/^[-*]\s+/, ""))}</div>;
        }
        if (/^\d+[.、]\s*/.test(text)) {
          return <div key={key} className="pl-4 text-slate-700">{renderInlineBold(text)}</div>;
        }
        return <p key={key}>{renderInlineBold(text)}</p>;
      })}
    </div>
  );
}

function renderInlineBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

export const FormattedMessage = memo(FormattedMessageComponent);
