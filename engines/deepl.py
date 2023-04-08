import json

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class DeeplTranslate(Base):
    name = 'DeepL'
    support_lang = 'deepl.json'
    endpoint = 'https://api-free.deepl.com/v2/translate'

    @Base._translate
    def translate(self, text):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'DeepL-Auth-Key %s' % self.api_key
        }

        data = {
            'text': text,
            'target_lang': self._get_target_lang_code()
        }

        if not self._is_auto_lang():
            data['source_lang'] = self._get_source_lang_code()

        return self.request(data, method='POST', headers=headers)

    def parse(self, response):
        return json.loads(response)['translations'][0]['text']
