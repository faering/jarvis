import { useEffect, useRef } from "react";
import type { Caption } from "../presence/presence.ts";

const NOTE: Record<NonNullable<Caption["tone"]>, string> = {
  degraded: "answered by the local model",
  error: "no answer",
};

/**
 * The conversation over any presence screen: your line, then Jarvis's reply as
 * it streams in. Long replies scroll, kept pinned to the newest text.
 */
export function ConversationOverlay({
  captions,
}: {
  captions: readonly Caption[];
}) {
  const box = useRef<HTMLDivElement>(null);
  const last = captions.at(-1);
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [last?.text]);

  if (captions.length === 0) return null;
  return (
    <div ref={box} className="conversation" aria-live="polite">
      {captions.map((caption, i) => (
        <p
          key={i}
          className={[
            "caption",
            `caption-${caption.who}`,
            caption.tone && `caption-${caption.tone}`,
            caption.streaming && "caption-streaming",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <span className="caption-who">
            {caption.who === "user" ? "You" : "Jarvis"}
            {caption.tone && (
              <span className="caption-note"> ({NOTE[caption.tone]})</span>
            )}
          </span>
          {caption.text}
        </p>
      ))}
    </div>
  );
}
