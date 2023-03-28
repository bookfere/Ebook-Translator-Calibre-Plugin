import json
import time

from mechanize import Browser, Request


load_translations()


class Base:
    def __init__(self, name, api_key, source_lang, target_lang):
        self.name = name
        self.api_key = api_key or ''
        self.source_lang = source_lang
        self.target_lang = target_lang

        self.timeout = 300.0
        self.lang_codes = json.loads(get_resources('engines/lang.json'))
        self.br = Browser()
        self.br.set_handle_robots(False)

    def set_proxy(self, proxy=[]):
        if isinstance(proxy, list) and len(proxy) == 2:
            proxy = 'http://%s:%s' % tuple(proxy)
            self.br.set_proxies({'http': proxy, 'https': proxy})

    def request(self, data, method='GET', headers={}):
        endpoint = self.get_endpoint()
        request = Request(endpoint, data, headers=headers, method=method,
                          timeout=self.timeout)
        response = self.br.open(request)
        data = response.read().decode()
        if not data:
            raise Exception('Translate engine return bad response.')
        return data

    def _get_lang_code(self, language):
        return 'auto' if language == _('Auto detect') else \
            self.lang_codes.get(language)

    def _is_auto_lang(self):
        return self._get_lang_code(self.source_lang) == 'auto'

    def is_need_sleep(self):
        return False

    def get_name(self):
        return self.name

    def get_endpoint(self):
        raise NotImplementedError()

    def translate(self, text):
        raise NotImplementedError()
