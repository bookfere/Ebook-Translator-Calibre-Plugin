import json
import time
import random

from ..lib.utils import request

from .base import Base
from .languages import deepl


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
    lang_codes = Base.load_lang_codes(deepl)
    endpoint = 'https://www2.deepl.com/jsonrpc?client=chrome-extension,1.5.1'
    need_api_key = False
    placeholder = DeeplTranslate.placeholder

    concurrency_limit = 1
    request_interval = 1.0

    def _vars(self, text):
        # t.forEach((e => r += (e.match(/[i]/g) || []).length)),
        # a.timestamp = o - o % r + r;
        uid = random.randint(1000000000, 9999999999)
        count_i = text.count('i')
        ts = int(time.time() * 1000)
        if count_i > 0:
            count_i += 1
            ts = ts - ts % count_i + count_i
        return uid, ts

    def get_headers(self):
        return {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'en-US,en;q=0.9',
            'Authorization': 'None',
            'Authority': 'www2.deepl.com',
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'DeepLBrowserExtension/1.5.1 Mozilla/5.0 '
            '(Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, '
            'like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Origin': 'chrome-extension://cofdbpoegempjloogbagkncekinflcnj',
            'Referer': 'https://www.deepl.com/',
        }

    def get_body(self, text):
        regional_variant = {}
        target_lang = self._get_target_code()
        if '-' in target_lang:
            portions = target_lang.split('-')
            variant = '-'.join([portions[0].lower(), portions[1]])
            regional_variant['regionalVariant'] = variant
            target_lang = portions[0]
        uid, ts = self._vars(text)

        body = json.dumps({
            'jsonrpc': '2.0',
            'method': 'LMT_handle_texts',
            'params': {
                'commonJobParams': regional_variant,
                'texts': [{'text': text}],
                'splitting': 'newlines',
                'lang': {
                    'source_lang_user_selected': self._get_source_code(),
                    'target_lang': target_lang,
                },
                'timestamp': ts
            },
            'id': uid
        }, separators=(',', ':'))

        # ((e, t) => e = (t.id + 3) % 13 == 0 || (t.id + 5) % 29 == 0
        # ? e.replace('"method":"', '"method" : "')
        # : e.replace('"method":"', '"method": "'))
        if (uid + 3) % 13 == 0 or (uid + 5) % 29 == 0:
            return body.replace('"method":"', '"method" : "')
        return body.replace('"method":"', '"method": "')

    def get_result(self, response):
        return json.loads(response)['result']['texts'][0]['text']
