import json
import base64
from datetime import datetime
from urllib.parse import urlencode

from calibre.utils.localization import _  # type: ignore

from ..lib.utils import request

from .base import Base
from .languages import microsoft
from .openai import ChatgptTranslate


load_translations()  # type: ignore


class MicrosoftEdgeTranslate(Base):
    name = 'MicrosoftEdge(Free)'
    alias = 'Microsoft Edge (Free)'
    free = True
    lang_codes = Base.load_lang_codes(microsoft)
    endpoint = 'https://edge.microsoft.com/translate/translatetext'
    need_api_key = False
    access_info = None

    def get_endpoint(self):
        query = {
            'isEnterpriseClient': False,
            'to': self._get_target_code(),
        }
        if not self._is_auto_lang():
            query['from'] = self._get_source_code()
        return '%s?%s' % (self.endpoint, urlencode(query))

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
        }

    def get_body(self, text):
        return json.dumps([text])

    def get_result(self, response):
        return json.loads(response)[0]['translations'][0]['text']


class AzureChatgptTranslate(ChatgptTranslate):
    name = 'ChatGPT(Azure)'
    alias = 'ChatGPT (Azure)'
    endpoint = (
        'https://{your-resource-name}.openai.azure.com/openai/deployments/'
        '{deployment-id}/chat/completions?api-version={api-version}')

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'api-key': self.api_key
        }

    def get_body(self, text):
        # Add system prompt with context if available
        system_content = self.get_prompt()
        if getattr(self, 'context_manager', None):
            current_row = getattr(self.local_state, 'current_row', -1)
            context_block = self.context_manager.get_context_block(current_row)
            if context_block:
                system_content += f"\n\n{context_block}"
        messages = [{'role': 'system', 'content': system_content}]
        messages.append({'role': 'user', 'content': text})

        body = {
            'stream': self.stream,
            'messages': messages
        }
        sampling_value = getattr(self, self.sampling)
        body.update({self.sampling: sampling_value})
        return json.dumps(body)
