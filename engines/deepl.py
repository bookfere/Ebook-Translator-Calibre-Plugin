import json

from calibre.utils.localization import lang_as_iso639_1
from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class DeeplTranslate(Base):
    source_lang_codes = [
        'bg', 'cs', 'da', 'de', 'el', 'en', 'es', 'et', 'fi', 'fr', 'hu', 'id',
        'it', 'ja', 'ko', 'lt', 'lv', 'nb', 'nl', 'pl', 'pt', 'ro', 'ru', 'sk',
        'sl', 'sv', 'tr', 'uk', 'zh',
    ]

    target_lang_codes = [
        'bg', 'cs', 'da', 'de', 'el', 'en', 'en-gb', 'en-us', 'es', 'et', 'fi',
        'fr', 'hu', 'id', 'it', 'ja', 'ko', 'lt', 'lv', 'nb', 'nl', 'pl', 'pt',
        'pt-br', 'pt-pt', 'ro', 'ru', 'sk', 'sl', 'sv', 'tr', 'uk', 'zh',
    ]

    def _get_support_code(self, language, codes):
        code = self._get_lang_code(language)
        code = code.lower() if code else None
        if code != 'auto' and code not in codes and \
                lang_as_iso639_1(code) not in codes:
            raise Exception(_('DeepL do not support the language: {}')
                            .format(language))
        return code.upper()

    def get_endpoint(self):
        return 'https://api-free.deepl.com/v2/translate'

    def translate(self, text):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'DeepL-Auth-Key %s' % self.api_key
        }

        data = {
            'text': text,
            'target_lang': self._get_support_code(
                self.target_lang, self.target_lang_codes)
        }

        if not self._is_auto_lang():
            source_lang = self._get_support_code(
                self.source_lang, self.source_lang_codes)
            data['source_lang'] = source_lang

        response = self.request(data, method='POST', headers=headers)
        return json.loads(response)['translations'][0]['text']
