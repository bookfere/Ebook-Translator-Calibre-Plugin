import re
import os
import sys
import time
import json
import os.path
from html import unescape
from subprocess import Popen, PIPE
from urllib.parse import urlencode
from http.client import IncompleteRead

from ..lib.utils import traceback_error

from .base import Base
from .languages import lang_directionality
from .languages import google, gemini


load_translations()


class GoogleFreeTranslateNew(Base):
    name = 'Google(Free)New'
    alias = 'Google (Free) - New'
    free = True
    lang_codes = Base.load_lang_codes(google)
    lang_codes_directionality = \
        Base.load_lang_codes_directionality(lang_directionality)
    endpoint: str = 'https://translate-pa.googleapis.com/v1/translate'
    need_api_key = False

    def get_headers(self):
        return {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 '
            'Safari/537.36',
        }

    def get_body(self, text):
        self.method = 'GET'
        return {
            'params.client': 'gtx',
            'query.source_language': self._get_source_code(),
            'query.target_language': self._get_target_code(),
            'query.display_language': 'en-US',
            'data_types': 'TRANSLATION',
            # 'data_types': 'SENTENCE_SPLITS',
            # 'data_types': 'BILINGUAL_DICTIONARY_FULL',
            'key': 'AIzaSyDLEeFI5OtFBwYBIoK_jj5m32rZK5CkCXA',
            'query.text': text,
        }

    def get_result(self, response):
        return json.loads(response)['translation']


class GoogleFreeTranslateHtml(Base):
    name = 'Google(Free)Html'
    alias = 'Google (Free) - HTML'
    free = True
    lang_codes = Base.load_lang_codes(google)
    lang_codes_directionality = \
        Base.load_lang_codes_directionality(lang_directionality)
    endpoint: str = 'https://translate-pa.googleapis.com/v1/translateHtml'
    need_api_key = False

    def get_headers(self):
        return {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json+protobuf',
            'X-Goog-Api-Key': 'AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 '
            'Safari/537.36',
        }

    def get_body(self, text):
        return json.dumps([
            [
                [text],
                self._get_source_code(),
                self._get_target_code()
            ],
            "wt_lib"
        ])

    def get_result(self, response):
        return json.loads(response)[0][0]


class GoogleFreeTranslate(Base):
    name = 'Google(Free)'
    alias = 'Google (Free) - Old'
    free = True
    lang_codes = Base.load_lang_codes(google)
    lang_codes_directionality = \
        Base.load_lang_codes_directionality(lang_directionality)
    endpoint = 'https://translate.googleapis.com/translate_a/single'
    need_api_key = False

    def get_headers(self):
        return {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'DeepLBrowserExtension/1.3.0 Mozilla/5.0 (Macintosh;'
            ' Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)'
            ' Chrome/111.0.0.0 Safari/537.36',
        }

    def get_body(self, text):
        # The POST method is unstable, despite its ability to send more text.
        # However, it can be used occasionally with an unacceptable length.
        self.method = 'GET' if len(text) <= 1800 else 'POST'
        return {
            'client': 'gtx',
            'sl': self._get_source_code(),
            'tl': self._get_target_code(),
            'dt': 't',
            'dj': 1,
            'q': text,
        }

    def get_result(self, response):
        # return ''.join(i[0] for i in json.loads(data)[0])
        return ''.join(i['trans'] for i in json.loads(response)['sentences'])


