import json

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
