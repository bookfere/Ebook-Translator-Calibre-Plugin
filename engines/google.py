import json

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class GoogleFreeTranslate(Base):
    name = 'Google(Free)'
    alias = 'Google (Free)'
    support_lang = 'google.json'
    endpoint = 'https://translate.googleapis.com/translate_a/single'
    need_api_key = False

    def translate(self, text):
        data = {
            'client': 'gtx',
            'sl': self._get_source_code(),
            'tl': self._get_target_code(),
            'dt': 't',
            'q': text,
        }

        return self.get_result(self.endpoint, data, method='POST')

    def parse(self, data):
        return ''.join(i[0] for i in json.loads(data)[0])


class GoogleBasicTranslate(Base):
    name = 'Google(Basic)'
    alias = 'Google (Basic)'
    support_lang = 'google.json'
    endpoint = 'https://translation.googleapis.com/language/translate/v2'
    need_api_key = True

    def translate(self, text):
        data = {
            'key': self.api_key,
            'format': 'html',
            'model': 'nmt',
            'target': self._get_target_code(),
            'q': text,
        }

        if not self._is_auto_lang():
            data.update(source= self._get_source_code())

        return self.get_result(self.endpoint, data, method='POST')

    def parse(self, data):
        return json.loads(data)['data']['translations'][0]['translatedText']