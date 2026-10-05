import json
import time
import random

from ..lib.utils import request

from .base import Base
from .languages import deepl, deepl_free


load_translations()  # type: ignore


class DeeplTranslate(Base):
    name = 'DeepL'
    alias = 'DeepL'
    lang_codes = Base.load_lang_codes(deepl)
    endpoint = 'https://api-free.deepl.com/v2/translate'
    usage_endpoint = 'https://api-free.deepl.com/v2/usage'
    # api_key_hint = 'xxx-xxx-xxx:fx'
    placeholder = ('<m id={} />', r'<m\s+id={}\s+/>')
    api_key_errors = ['403', '456']

    def get_usage(self):
        # See: https://www.deepl.com/docs-api/general/get-usage/
        headers = {'Authorization': 'DeepL-Auth-Key %s' % self.api_key}
        try:
            response = request(
                self.usage_endpoint, headers=headers, proxy_uri=self.proxy_uri)
            usage = json.loads(response)
        except Exception:
            return None
        total = usage.get('character_limit')
        used = usage.get('character_count')
        left = total - used

        return _('{} total, {} used, {} left').format(total, used, left)

    def get_headers(self):
        return {'Authorization': 'DeepL-Auth-Key %s' % self.api_key}

    def get_body(self, text):
        body = {
            'text': text,
            'target_lang': self._get_target_code()
        }
        if not self._is_auto_lang():
            body.update(source_lang=self._get_source_code())

        return body

    def get_result(self, response):
        return json.loads(response)['translations'][0]['text']


class DeeplProTranslate(DeeplTranslate):
    name = 'DeepL(Pro)'
    alias = 'DeepL (Pro)'
    endpoint = 'https://api.deepl.com/v2/translate'
    usage_endpoint = 'https://api.deepl.com/v2/usage'


class DeeplFreeTranslate(Base):
    name = 'DeepL(Free)'
    alias = 'DeepL (Free)'
    free = True
    lang_codes = Base.load_lang_codes(deepl_free)
    endpoint = 'https://oneshot-free.www.deepl.com/v1/storefront/translate'
    need_api_key = False
    placeholder = DeeplTranslate.placeholder

    concurrency_limit = 1
    request_interval = 1.0

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
            'Origin': 'https://www.deepl.com',
            'Referer': 'https://www.deepl.com/',
        }

    def get_body(self, text):
        body = {
            'app_information': {
                'app_build': 'Chrome',
                'app_version': 'any',
                'instance_id': '%08x-%04x-%04x-%04x-%012x' % (
                    random.getrandbits(32), random.getrandbits(16),
                    random.getrandbits(16), random.getrandbits(16),
                    random.getrandbits(48)),
                'os': 'Windows',
                'os_version': 'any',
            },
            'language_model': 'next-gen',
            'source_lang': self._get_source_code(),
            'text': [text],
            'usage_type': 'Translate',
        }
        body['target_lang'] = self._get_target_code()

        return json.dumps(body, separators=(',', ':'))

    def get_result(self, response):
        return json.loads(response)['translations'][0]['text']