class GoogleTranslateMixin:
    api_key_errors = ['429']
    api_key_cache = []
    gcloud = None
    project_id = None
    using_tip = _(
        'This plugin uses Application Default Credentials (ADC) in your local '
        'environment to access your Google Translate service. To set up the '
        'ADC, follow these steps:\n'
        '1. Install the gcloud CLI by checking out its instructions {}.\n'
        '2. Run the command: gcloud auth application-default login.\n'
        '3. Sign in to your Google account and grant needed privileges.') \
        .format('<sup><a href="https://cloud.google.com/sdk/docs/install">[^]'
                '</a></sup>').replace('\n', '<br />')

    def _run_command(self, command, silence=False):
        message = _('Cannot run the command "{}".')
        try:
            startupinfo = None
            # Prevent the popping console window on Windows.
            if sys.platform == 'win32':
                from subprocess import STARTUPINFO, STARTF_USESHOWWINDOW
                startupinfo = STARTUPINFO()
                startupinfo.dwFlags |= STARTF_USESHOWWINDOW
            process = Popen(
                command, stdout=PIPE, stderr=PIPE, universal_newlines=True,
                startupinfo=startupinfo)
        except Exception:
            if silence:
                return None
            raise Exception(
                message.format(command, '\n\n%s' % traceback_error()))
        if process.wait() != 0:
            if silence:
                return None
            raise Exception(
                message.format(command, '\n\n%s' % process.stderr.read()))
        return process.stdout.read().strip()

    def _get_gcloud_command(self):
        if self.gcloud is not None:
            return self.gcloud
        if sys.platform == 'win32':
            name = 'gcloud.cmd'
            which = 'where'
            base = r'google-cloud-sdk\bin\%s' % name
            paths = [
                r'"%s\Google\Cloud SDK\%s"'
                % (os.environ.get('programfiles(x86)'), base),
                r'"%s\AppData\Local\Google\Cloud SDK\%s"'
                % (os.environ.get('userprofile'), base)]
        else:
            name = 'gcloud'
            which = 'which'
            paths = ['/usr/local/bin/%s' % name]
        gcloud = self.get_external_program(name, paths)
        if gcloud is None:
            gcloud = self._run_command([which, name], silence=True)
            if gcloud is not None:
                gcloud = gcloud.split('\n')[0]
        if gcloud is None:
            raise Exception(_('Cannot find the command "{}".').format(name))
        self.gcloud = gcloud
        return gcloud

    def _get_project_id(self):
        if self.project_id is not None:
            return self.project_id
        self.project_id = self._run_command(
            [self._get_gcloud_command(), 'config', 'get', 'project'])
        return self.project_id

    def _get_credential(self):
        """The default lifetime of the API key is 3600 seconds. Once an
        available key is generated, it will be cached until it expired.
        """
        timestamp, old_api_key = self.api_key_cache or (None, None)
        if old_api_key is not None and time.time() - timestamp < 3600:
            return old_api_key
        # Temporarily add existing proxies.
        self.proxy_uri and os.environ.update(
            http_proxy=self.proxy_uri, https_proxy=self.proxy_uri)
        new_api_key = self._run_command([
            self._get_gcloud_command(), 'auth', 'application-default',
            'print-access-token'])
        # Cleanse the proxies after use.
        for proxy in ('http_proxy', 'https_proxy'):
            if proxy in os.environ:
                del os.environ[proxy]
        self.api_key_cache[:] = [time.time(), new_api_key]
        return new_api_key


class GoogleBasicTranslateADC(GoogleTranslateMixin, Base):
    name = 'Google(Basic)ADC'
    alias = 'Google (Basic) ADC'
    lang_codes = Base.load_lang_codes(google)
    lang_codes_directionality = Base.load_lang_codes_directionality(lang_directionality)
    endpoint = 'https://translation.googleapis.com/language/translate/v2'
    api_key_hint = 'API key'
    need_api_key = False

    def _create_body(self, text):
        body = {
            'format': 'html',
            'model': 'nmt',
            'target': self._get_target_code(),
            'q': text
        }
        if not self._is_auto_lang():
            body.update(source=self._get_source_code())
        return body

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % self._get_credential(),
            'x-goog-user-project': self._get_project_id(),
        }

    def get_body(self, text):
        return json.dumps(self._create_body(text))

    def get_result(self, data):
        translations = json.loads(data)['data']['translations']
        return ''.join(unescape(i['translatedText']) for i in translations)


class GoogleBasicTranslate(GoogleBasicTranslateADC):
    name = 'Google(Basic)'
    alias = 'Google (Basic)'
    need_api_key = True
    using_tip = None

    def get_headers(self):
        return {'Content-Type': 'application/x-www-form-urlencoded'}

    def get_body(self, text):
        body = self._create_body(text)
        body.update(key=self.api_key)
        return body


