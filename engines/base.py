import ssl
import os.path

from mechanize import Browser, Request, HTTPError
from calibre import get_proxies
from calibre.utils.localization import lang_as_iso639_1

from ..lib.utils import traceback_error


load_translations()


class Base:
    name = 'Unknown'
    alias = 'Unknown'
    lang_codes = {}
    config = {}
    endpoint = 'https://example.com'
    need_api_key = True
    api_key_hint = _('API Keys')
    api_key_pattern = r'^[^\s]+$'
    api_key_errors = ['401']
    separator = '\n\n'
    placeholder = ('{{{{id_{}}}}}', r'({{\s*)+id\s*_\s*{}\s*(\s*}})+')
    using_tip = None

    concurrency_limit = 0
    request_interval = 0.0
    request_attempt = 3
    request_timeout = 10.0
    max_error_count = 10

    def __init__(self):
        self.source_lang = None
        self.target_lang = None
        self.proxy_uri = None
        self.search_paths = []

        self.merge_enabled = False

        self.api_keys = self.config.get('api_keys', [])[:]
        self.bad_api_keys = []
        self.api_key = self._get_api_key()

        concurrency_limit = self.config.get('concurrency_limit')
        if concurrency_limit is not None:
            self.concurrency_limit = int(concurrency_limit)
        request_interval = self.config.get('request_interval')
        if request_interval is not None:
            self.request_interval = request_interval
        request_attempt = self.config.get('request_attempt')
        if request_attempt is not None:
            self.request_attempt = int(request_attempt)
        request_timeout = self.config.get('request_timeout')
        if request_timeout is not None:
            self.request_timeout = request_timeout
        max_error_count = self.config.get('max_error_count')
        if max_error_count is not None:
            self.max_error_count = max_error_count

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

    def change_api_key(self):
        """Change the API key if the previous one cannot be used."""
        if self.api_key not in self.bad_api_keys:
            self.bad_api_keys.append(self.api_key)
            self.api_key = self._get_api_key()
            if self.api_key is not None:
                return True
        return False

    def need_change_api_key(self, error_message):
        if self.need_api_key and len(self.api_keys) > 0:
            for error in self.api_key_errors:
                if error in error_message:
                    return True
        return False

    def set_search_paths(self, paths):
        self.search_paths = paths

    def get_external_program(self, name, paths=[]):
        for path in paths + self.search_paths:
            if not path.endswith('%s%s' % (os.path.sep, name)):
                path = os.path.join(path, name)
            if os.path.isfile(path):
                return path
        return None

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

    def get_browser(self):
        br = Browser()
        br.set_handle_robots(False)
        # Do not verify SSL certificates
        br.set_ca_data(
            context=ssl._create_unverified_context(cert_reqs=ssl.CERT_NONE))

        proxies = {}
        if self.proxy_uri is not None:
            proxies.update(http=self.proxy_uri, https=self.proxy_uri)
        else:
            http = get_proxies(False).get('http')
            http and proxies.update(http=http, https=http)
            https = get_proxies(False).get('https')
            https and proxies.update(https=https)
        proxies and br.set_proxies(proxies)

        return br

    def get_result(self, url, data=None, headers={}, method='GET',
                   stream=False, silence=False, callback=None):
        # Compatible with mechanize 0.3.0 on Calibre 3.21.
        try:
            request = Request(
                url, data, headers=headers, timeout=self.request_timeout,
                method=method)
        except Exception:
            request = Request(
                url, data, headers=headers, timeout=self.request_timeout)
        try:
            result = ''
            br = self.get_browser()
            br.open(request)
            response = br.response()
            if not stream:
                response = result = response.read().decode('utf-8').strip()
            return response if callback is None else callback(response)
        except Exception as e:
            if silence:
                return None
            error = [traceback_error()]
            if isinstance(e, HTTPError):
                error.append(e.read().decode('utf-8'))
            elif result:
                error.append(result)
            raise Exception(
                _('Can not parse returned response. Raw data: {}')
                .format('\n\n' + '\n\n'.join(error)))

    def get_usage(self):
        return None

    def translate(self, text):
        raise NotImplementedError()
