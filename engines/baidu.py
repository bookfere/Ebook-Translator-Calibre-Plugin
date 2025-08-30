import re
import json
import random
import hashlib

from .. import _z
from ..lib.exception import BadApiKeyFormat

from .base import Base
from .languages import baidu


load_translations()  # type: ignore


class BaiduTranslate(Base):
    name = 'Baidu'
    alias = _z('Baidu')
    lang_codes = Base.load_lang_codes(baidu)
    endpoint = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    api_key_hint = 'appid|appkey'
    api_key_pattern = r'^[^\s:\|]+?[:\|][^\s:\|]+$'
    api_key_errors = ['54004']

    def get_headers(self):
        return {'Content-Type': 'application/x-www-form-urlencoded'}

    def get_body(self, text):
        try:
            app_id, app_key = re.split(r'[:\|]', self.api_key or '')
        except Exception:
            raise BadApiKeyFormat(self.api_key_error_message())

        salt = random.randint(32768, 65536)
        sign_str = app_id + text + str(salt) + app_key
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

        return {
            'appid': app_id,
            'q': text,
            'from': self._get_source_code(),
            'to': self._get_target_code(),
            'salt': salt,
            'sign': sign
        }

    def get_result(self, response):
        return json.loads(response)['trans_result'][0]['dst']
