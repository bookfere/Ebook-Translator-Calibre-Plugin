import traceback

from mechanize import Browser, Request
from calibre.constants import DEBUG
from calibre.utils.localization import lang_as_iso639_1

from ..utils import is_test


load_translations()


class Base:
    name = None
    alias = None
    lang_codes = {}
    config = {}
    endpoint = None
    need_api_key = True
    api_key_hint = _('API Keys')
    api_key_pattern = r'^[^\s]+$'
    api_key_errors = ['401']
    placeholder = ('{{{{id_{}}}}}', r'({{\s*)+id\s*_\s*{}\s*(\s*}})+')

    concurrency_limit = 0
    request_interval = 0
    request_attempt = 3
    request_timeout = 10.0

    def __init__(self):
        self.source_lang = None
        self.target_lang = None
        self.proxy_uri = None

        self.br = Browser()
        self.br.set_handle_robots(False)

        self.merge_enabled = False

        self.api_keys = self.config.get('api_keys', [])[:]
        self.bad_api_keys = []
        self.api_key = self._get_api_key()

    @classmethod
    def load_lang_codes(cls, codes):
        if not ('source' in codes or 'target' in codes):
            codes = {'source': codes, 'target': codes}
        return codes

    @classmethod
    def get_source_code(cls, lang):
        source_codes = cls.lang_codes.get('source')
        return 'auto' if lang == _('Auto detect') else source_codes.get(lang)

    @classmethod
    def get_target_code(cls, lang):
        target_codes = cls.lang_codes.get('target')
        return target_codes.get(lang)

    @classmethod
    def get_iso639_target_code(cls, lang):
        return lang_as_iso639_1(cls.get_target_code(lang))

    @classmethod
    def set_config(cls, config):
        cls.config = config

    @classmethod
    def api_key_error_message(cls):
        return _('A correct key format "{}" is required.') \
            .format(cls.api_key_hint)

    @classmethod
    def is_chatgpt(cls):
        return 'chatgpt' in cls.__name__.lower()

    @classmethod
    def is_custom(cls):
        return cls.__name__ == 'CustomTranslate'

    def change_api_key(self):
        """Change the API key if the previous one cannot be used."""
        if self.api_key not in self.bad_api_keys:
            self.bad_api_keys.append(self.api_key)
            self.api_key = self._get_api_key()
            if self.api_key is not None:
                return True
        return False

    def need_change_api_key(self, error_message):
        if self.need_api_key and len(self.api_keys) > 1:
            for error in self.api_key_errors:
                if error in error_message:
                    return True
        return False

    def set_endpoint(self, endpoint):
        self.endpoint = endpoint

    def set_merge_enabled(self, enable):
        self.merge_enabled = enable

    def set_source_lang(self, source_lang):
        self.source_lang = source_lang

    def set_target_lang(self, target_lang):
        self.target_lang = target_lang

    def get_target_lang(self):
        return self.target_lang

    def set_proxy(self, proxy=[]):
        if isinstance(proxy, list) and len(proxy) == 2:
            self.proxy_uri = '%s:%s' % tuple(proxy)
            if not self.proxy_uri.startswith('http'):
                self.proxy_uri = 'http://%s' % self.proxy_uri

    def set_concurrency_limit(self, limit):
        self.concurrency_limit = limit

    def set_request_attempt(self, limit):
        self.request_attempt = limit

    def set_request_interval(self, seconds):
        self.request_interval = seconds

    def set_request_timeout(self, seconds):
        self.request_timeout = seconds

    def _get_source_code(self):
        return self.get_source_code(self.source_lang)

    def _get_target_code(self):
        return self.get_target_code(self.target_lang)

    def _is_auto_lang(self):
        return self._get_source_code() == 'auto'

    def _get_api_key(self):
        if self.need_api_key and self.api_keys:
            return self.api_keys.pop(0)
        return None

    def get_result(self, url, data=None, headers={}, method='GET',
                   stream=False, silence=False, callback=None):
        result = None
        self.proxy_uri and self.br.set_proxies(
            {'http': self.proxy_uri, 'https': self.proxy_uri})
        # Compatible with mechanize 0.3.0 on Calibre 3.21.
        try:
            request = Request(
                url, data, headers=headers, timeout=self.request_timeout,
                method=method)
        except Exception:
            request = Request(
                url, data, headers=headers, timeout=self.request_timeout)
        try:
            self.br.open(request)
            response = self.br.response()
            result = response if stream else \
                response.read().decode('utf-8').strip()
            return callback(result) if callback else self.parse(result)
        except Exception as e:
            # Only show the trackback when debugging is enabled.
            if not is_test and DEBUG:
                traceback.print_exc()
            if silence:
                return None
            raw_data = str(e) if result is None else result + ' ' + str(e)
            raise Exception(
                _('Can not parse returned response. Raw data: {}')
                .format(raw_data))

    def get_usage(self):
        return None

    def translate(self, text):
        raise NotImplementedError()

    def parse(self, data):
        raise NotImplementedError()
