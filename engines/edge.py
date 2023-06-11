import re
import os
import time
import json
import os.path
from subprocess import Popen, PIPE

from ..exceptions.engine import IncorrectApiKeyFormat
from .base import load_lang_codes, Base
from .languages import edge


load_translations()

lang_codes = load_lang_codes(edge)

class EdgeTranslate(Base):
    name = 'msEdge'
    alias = 'msEdge'
    lang_codes = lang_codes
    need_api_key = False
    access_info = None

    endpoint = f'https://api-edge.cognitive.microsofttranslator.com/translate?from=%s&to=%s&api-version=3.0&includeSentenceLength=true'

    def translate(self, text):
        trans_to =  self._get_target_code()
        if self._is_auto_lang():
            self.endpoint = f'https://api-edge.cognitive.microsofttranslator.com/translate?to={trans_to}&api-version=3.0&includeSentenceLength=true'
        else:
            trans_from= self._get_source_code()
            self.endpoint = f'https://api-edge.cognitive.microsofttranslator.com/translate?from={trans_from}&to={trans_to}&api-version=3.0&includeSentenceLength=true'
            
        app_key = self.get_app_key()
        headers = {'Content-Type': 'application/json',
                   'authorization': f'Bearer {app_key}'}
        data = json.dumps(
            [{'text': text.replace('"','\"')}]
        )
        result = self.get_result(self.endpoint, data, headers, method='POST')
        return result

    def parse(self, response):
        return json.loads(response)[0]['translations'][0]['text']

    def get_key(self, result):
        return result
    def get_app_key(self):
        if self.access_info is None or datetime.now() > self.access_info['Expire']:
            auth_url = 'https://edge.microsoft.com/translate/auth'
            app_key = self.get_result(auth_url, callback=self.get_key,  method='GET')
            self.access_info = parseJWT(app_key)
        else:
            app_key = self.access_info['Token']
        return app_key


import base64
import json
from datetime import datetime

def parseJWT(token):
    parts = token.split(".")
    if len(parts) <= 1:
        raise Exception("invlaid token")
    base64Url = parts[1]
    if not base64Url:
        raise Exception("invalid base64 url token")
    base64Url = base64Url.replace('-', '+').replace('_', '/')
    jsonPayload = base64.b64decode(base64Url + '===').decode('utf-8')
    parsed = json.loads(jsonPayload)
    expiredDate = datetime.fromtimestamp(parsed['exp'])
    return {
        'Token': token,
        'Expire': expiredDate
    }

