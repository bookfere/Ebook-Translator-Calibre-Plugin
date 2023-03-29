import json

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class GoogleTranslate(Base):
    def get_endpoint(self):
        return 'https://translate.googleapis.com/translate_a/single'

    def need_sleep(self):
        return True

    def translate(self, text):
        sl = self._get_lang_code(self.source_lang)
        tl = self._get_lang_code(self.target_lang)
        data = self.request({
            'client': 'gtx',
            'sl': sl,
            'tl': tl,
            'dt': 't',
            'q': text,
        })

        return ''.join(i[0] for i in json.loads(data)[0])
