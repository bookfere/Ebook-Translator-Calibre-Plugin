import traceback

from mechanize import Browser, Request
from calibre.constants import DEBUG
from calibre.utils.localization import lang_as_iso639_1


load_translations()


class Base:
    name = None
    alias = None
    support_lang = None
    engine_data = {}
    lang_codes = {}
    endpoint = None
    need_api_key = True
    api_key_hint = _('API Key')
    api_key_rule = r'^[^\s]+$'
    placeholder = ('{{{{id_{}}}}}', r'({{\s*)*id\s*_\s*{}\s*(\s*}})*')

    def __init__(self):
        self.api_key = ''
        self.source_lang = None
        self.target_lang = None
        self.proxy_uri = None

        self.br = Browser()
        self.br.set_handle_robots(False)
        self.timeout = 300.0

        self.source_codes = self.lang_codes.get('source')
        self.target_codes = self.lang_codes.get('target')

    @classmethod
    def get_api_key_error(cls):
        return _('A correct key format "{}" is required.') \
            .format(cls.api_key_hint)

    @classmethod
    def set_engine_data(cls, data):
        cls.name = data.get('name')  # rename custom engine
        cls.engine_data = data

    @classmethod
    def set_lang_codes(cls, codes):
        if not ('source' in codes or 'target' in codes):
            codes = {'source': codes, 'target': codes}
        cls.lang_codes = codes

    @classmethod
    def is_chatgpt(cls):
        return cls.__name__ == 'ChatgptTranslate'

    @classmethod
    def is_custom(cls):
        return cls.__name__ == 'CustomTranslate'

    def set_api_key(self, api_key):
        self.api_key = api_key

    def set_source_lang(self, source_lang):
        self.source_lang = source_lang

    def set_target_lang(self, target_lang):
        self.target_lang = target_lang

    def set_proxy(self, proxy=[]):
        if isinstance(proxy, list) and len(proxy) == 2:
            self.proxy_uri = '%s:%s' % tuple(proxy)
            if not self.proxy_uri.startswith('http'):
                self.proxy_uri = 'http://%s' % self.proxy_uri

    def _get_source_code(self):
        return 'auto' if self.source_lang == _('Auto detect') else \
           self.source_codes.get(self.source_lang)

    def _get_target_code(self):
        return self.target_codes.get(self.target_lang)

    def _is_auto_lang(self):
        return self._get_source_code() == 'auto'

    def get_target_code(self):
        return lang_as_iso639_1(self._get_target_code())

    def get_result(self, url, data=None, headers={}, method='GET',
                   stream=False, callback=None, silence=False):
        result = None
        self.proxy_uri and self.br.set_proxies(
            {'http': self.proxy_uri, 'https': self.proxy_uri})
        # Compatible with mechanize 0.3.0 on Calibre 3.21.
        try:
            request = Request(
                url, data, headers=headers, timeout=self.timeout,
                method=method)
        except Exception:
            request = Request(
                url, data, headers=headers, timeout=self.timeout)
        try:
            self.br.open(request)
            response = self.br.response()
            result = response if stream else \
                response.read().decode('utf-8').strip()
            return self.parse(result) if callback is None else callback(result)
        except Exception as e:
            DEBUG and traceback.print_exc()
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
