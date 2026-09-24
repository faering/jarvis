"""Split streamed reply text into speakable chunks, so TTS can start before the reply ends."""

import re

# A sentence ends at . ! ? or … (optionally closed by quotes/brackets) followed by whitespace,
# or at a newline. Requiring whitespace keeps "3.14" whole and waits for the next delta.
_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’)\]]*\s|\n")
_CLAUSE_END = re.compile(r"[,;:]\s|\s[–—]\s")
_SPEAKABLE = re.compile(r"\w")


class Segmenter:
    """Buffers text deltas and emits chunks at sentence ends.

    A long sentence is also cut at a clause boundary (``, ; :`` or a dash) once it reaches
    ``min_clause_chars``, and hard-cut at the last space before ``max_chars``. Chunks with
    nothing speakable (bare punctuation) are dropped.
    """

    def __init__(self, *, min_clause_chars: int = 40, max_chars: int = 200) -> None:
        if not 0 < min_clause_chars <= max_chars:
            raise ValueError("need 0 < min_clause_chars <= max_chars")
        self._min_clause = min_clause_chars
        self._max = max_chars
        self._buffer = ""

    def push(self, text: str) -> list[str]:
        """Add a delta; return the chunks it completed (possibly none)."""
        self._buffer += text
        chunks: list[str] = []
        while (cut := self._find_cut()) is not None:
            chunk, self._buffer = self._buffer[:cut], self._buffer[cut:]
            _append_speakable(chunks, chunk)
        return chunks

    def flush(self) -> list[str]:
        """End of reply: return whatever is left as a final chunk."""
        chunks: list[str] = []
        _append_speakable(chunks, self._buffer)
        self._buffer = ""
        return chunks

    def reset(self) -> None:
        self._buffer = ""

    def _find_cut(self) -> int | None:
        buffer = self._buffer
        cuts: list[int] = []
        if sentence := _SENTENCE_END.search(buffer):
            cuts.append(sentence.end())
        clause = next(
            (m for m in _CLAUSE_END.finditer(buffer) if m.end() >= self._min_clause), None
        )
        if clause:
            cuts.append(clause.end())
        if cuts:
            return min(cuts)
        if len(buffer) > self._max:
            space = buffer.rfind(" ", 0, self._max)
            return space + 1 if space > 0 else self._max
        return None


def _append_speakable(chunks: list[str], chunk: str) -> None:
    chunk = chunk.strip()
    if _SPEAKABLE.search(chunk):
        chunks.append(chunk)
