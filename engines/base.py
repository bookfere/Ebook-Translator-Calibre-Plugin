from mechanize import Browser, Request
from calibre.utils.localization import lang_as_iso639_1


load_translations()


class Base:
    name = None
    support_lang = None
    engine_data = {}
    lang_codes = {}
    endpoint = None
    need_api_key = True
    api_key_hint = _('API Key')
    api_key_rule = r'^.*$'
    merge_divider = '{{{{{}}}}}'

    def __init__(self):
        self.api_key = ''
        self.source_lang = None
        self.target_lang = None

        self.br = Browser()
        self.br.set_handle_robots(False)
        self.timeout = 300.0

        self.source_codes = self.lang_codes.get('source')
        self.target_codes = self.lang_codes.get('target')

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
            proxy = 'http://%s:%s' % tuple(proxy)
            self.br.set_proxies({'http': proxy, 'https': proxy})

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
        try:
            self.br.open(Request(url, data, headers=headers, method=method,
                                 timeout=self.timeout))
            response = self.br.response()
            result = response if stream else \
                response.read().decode('utf-8').strip()
            return self.parse(result) if callback is None else callback(result)
        except Exception as e:
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
