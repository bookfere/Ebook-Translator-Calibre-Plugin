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


class OpenCodeZenTranslate(OpenCodeTranslate):
    name = 'OpenCode Zen'
    alias = 'OpenCode Zen'
    endpoint = 'https://opencode.ai/zen/v1/chat/completions'

    # The API model list is authoritative. This fallback lets users choose
    # every currently published Zen model when the model endpoint is down.
    models: list[str] = [
        'claude-fable-5', 'claude-opus-5', 'claude-opus-4-8',
        'claude-opus-4-7', 'claude-opus-4-6', 'claude-opus-4-5',
        'claude-sonnet-5', 'claude-sonnet-4-6', 'claude-sonnet-4-5',
        'claude-sonnet-4', 'claude-haiku-4-5', 'gemini-3.7-flash',
        'gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-3.5-flash',
        'gemini-3.1-pro', 'gemini-3-flash', 'gpt-5.6-sol',
        'gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-5.5', 'gpt-5.5-pro',
        'gpt-5.4', 'gpt-5.4-pro', 'gpt-5.4-mini', 'gpt-5.4-nano',
        'gpt-5.3-codex-spark', 'gpt-5.3-codex', 'gpt-5.2',
        'gpt-5.2-codex', 'gpt-5.1', 'gpt-5.1-codex-max',
        'gpt-5.1-codex', 'gpt-5.1-codex-mini', 'gpt-5', 'gpt-5-codex',
        'gpt-5-nano', 'grok-build-0.1', 'grok-4.6', 'grok-4.5',
        'muse-spark-1.2', 'deepseek-v4-pro', 'deepseek-v4-flash',
        'glm-5.2', 'glm-5.1', 'glm-5', 'minimax-m3', 'minimax-m2.7',
        'minimax-m2.5', 'kimi-k3', 'kimi-k2.7-code', 'kimi-k2.6',
        'kimi-k2.5', 'qwen3.6-plus', 'qwen3.5-plus', 'big-pickle',
        'deepseek-v4-flash-free', 'mimo-v2.5-free', 'hy3-free',
        'nemotron-3-ultra-free', 'nemotron-3.5-lightning-free',
        'laguna-s-2.1-free',
    ]
    model: str | None = 'deepseek-v4-flash'
    recommended_merge_length = 6000
    prompt = (
        'Translate all content from <slang> to <tlang>. Preserve every part, '
        'URL, and placeholder. Output only the translation, with no '
        'explanation, prefix, suffix, or formatting.')
    using_tip = _(
        'OpenCode Zen lists every model returned by your API key. Some '
        'models may reject this engine\'s request format; use Test '
        'Translation Engine to verify a model before translating an ebook. '
        'To reduce token usage, apply the OpenCode Zen balanced preset in '
        'Merge to Translate. Check actual charges and monthly limits in the '
        'OpenCode Zen console.')
