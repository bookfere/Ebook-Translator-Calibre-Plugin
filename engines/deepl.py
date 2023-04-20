import json
import time
import random

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class DeeplTranslate(Base):
    name = 'DeepL'
    support_lang = 'deepl.json'
    endpoint = {
        'translate': 'https://api-free.deepl.com/v2/translate',
        'usage': 'https://api-free.deepl.com/v2/usage',
    }

    def get_usage(self):
        # See: https://www.deepl.com/docs-api/general/get-usage/
        def usage_info(data):
            usage = json.loads(data)
            total = usage.get('character_limit')
            used = usage.get('character_count')
            left = total - used
            return _('{} total, {} used, {} left').format(total, used, left)

        return self.get_result(
            self.endpoint.get('usage'), callback=usage_info, silence=True,
            headers={'Authorization': 'DeepL-Auth-Key %s' % self.api_key})

    def translate(self, text):
        headers = {'Authorization': 'DeepL-Auth-Key %s' % self.api_key}

        data = {
            'text': text,
            'target_lang': self._get_target_code()
        }

        if not self._is_auto_lang():
            data['source_lang'] = self._get_source_code()

        return self.get_result(
            self.endpoint.get('translate'), data, headers, method='POST')

    def parse(self, data):
        return json.loads(data)['translations'][0]['text']


class DeeplProTranslate(DeeplTranslate):
    name = 'DeepL(Pro)'
    endpoint = {
        'translate': 'https://api.deepl.com/v2/translate',
        'usage': 'https://api.deepl.com/v2/usage',
    }


class DeeplFreeTranslate(Base):
    name = 'DeepL(Free)'
    support_lang = 'deepl.json'
    endpoint = 'https://www2.deepl.com/jsonrpc?client=chrome-extension,1.4.0'
    need_api_key = False

    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'Authorization': 'None',
        'Authority': 'www2.deepl.com',
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'DeepLBrowserExtension/1.3.0 Mozilla/5.0 (Macintosh;'
        ' Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/111.0.0.0 Safari/537.36',
        'Origin': 'chrome-extension://cofdbpoegempjloogbagkncekinflcnj',
        'Referer': 'https://www.deepl.com/',
    }

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

    def _data(self, text):
        uid, ts = self._vars(text)
        data = json.dumps({
            "jsonrpc": "2.0",
            "method": "LMT_handle_texts",
            "params": {
                "texts": [{"text": text}],
                "splitting": "newlines",
                "lang": {
                    "source_lang_user_selected": self._get_source_code(),
                    "target_lang": self._get_target_code(),
                },
                "timestamp": ts
            },
            "id": uid
        }, separators=',:')

        # ((e, t) => e = (t.id + 3) % 13 == 0 || (t.id + 5) % 29 == 0
        # ? e.replace('"method":"', '"method" : "')
        # : e.replace('"method":"', '"method": "'))
        if (uid + 3) % 13 == 0 or (uid + 5) % 29 == 0:
            return data.replace('"method":"', '"method" : "')
        return data.replace('"method":"', '"method": "')

    def translate(self, text):
        return self.get_result(
            self.endpoint, self._data(text), self.headers, method='POST')

    def parse(self, data):
        return json.loads(data)['result']['texts'][0]['text']
