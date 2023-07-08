import re
import json
import time
import uuid
import hashlib

from .. import _z
from ..lib.exception import BadApiKeyFormat

from .base import Base
from .languages import youdao


load_translations()


class YoudaoTranslate(Base):
    name = 'Youdao'
    alias = _z('Youdao')
    lang_codes = Base.load_lang_codes(youdao)
    endpoint = 'https://openapi.youdao.com/api'
    api_key_hint = 'appid|appsecret'
    api_key_pattern = r'^[^\s:\|]+?[:\|][^\s:\|]+$'
    api_key_errors = ['401']

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

    def translate(self, text):
        try:
            app_key, app_secret = re.split(r'[:\|]', self.api_key)
        except Exception:
            raise BadApiKeyFormat(self.api_key_error_message())

        curtime = str(int(time.time()))
        salt = str(uuid.uuid1())
        sign_str = app_key + self.truncate(text) + salt + curtime + app_secret
        sign = self.encrypt(sign_str)

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        data = {
            'from': self._get_source_code(),
            'to': self._get_target_code(),
            'signType': 'v3',
            'curtime': curtime,
            'appKey': app_key,
            'q': text,
            'salt': salt,
            'sign': sign,
            'vocabId': False,
        }

        return self.get_result(self.endpoint, data, headers, method='POST')

    def parse(self, data):
        return json.loads(data)['translation'][0]
