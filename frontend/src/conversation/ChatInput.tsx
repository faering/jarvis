import { useEffect, useRef, useState, type KeyboardEvent } from "react";

export interface ChatInputProps {
  /** Text to start with (the key that opened the input). */
  initial?: string;
  /** False while the agent isn't connected: the input says so and won't send. */
  enabled: boolean;
  /** Send a message; returns false if it could not be sent. */
  onSend: (text: string) => boolean;
  onClose: () => void;
}

/**
 * One-line keyboard input for talking to Jarvis (Bluetooth keyboard on the Pi).
 * Enter sends, Escape closes; it sits at the bottom so the face stays visible.
 * Mount it only while open (with a fresh `key` per opening).
 */
export function ChatInput({
  initial = "",
  enabled,
  onSend,
  onClose,
}: ChatInputProps) {
  const [text, setText] = useState(initial);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => field.current?.focus(), []);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      e.preventDefault();
      const message = text.trim();
      if (message && enabled && onSend(message)) {
        setText("");
        onClose();
      }
    }
  };

  return (
    <div
      className="chat-input"
      onPointerDown={(e) => e.stopPropagation()}
      onPointerUp={(e) => e.stopPropagation()}
    >
      <input
        ref={field}
        type="text"
        aria-label="Message to Jarvis"
        placeholder={
          enabled ? "Say something to Jarvis…" : "Jarvis is not connected"
        }
        value={text}
        maxLength={2000}
        enterKeyHint="send"
        autoComplete="off"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => text.trim() === "" && onClose()}
      />
    </div>
  );
}
