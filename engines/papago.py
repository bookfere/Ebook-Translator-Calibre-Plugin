import json

from .base import Base
from .languages import papago

load_translations()


class PapagoTranslate(Base):
    name = 'papago'
    alias = 'Papago'
    lang_codes = Base.load_lang_codes(papago)
    endpoint = {
        'translate': 'https://naveropenapi.apigw.ntruss.com/nmt/v1/translation',
    }
    need_api_key = False

    client_id = ""
    client_secret = ""
    glossary_key = ""

    def __init__(self):
        Base.__init__(self)

        self.client_id = self.config.get('client_id', self.client_id)
        self.client_secret = self.config.get('client_secret', self.client_secret)
        self.glossary_key = self.config.get('glossary_key', self.glossary_key)

    def translate(self, text):
        headers = {
            "Content-Type": "application/json",
            "X-NCP-APIGW-API-KEY-ID": self.client_id,
            "X-NCP-APIGW-API-KEY": self.client_secret
        }

        data = json.dumps({
            'text': text,
            'source': self._get_source_code(),
            'target': self._get_target_code(),
            'glossaryKey': self.glossary_key
        })

        return self.get_result(
            self.endpoint.get('translate'), data, headers, method='POST',
            callback=lambda r: json.loads(r)['message']['result']['translatedText'])
