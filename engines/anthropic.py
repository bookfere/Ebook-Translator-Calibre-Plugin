import json
from typing import Generator
from urllib.parse import urljoin
from http.client import IncompleteRead

from mechanize._response import response_seek_wrapper as Response

from .. import EbookTranslator
from ..lib.utils import request

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
        if self.model is not None:
            # For Claude Sonnet 3.7 - enable 128K output tokens
            # (requires user to enable this option)
            if self.enable_extended_output and self.model.startswith('claude-3-7-sonnet-'):
                headers['anthropic-beta'] = 'output-128k-2025-02-19'

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
                headers['anthropic-beta'] = 'context-1m-2025-08-07'

        return headers

    def get_body(self, text):
        body = {
            'stream': self.stream,
            'max_tokens': 4096,
            'model': self.model,
            'top_k': self.top_k,
            'system': self._get_prompt(),
            'messages': [{'role': 'user', 'content': text}]
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


class ClaudeBatchTranslate:
    """TODO: use the message batches api (currently only the streaming api can
    be used). The message batches api allows sending any number of batches of
    up to 100,000 messages per batch. Batches are processed asynchronously with
    results returned as soon as the batch is complete and cost 50% less than
    standard API calls (more info here:
    https://docs.anthropic.com/en/docs/build-with-claude/message-batches)
    """