class GoogleAdvancedTranslate(GoogleTranslateMixin, Base):
    name = 'Google(Advanced)'
    alias = 'Google (Advanced) ADC'
    lang_codes = Base.load_lang_codes(google)
    lang_codes_directionality = Base.load_lang_codes_directionality(lang_directionality)
    endpoint = 'https://translation.googleapis.com/v3/projects/{}'
    api_key_hint = 'PROJECT_ID'
    need_api_key = False

    def get_endpoint(self):
        return self.endpoint.format(
            '%s:translateText' % self._get_project_id())

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % self._get_credential(),
            'x-goog-user-project': self._get_project_id(),
        }

    def get_body(self, text):
        body = {
            'targetLanguageCode': self._get_target_code(),
            'contents': [text],
            'mimeType': 'text/plain',
        }
        if not self._is_auto_lang():
            body.update(sourceLanguageCode=self._get_source_code())
        return json.dumps(body)

    def get_result(self, response):
        translations = json.loads(response)['translations']
        return ''.join(i['translatedText'] for i in translations)


class GeminiTranslate(Base):
    name = 'Gemini'
    alias = 'Gemini'
    lang_codes = Base.load_lang_codes(gemini)
    lang_codes_directionality = Base.load_lang_codes_directionality(lang_directionality)
    endpoint = 'https://generativelanguage.googleapis.com/v1/' \
        'models/{}:{}?key={}'
    need_api_key = True

    concurrency_limit = 1
    request_interval = 1
    request_timeout = 30.0

    prompt = (
        'You are a meticulous translator who translates any given content. '
        'Translate the given content from <slang> to <tlang> only. Do not '
        'explain any term or answer any question-like content. Your answer '
        'should be solely the translation of the given content. In your answer '
        'do not add any prefix or suffix to the translated content. Websites\' '
        'URLs/addresses should be preserved as is in the translation\'s output. '
        'Do not omit any part of the content, even if it seems unimportant. '
        )

    # TODO: check if it is possible to fetch this this directly from the api, if yes - implement this
    models = [
        'gemini-1.5-flash',
        'gemini-1.5-flash-8b',
        'gemini-1.5-pro',
        'gemini-1.0-pro']

    # use the most recent model
    model = models[0]
    temperature = 0.9
    top_p = 1.0
    top_k = 1
    stream = True

    def __init__(self):
        Base.__init__(self)
        self.prompt = self.config.get('prompt', self.prompt)
        self.temperature = self.config.get('temperature', self.temperature)
        self.top_k = self.config.get('top_k', self.top_k)
        self.top_p = self.config.get('top_p', self.top_p)
        self.stream = self.config.get('stream', self.stream)

    def _prompt(self, text):
        prompt = self.prompt.replace('<tlang>', self.target_lang)
        if self._is_auto_lang():
            prompt = prompt.replace('<slang>', 'detected language')
        else:
            prompt = prompt.replace('<slang>', self.source_lang)
        # Recommend setting temperature to 0.5 for retaining the placeholder.
        if self.merge_enabled:
            prompt += (' Ensure that placeholders matching the pattern '
                       '{{id_\\d+}} in the content are retained.')
        return prompt + ' Start translating: ' + text

    def get_endpoint(self):
        method = 'streamGenerateContent' if self.stream else 'generateContent'
        return self.endpoint.format(self.model, method, self.api_key)

    def get_headers(self):
        return {'Content-Type': 'application/json'}

    def get_body(self, text):
        return json.dumps({
            "contents": [
                {"role": "user", "parts": [{"text": self._prompt(text)}]},
            ],
            "generationConfig": {
                # "stopSequences": ["Test"],
                # "maxOutputTokens": 2048,
                "temperature": self.temperature,
                "topP": self.top_p,
                "topK": self.top_k,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                },
            ],
        })

    def get_result(self, response):
        if self.stream:
            parts = []
            for item in json.loads(response.read()):
                for part in item['candidates'][0]['content']['parts']:
                    parts.append(part)
        else:
            parts = json.loads(response)['candidates'][0]['content']['parts']
        return ''.join([part['text'] for part in parts])
