import json
import time
import uuid
import hashlib

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class YoudaoTranslate(Base):
    name = 'Youdao'
    support_lang = 'youdao.json'
    endpoint = 'https://openapi.youdao.com/api'
    api_key_hint = 'appid:appsecret'

    def encrypt(self, signStr):
        hash_algorithm = hashlib.sha256()
        hash_algorithm.update(signStr.encode('utf-8'))
        return hash_algorithm.hexdigest()

    def truncate(self, text):
        if text is None:
            return None
        size = len(text)
        return text if size <= 20 else \
            text[0:10] + str(size) + text[size - 10:size]

    @Base._translate
    def translate(self, text):
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        try:
            app_key, app_secret = self.api_key.split(':')
        except Exception:
            raise Exception(_('Incorrect format of APP key and secret.'))

        curtime = str(int(time.time()))
        salt = str(uuid.uuid1())
        sign_str = app_key + self.truncate(text) + salt + curtime + app_secret
        sign = self.encrypt(sign_str)

        data = {
            'from': self._get_source_lang_code(),
            'to': self._get_target_lang_code(),
            'signType': 'v3',
            'curtime': curtime,
            'appKey': app_key,
            'q': text,
            'salt': salt,
            'sign': sign,
            'vocabId': False,
        }

        return self.request(data, method='POST', headers=headers)

    def parse(self, response):
        return json.loads(response)['translation'][0]
