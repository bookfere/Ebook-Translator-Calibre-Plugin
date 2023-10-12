import re
import os
import time
import json
import os.path
from subprocess import Popen, PIPE

from ..lib.exception import BadApiKeyFormat

from .base import Base
from .languages import google


load_translations()


class GoogleFreeTranslate(Base):
    name = 'Google(Free)'
    alias = 'Google (Free)'
    lang_codes = Base.load_lang_codes(google)
    endpoint = 'https://translate.googleapis.com/translate_a/single'
    need_api_key = False

    def translate(self, text):
        headers = {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'DeepLBrowserExtension/1.3.0 Mozilla/5.0 (Macintosh;'
            ' Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)'
            ' Chrome/111.0.0.0 Safari/537.36',
        }

        data = {
            'client': 'gtx',
            'sl': self._get_source_code(),
            'tl': self._get_target_code(),
            'dt': 't',
            'dj': 1,
            'q': text,
        }

        # The POST method is unstable, despite its ability to send more text.
        # However, it can be used occasionally with an unacceptable length.
        method = 'GET' if len(text) <= 1800 else 'POST'
        return self.get_result(
            self.endpoint, data, headers, method=method, callback=self._parse)

    def _parse(self, data):
        # return ''.join(i[0] for i in json.loads(data)[0])
        return ''.join(i['trans'] for i in json.loads(data)['sentences'])


class GoogleTranslate:
    def _get_credential(self, key_file_path):
        """Default lifetime of api key is 3600 seconds."""
        timestamp, old_api_key = self.api_key_cache or (None, None)
        if old_api_key is not None and time.time() - timestamp < 3600:
            return old_api_key
        os.environ.update(GOOGLE_APPLICATION_CREDENTIALS=key_file_path)
        self.proxy_uri and os.environ.update(
            http_proxy=self.proxy_uri, https_proxy=self.proxy_uri)
        process = Popen(
            ['gcloud', 'auth', 'application-default', 'print-access-token'],
            stdout=PIPE, stderr=PIPE)
        if process.wait() != 0:
            raise Exception(_('Can not obtain Google API key. Reason: {}')
                            .format(process.stderr.read().decode('utf-8')))
        for proxy in ('http_proxy', 'https_proxy'):
            if proxy in os.environ:
                del os.environ[proxy]
        new_api_key = process.stdout.read().decode('utf-8').strip()
        self.api_key_cache[:] = [time.time(), new_api_key]
        return new_api_key


class GoogleBasicTranslate(Base, GoogleTranslate):
    name = 'Google(Basic)'
    alias = 'Google (Basic)'
    lang_codes = Base.load_lang_codes(google)
    endpoint = 'https://translation.googleapis.com/language/translate/v2'
    api_key_hint = 'API key or KEY_PATH'
    api_key_errors = ['429']
    api_key_cache = []

    def translate(self, text):
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        data = {
            'format': 'html',
            'model': 'nmt',
            'target': self._get_target_code(),
            'q': text
        }

        if self.api_key:
            if os.path.sep not in self.api_key:
                data.update(key=self.api_key)
            else:
                api_key = self._get_credential(self.api_key)
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer %s' % api_key
                }
                data = json.dumps(data)

        if not self._is_auto_lang():
            data.update(source=self._get_source_code())

        return self.get_result(
            self.endpoint, data, headers, method='POST', callback=self._parse)

    def _parse(self, data):
        translations = json.loads(data)['data']['translations']
        return ''.join(i['translatedText'] for i in translations)


class GoogleAdvancedTranslate(Base, GoogleTranslate):
    name = 'Google(Advanced)'
    alias = 'Google (Advanced)'
    lang_codes = Base.load_lang_codes(google)
    endpoint = 'https://translation.googleapis.com/v3/projects/{}'
    api_key_hint = 'PROJECT_NUMBER_OR_ID|KEY_PATH'
    api_key_pattern = r'^[^\s\|]+?\|.+$'
    api_key_errors = ['429']
    api_key_cache = []

    def translate(self, text):
        try:
            project_id, key_file_path = re.split(r'\|', self.api_key)
        except Exception:
            raise BadApiKeyFormat(self.api_key_error_message())

        endpoint = self.endpoint.format('%s:translateText' % project_id)
        api_key = self._get_credential(key_file_path)

        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % api_key
        }

        data = {
            'targetLanguageCode': self._get_target_code(),
            'contents': [text],
            'mimeType': 'text/plain',
        }

        if not self._is_auto_lang():
            data.update(sourceLanguageCode=self._get_source_code())

        return self.get_result(
            endpoint, json.dumps(data), headers, method='POST',
            callback=self._parse)

    def _parse(self, data):
        translations = json.loads(data)['translations']
        return ''.join(i['translatedText'] for i in translations)
