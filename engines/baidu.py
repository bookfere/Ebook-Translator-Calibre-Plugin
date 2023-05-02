import json
import random
import hashlib

from calibre_plugins.ebook_translator.utils import _z
from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class BaiduTranslate(Base):
    name = 'Baidu'
    alias = _z('Baidu')
    support_lang = 'baidu.json'
    endpoint = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    api_key_hint = 'appid:appkey'
    api_key_rule = r'^[^\s:]+?:[^\s:]+$'

    def translate(self, text):
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        try:
            app_id, app_key = self.api_key.split(':')
        except Exception:
            raise Exception(self.get_api_key_error())

        salt = random.randint(32768, 65536)
        sign_str = app_id + text + str(salt) + app_key
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

        data = {
            'appid': app_id,
            'q': text,
            'from': self._get_source_code(),
            'to': self._get_target_code(),
            'salt': salt,
            'sign': sign
        }

        return self.get_result(self.endpoint, data, headers, method='POST')

    def parse(self, response):
        return json.loads(response)['trans_result'][0]['dst']
