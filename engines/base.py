import json

from mechanize import Browser, Request
from calibre.utils.localization import lang_as_iso639_1

load_translations()


class Base:
    name = None
    endpoint = None
    support_lang = None
    need_api_key = True
    api_key_hint = _('API Key')
    api_key_validate = r'^.*$'

    def __init__(self, api_key, source_lang, target_lang):
        self.api_key = api_key or ''
        self.source_lang = source_lang
        self.target_lang = target_lang

        self.lang_codes = self.get_support_lang()

        self.br = Browser()
        self.br.set_handle_robots(False)
        self.timeout = 300.0

    @classmethod
    def get_support_lang(cls):
        codes = json.loads(
            get_resources('engines/codes/%s' % cls.support_lang))
        if 'source' not in codes or 'target' not in codes:
            return {'source': codes, 'target': codes}
        return codes

    @classmethod
    def is_chatgpt(cls):
        return cls.name == 'ChatGPT'

    def _get_source_lang_code(self):
        return 'auto' if self.source_lang == _('Auto detect') else \
            self.lang_codes.get('source').get(self.source_lang)

    def _get_target_lang_code(self):
        return self.lang_codes.get('target').get(self.target_lang)

    def _is_auto_lang(self):
        return self._get_source_lang_code() == 'auto'

    def get_target_lang_code(self):
        return lang_as_iso639_1(self._get_target_lang_code())

    def set_proxy(self, proxy=[]):
        if isinstance(proxy, list) and len(proxy) == 2:
            proxy = 'http://%s:%s' % tuple(proxy)
            self.br.set_proxies({'http': proxy, 'https': proxy})

    def request(self, data, method='GET', headers={}):
        request = Request(self.endpoint, data, headers=headers,
                          method=method, timeout=self.timeout)
        return self.br.open(request)

    def _translate(func):
        def wrapper(self, text):
            response = func(self, text)
            data = response.read().decode('utf-8')
            if response.code != 200 or not data:
                raise Exception(_('Translate engine return bad response.'))
            try:
                return self.parse(data)
            except Exception as e:
                raise Exception(
                    _('Can not parse returned response. Raw data: {}')
                    .format(data))
        return wrapper

    def translate(self, text):
        raise NotImplementedError()

    def parse(self, response):
        raise NotImplementedError()

    _translate = staticmethod(_translate)
