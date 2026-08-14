from .openai import ChatgptTranslate

load_translations()  # type: ignore


class OpenCodeTranslate(ChatgptTranslate):
    name = 'OpenCode Go'
    alias = 'OpenCode Go'
    endpoint = 'https://opencode.ai/zen/go/v1/chat/completions'

    # A relay service that may buffer streaming responses and limit the
    # upstream throughput. Disable throttling and streaming by default.
    concurrency_limit = 0
    request_interval = 0.0
    request_timeout = 120.0
    stream = False

    # The models are fetched dynamically from the /models endpoint. The
    # static list below is used as a fallback when fetching is unavailable.
    models: list[str] = [
        'minimax-m3', 'minimax-m2.7', 'minimax-m2.5', 'kimi-k3',
        'kimi-k2.7-code', 'kimi-k2.6', 'kimi-k2.5', 'glm-5.2', 'glm-5.3',
        'glm-5.1', 'glm-5', 'deepseek-v4-pro', 'deepseek-v4-flash',
        'qwen3.7-max', 'qwen3.8-max', 'qwen3.7-plus', 'qwen3.6-plus',
        'qwen3.5-plus', 'mimo-v2-pro', 'mimo-v2-omni', 'mimo-v2.5-pro',
        'mimo-v2.5', 'hy3', 'hy3-preview', 'gpt-5.6-luna', 'grok-4.5',
    ]
    model: str | None = 'deepseek-v4-flash'
