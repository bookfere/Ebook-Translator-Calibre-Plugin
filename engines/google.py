import json

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class GoogleTranslate(Base):
    name = 'Google'
    support_lang = 'google.json'
    endpoint = 'https://translate.googleapis.com/translate_a/single'
    need_api_key = False

    @Base._translate
    def translate(self, text):
        sl = self._get_source_lang_code()
        tl = self._get_target_lang_code()

        return self.request({
            'client': 'gtx',
            'sl': sl,
            'tl': tl,
            'dt': 't',
            'q': text,
        })

    def parse(self, response):
        return ''.join(i[0] for i in json.loads(response)[0])
