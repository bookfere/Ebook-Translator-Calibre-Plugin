import json
import time
from typing import Generator
from urllib.parse import urljoin
from http.client import IncompleteRead

from mechanize._response import response_seek_wrapper as Response

from .. import EbookTranslator
from ..lib.utils import request, log

from .genai import GenAI
from .languages import anthropic
from .prompt_extensions import anthropic as anthropic_prompt_extension


load_translations()  # type: ignore


class ClaudeTranslate(GenAI):
    name = 'Claude'
    alias = 'Claude (Anthropic)'
    lang_codes = GenAI.load_lang_codes(anthropic)
    endpoint = 'https://api.anthropic.com/v1/messages'
    # by default use the latest version of the api (currently this is 2023-06-01)
    api_version = '2023-06-01'
    api_key_hint = 'sk-ant-xxxx'
    # https://docs.anthropic.com/claude/reference/errors
    api_key_errors = ['401', 'permission_error']

    concurrency_limit = 1
    request_interval = 12.0
    request_timeout = 30.0

    prompt = (
        'You are a meticulous translator who translates any given content. '
        'Translate the given content from <slang> to <tlang> only. Do not '
        'explain any term or answer any question-like content. Your answer '
        'should be solely the translation of the given content. In your '
        'answer do not add any prefix or suffix to the translated content. '
        'Websites\' URLs/addresses should be preserved as is in the '
        'translation\'s output. Do not omit any part of the content, even if '
        'it seems unimportant. ')

    samplings = ['temperature', 'top_p']
    sampling = 'temperature'
    temperature = 1.0
    top_p = 1.0
    top_k = 1
    stream = True
    enable_extended_output = False  # 128K output for Claude 3.7 Sonnet
    enable_extended_context = False  # 1M context for Claude Sonnet 4.0/4.5
    enable_dynamic_timeout = False  # Dynamic timeout based on content length
    enable_prompt_caching = False  # Prompt caching for parallel sections with full context

    # event types for streaming are listed here:
    # https://docs.anthropic.com/en/api/messages-streaming
    valid_event_types = [
        'ping',
        'error',
        'content_block_start',
        'content_block_delta',
        'content_block_stop',
        'message_start',
        'message_delta',
        'message_stop']

    models: list[str] = []
    model: str | None = 'claude-sonnet-4-5'

    def __init__(self):
        super().__init__()
        self.endpoint = self.config.get('endpoint', self.endpoint)
        self.prompt = self.config.get('prompt', self.prompt)
        self.sampling = self.config.get('sampling', self.sampling)
        self.temperature = self.config.get('temperature', self.temperature)
        self.top_p = self.config.get('top_p', self.top_p)
        self.top_k = self.config.get('top_k', self.top_k)
        self.stream = self.config.get('stream', self.stream)
        self.model = self.config.get('model', self.model)
        self.enable_extended_output = self.config.get(
            'enable_extended_output', self.enable_extended_output)
        self.enable_extended_context = self.config.get(
            'enable_extended_context', self.enable_extended_context)
        self.enable_dynamic_timeout = self.config.get(
            'enable_dynamic_timeout', self.enable_dynamic_timeout)
        self.enable_prompt_caching = self.config.get(
            'enable_prompt_caching', self.enable_prompt_caching)
        self.full_book_context = None  # Set externally for prompt caching

    def _get_prompt(self):
        prompt = self.prompt.replace('<tlang>', self.target_lang)
        if self._is_auto_lang():
            prompt = prompt.replace('<slang>', 'detected language')
        else:
            prompt = prompt.replace('<slang>', self.source_lang)

        prompt_extension = anthropic_prompt_extension.get(self.target_lang)
        if prompt_extension is not None:
            prompt += ' ' + prompt_extension

        # Recommend setting temperature to 0.5 for retaining the placeholder.
        if self.merge_enabled:
            prompt += (' Ensure that placeholders matching the pattern '
                       '{{id_\\d+}} in the content are retained.')
        return prompt

    def translate(self, content):
        # Use dynamic timeout only if enabled (default: disabled)
        if self.enable_dynamic_timeout:
            # Calculate dynamic timeout based on estimated token generation time
            # Estimate output tokens (conservative: 3 chars per token)
            estimated_output_tokens = len(content) // 3
            # Claude models generate 65-120 tokens/second (varies by model)
            # Use conservative 50 tokens/sec to account for network latency and processing
            # Source: https://artificialanalysis.ai/models/claude-3-opus
            # Add 60s base overhead for request processing and network latency
            estimated_time = (estimated_output_tokens / 50) + 60
            # Minimum 30s, maximum 2 hours for very large content
            dynamic_timeout = max(30.0, min(estimated_time, 7200.0))

            # Temporarily set timeout for this request
            original_timeout = self.request_timeout
            self.request_timeout = dynamic_timeout

            try:
                return super().translate(content)
            finally:
                # Restore original timeout
                self.request_timeout = original_timeout
        else:
            # Use user-configured timeout (default 30s)
            return super().translate(content)

    def get_models(self):
        model_endpoint = urljoin(self.endpoint, 'models')
        response = request(model_endpoint, headers=self.get_headers())
        return [i['id'] for i in json.loads(response)['data']]

    def get_headers(self):
        headers = {
            'Content-Type': 'application/json',
            'anthropic-version': self.api_version,
            'x-api-key': self.api_key,
            'User-Agent': 'Ebook-Translator/%s' % EbookTranslator.__version__,
        }

        # Enable beta features based on user configuration
        # More info: https://platform.claude.com/docs/en/about-claude/models/overview
        beta_features = []

        if self.model is not None:
            # For Claude Sonnet 3.7 - enable 128K output tokens
            # (requires user to enable this option)
            if self.enable_extended_output and self.model.startswith('claude-3-7-sonnet-'):
                beta_features.append('output-128k-2025-02-19')
            # For Claude Sonnet 4/4.5 - enable 1M token context window
            # (requires user to enable this option)
            # More info: https://platform.claude.com/docs/en/about-claude/pricing#long-context-pricing
            #
            # NOTE: When the 1M token context window is enabled, requests that exceed 200K input tokens
            #       are automatically charged at premium long context rates. The 1M token context window
            #       is currently in beta for organizations in usage tier 4 and organizations with custom
            #       rate limits.
            #
            #       Even with the beta flag enabled, requests with fewer than 200K input tokens are
            #       charged at standard rates. If your request exceeds 200K input tokens, all tokens
            #       incur premium pricing.
            #
            #       The 200K threshold is based solely on input tokens (including cache reads/writes).
            #       Output token count does not affect pricing tier selection, though output tokens are
            #       charged at the higher rate when the input threshold is exceeded.
            elif self.enable_extended_context and (
                    self.model.startswith('claude-sonnet-4-0') or
                    self.model.startswith('claude-sonnet-4-5')):
                beta_features.append('context-1m-2025-08-07')

        # Prompt caching can be used with any Claude model
        # More info: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
        if self.enable_prompt_caching:
            beta_features.append('prompt-caching-2024-07-31')

        if beta_features:
            headers['anthropic-beta'] = ','.join(beta_features)

        return headers

    def get_body(self, text):
        # Calculate max_tokens based on model and input length
        # Estimate output will be similar length to input
        estimated_output_tokens = len(text) // 3  # Conservative: ~3 chars per token

        # Determine model's max output capability based on official docs
        # Source: https://platform.claude.com/docs/en/about-claude/models/overview
        if not self.model:
            model_max_output = 4_096
        elif self.model.startswith('claude-3-7-sonnet-') and self.enable_extended_output:
            # Claude 3.7 Sonnet with extended output beta flag
            model_max_output = 128_000
        elif self.model.startswith('claude-3-7-sonnet-'):
            # Claude 3.7 Sonnet without beta flag
            model_max_output = 64_000
        elif self.model.startswith('claude-sonnet-4-') or \
             self.model.startswith('claude-haiku-4-') or \
             self.model.startswith('claude-opus-4-5') or \
             self.model.startswith('claude-opus-4-1'):
            # Claude 4.5 (all variants) and Claude 4.1 Opus: 64K
            # Also Claude Sonnet 4.0, Haiku 4.5
            model_max_output = 64_000
        elif self.model.startswith('claude-opus-4-0'):
            # Claude Opus 4.0: 32K
            model_max_output = 32_000
        elif self.model.startswith('claude-3-haiku-'):
            # Claude Haiku 3.x: 4K
            model_max_output = 4_000
        elif self.model.startswith('claude-'):
            # Other Claude models: conservative 32K default
            model_max_output = 32_000
        else:
            # Non-Claude models or unknown: very conservative
            model_max_output = 4_096

        # Use estimated output or model max, whichever is smaller
        # Add 10% buffer for safety
        max_tokens = min(int(estimated_output_tokens * 1.1), model_max_output)
        # Minimum 4096 tokens
        max_tokens = max(max_tokens, 4_096)

        # Build system message with optional caching
        if self.enable_prompt_caching and self.full_book_context:
            # Use full book context as cached system message
            # More info: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
            system_content = [
                {
                    "type": "text",
                    "text": self._get_prompt()
                },
                {
                    "type": "text",
                    "text": "Full book context for reference:\n\n" + self.full_book_context,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
            # Add instruction to translate only this section
            user_message = f"Translate only the following section:\n\n{text}"
        else:
            # Standard system message without caching
            system_content = self._get_prompt()
            user_message = text

        body = {
            'stream': self.stream,
            'max_tokens': max_tokens,
            'model': self.model,
            'top_k': self.top_k,
            'system': system_content,
            'messages': [{'role': 'user', 'content': user_message}]
        }
        sampling_value = getattr(self, self.sampling)
        body.update({self.sampling: sampling_value})

        return json.dumps(body)

    def get_result(self, response: Response | str) -> str:
        if self.stream:
            return self._parse_stream(response)

        response_json = json.loads(response)
        response_content_text: str = response_json['content'][0]['text']
        return response_content_text

    def _parse_stream(self, data: Response) -> Generator:
        while True:
            try:
                line = data.readline().decode('utf-8').strip()
            except IncompleteRead:
                continue
            except Exception as e:
                raise Exception(
                    _('Can not parse returned response. Raw data: {}')
                    .format(str(e)))

            if line.startswith('data:'):
                chunk: dict = json.loads(line.split('data: ')[1])
                event_type: str = chunk['type']

                if event_type not in self.valid_event_types:
                    raise Exception(
                        _('Invalid event type received: {}')
                        .format(event_type))

                if event_type == 'message_stop':
                    break
                elif event_type == 'content_block_delta':
                    delta = chunk.get('delta')
                    if delta is not None:
                        yield str(delta.get('text'))
                elif event_type == 'error':
                    raise Exception(
                        _('Error received: {}')
                        .format(chunk['error']['message']))


class ClaudeBatchTranslate(ClaudeTranslate):
    """Message Batches API for asynchronous bulk translation with 50% cost reduction.

    The message batches API allows sending batches of up to 100,000 messages.
    Batches are processed asynchronously with results returned when complete.
    Costs 50% less than standard API calls.

    Combined with prompt caching, offers up to 84% total cost savings.
    Trade-off: Processing takes up to 24 hours (most <1 hour) vs immediate results.

    More info: https://docs.anthropic.com/en/docs/build-with-claude/message-batches
    """

    name = 'Claude Batch'
    alias = 'Claude Batch (Anthropic)'

    # Batch-specific settings
    stream = False  # Batches don't support streaming
    batch_poll_interval = 60.0  # Poll every 60 seconds

    def __init__(self):
        super().__init__()
        # Batch API uses different endpoints
        self.batch_endpoint = 'https://api.anthropic.com/v1/messages/batches'
        self.batch_poll_interval = self.config.get('batch_poll_interval', self.batch_poll_interval)

    def create_batch_request(self, custom_id, text):
        """Create a single request object for batch API."""
        # Parse the body that get_body() creates
        body_json = json.loads(self.get_body(text))
        # Remove stream parameter (not supported in batches)
        body_json.pop('stream', None)

        return {
            'custom_id': custom_id,
            'params': body_json
        }

    def create_batch(self, requests):
        """Submit a batch of translation requests."""
        batch_body = json.dumps({'requests': requests})
        response = request(
            self.batch_endpoint,
            data=batch_body,
            headers=self.get_headers(),
            method='POST',
            timeout=int(self.request_timeout),
            proxy_uri=self.proxy_uri if self.proxy_type == 'http' else None
        )
        batch = json.loads(response)
        return batch['id']

    def poll_batch(self, batch_id):
        """Poll batch status until completion."""
        while True:
            response = request(
                f'{self.batch_endpoint}/{batch_id}',
                headers=self.get_headers(),
                timeout=int(self.request_timeout),
                proxy_uri=self.proxy_uri if self.proxy_type == 'http' else None
            )
            batch = json.loads(response)

            if batch['processing_status'] == 'ended':
                return batch

            # Log progress
            counts = batch['request_counts']
            log.info(f"Batch {batch_id}: {counts['succeeded']}/{counts['processing']} completed")

            time.sleep(self.batch_poll_interval)

    def get_batch_results(self, results_url):
        """Retrieve and parse batch results."""
        response = request(
            results_url,
            headers=self.get_headers(),
            timeout=int(self.request_timeout),
            proxy_uri=self.proxy_uri if self.proxy_type == 'http' else None
        )

        # Results are in JSONL format (one JSON object per line)
        results = {}
        for line in response.decode('utf-8').strip().split('\n'):
            if line:
                result = json.loads(line)
                custom_id = result['custom_id']
                if result['result']['type'] == 'succeeded':
                    message = result['result']['message']
                    translation = message['content'][0]['text']
                    results[custom_id] = translation
                else:
                    # Handle errors
                    error_type = result['result'].get('error', {}).get('type', 'unknown')
                    raise Exception(f"Batch request {custom_id} failed: {error_type}")

        return results

    def translate(self, content):
        """Override translate to use batch API."""
        # For single paragraph translation, create a single-item batch
        batch_request = self.create_batch_request('translation-0', content)
        batch_id = self.create_batch([batch_request])

        log.info(f'Created batch {batch_id}, polling for completion...')
        batch = self.poll_batch(batch_id)

        if batch['results_url']:
            results = self.get_batch_results(batch['results_url'])
            return results.get('translation-0', '')
        else:
            raise Exception('Batch completed but no results URL provided')

