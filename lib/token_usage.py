import json
import threading
from dataclasses import dataclass
from typing import Any


def token_estimate(value: Any) -> int:
    """Return a tokenizer-independent approximation for usage reporting."""
    if value is None:
        return 0
    if isinstance(value, bytes):
        data = value
    else:
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, default=str)
        data = value.encode('utf-8')
    if not data:
        return 0
    return max(1, (len(data) + 3) // 4)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False

    def __post_init__(self):
        input_tokens = max(0, int(self.input_tokens or 0))
        output_tokens = max(0, int(self.output_tokens or 0))
        total_tokens = max(0, int(self.total_tokens or 0))
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens
        object.__setattr__(self, 'input_tokens', input_tokens)
        object.__setattr__(self, 'output_tokens', output_tokens)
        object.__setattr__(self, 'total_tokens', total_tokens)


class TokenCounter:
    def __init__(self, limit=0):
        self.limit = max(0, int(limit or 0))
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.estimated = False
        self._lock = threading.Lock()

    def add(self, usage):
        with self._lock:
            self.input_tokens += max(0, int(usage.input_tokens or 0))
            self.output_tokens += max(0, int(usage.output_tokens or 0))
            self.total_tokens += max(0, int(usage.total_tokens or 0))
            self.estimated = self.estimated or bool(usage.estimated)
            return self._snapshot()

    def _snapshot(self):
        return {
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'estimated': self.estimated,
            'limit': self.limit,
            'reached': self.limit > 0 and self.total_tokens >= self.limit,
        }

    def snapshot(self):
        with self._lock:
            return self._snapshot()
