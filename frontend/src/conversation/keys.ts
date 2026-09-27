/** The key events that start typing a message (a printable key, no shortcut). */
export function isTypingKey(e: {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  isComposing?: boolean;
}): boolean {
  return (
    e.key.length === 1 &&
    e.key.trim() !== "" &&
    !e.ctrlKey &&
    !e.metaKey &&
    !e.altKey &&
    !e.isComposing
  );
}
