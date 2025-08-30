import json
from typing import Any

from lxml import etree

from calibre.utils.localization import _  # type: ignore

from ..lib.utils import is_str

from . import builtin_engines
from .base import Base


load_translations()  # type: ignore


def create_engine_template(name):
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
    if name.lower() in [
            engine.name.lower() for engine in builtin_engines
            if engine.name is not None]:
        return (False, _(
            'Engine name must be different from builtin engine name.'))
    # language codes
    languages = json_data.get('languages')
    if not languages:
        return (False, _('Language codes are required.'))
    has_source = 'source' in languages
    has_target = 'target' in languages
    if (has_source and not has_target) or (has_target and not has_source):
        return (False, _('Source and target must be added in pair.'))
    # request info
    request = json_data.get('request')
    if not request:
        return (False, _('Request information is required.'))
    if 'url' not in request:
        return (False, _('API URL is required.'))
    # request data
    data = request.get('data')
    if data is not None and '<text>' not in str(data):
        return (False, _('Placeholder <text> is required.'))
    # request headers
    headers = request.get('headers') or {}
    if headers and not isinstance(headers, dict):
        return (False, _('Request headers must be an JSON object.'))
    has_content_type = 'content-type' in [i.lower() for i in headers]
    if is_str(data) and not has_content_type:
        return (False, _('A appropriate Content-Type in headers is required.'))
    # response parser
    response = json_data.get('response')
    if not response or 'response' not in response:
        return (False, _('Expression to parse response is required.'))

    return (True, json_data)


class CustomTranslate(Base):
    name = 'Custom'
    alias = 'Custom'

    need_api_key = False

    engine_data: dict[str, Any]
    request: dict[str, Any]
    response: str

    @classmethod
    def set_engine_data(cls, data):
        cls.name = data.get('name')  # rename custom engine
        cls.request = data.get('request')
        cls.response = data.get('response')
        cls.lang_codes = cls.load_lang_codes(data.get('languages'))

    def __init__(self):
        super().__init__()
        self.endpoint = self.request.get('url') or ''
        self.method = self.request.get('method') or 'GET'

    def get_headers(self):
        return self.request.get('headers') or {}

    def get_body(self, text):
        body = self.request.get('data')
        need_restore = isinstance(body, dict)
        body = json.dumps(body)
        # The replacement may include UTF-8 characters that need to be encoded
        # to ensure pure Latin-1 (compliance with ISO-8859-1).
        body = body.replace('<source>', self._get_source_code()) \
            .replace('<target>', self._get_target_code()) \
            .replace('<text>', json.dumps(text)[1:-1]).encode('utf-8')
        headers = self.get_headers()
        is_json = headers and 'application/json' in headers.values()
        if need_restore and not is_json:
            return json.loads(body)
        return body

    def get_result(self, response):
        try:
            response = json.loads(response)
        except Exception:
            try:
                response = etree.fromstring(response)
            except Exception:
                return response
        result = eval(self.response, {"response": response})
        if not is_str(result):
            raise Exception(_('Response was parsed incorrectly.'))
        return result
