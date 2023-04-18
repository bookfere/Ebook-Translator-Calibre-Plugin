import json
from lxml import etree

from calibre_plugins.ebook_translator.utils import _z, is_str
from calibre_plugins.ebook_translator.engines import builtin_engines
from calibre_plugins.ebook_translator.engines.base import Base

load_translations()


def get_engine_template(name):
    return """{
    "name": "%s",
    "languages": {
        "source": {
            "Source Language": "code"
        },
        "target": {
            "Target Language": "code"
        }
    },
    "request": {
        "url": "https://example.api",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json"
        },
        "data": {
            "source": "<source>",
            "target": "<target>",
            "text": "<text>"
        }
    },
    "response": "response"
}""" % name


def load_engine_data(text):
    # json format
    try:
        json_data = json.loads(text)
    except Exception:
        return (False, _('Engine data must be in valid JSON format.'))
    # validate data
    if not isinstance(json_data, dict):
        return (False, _('Invalid engine data.'))
    # engine name
    name = json_data.get('name')
    if not name:
        return (False, _('Engine name is required.'))
    if name.lower() in [engine.name.lower() for engine in builtin_engines]:
        return (False, _(
            'Engine name must be different from builtin engine name.'))
    # language codes
    languages = json_data.get('languages')
    if not languages:
        return (False, _('Language codes are required.'))
    elif not ('source' in languages and 'target' in languages):
        return (False, _('Source and target must be added in pair.'))
    # request info
    request = json_data.get('request')
    if not request:
        return (False, _('Request information is required.'))
    if 'url' not in request:
        return (False, _('API URL is required.'))
    # request data
    headers = request.get('headers')
    data = request.get('data')
    if isinstance(data, dict):
        if '<text>' not in data.values():
            return (False, _('Placeholder <text> is required.'))
        if headers and 'application/json' in headers.values():
            json_data.update(data=json.dumps(data))
    elif is_str(data):
        if '<text>' not in data:
            return (False, _('Placeholder <text> is required.'))
        if not headers or 'content-type' not in [i.lower() for i in headers]:
            return (False, _(
                'A appropriate Content-Type in headers is required.'))
    # response parser
    response = json_data.get('response')
    if not response or 'response' not in response:
        return (False, _('Expression to parse response is required.'))

    return (True, json_data)


class CustomTranslate(Base):
    name = _z('Custom')
    need_api_key = False

    def translate(self, text):
        request = self.engine_data.get('request')

        endpoint = request.get('url')
        method = request.get('method') or 'GET'
        headers = request.get('headers') or {}

        data = request.get('data')
        if isinstance(data, dict):
            for k, v in request.get('data').items():
                if v == '<source>':
                    data[k] = self._get_source_code()
                elif v == '<target>':
                    data[k] = self._get_target_code()
                elif v == '<text>':
                    data[k] = text
                else:
                    data[k] = v
        elif is_str(data):
            data.replace('<source>', self._get_source_code()) \
                .repalce('<target>', self._get_target_code()) \
                .replace('<text>', text)

        def parse(response):
            try:
                response = json.loads(response)
            except Exception:
                response = etree.fromstring(response)
            result = eval(
                self.engine_data.get('response'), {"response": response})
            if is_str(result):
                raise Exception(_('Response was parsed incorrectly.'))
            return result

        return self.get_result(
            endpoint, data, headers, method=method, callback=parse)
