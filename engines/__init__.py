from .google import (
    GoogleFreeTranslate, GoogleBasicTranslate, GoogleAdvancedTranslate)
from .chatgpt import ChatgptTranslate, AzureChatgptTranslate
from .deepl import DeeplTranslate, DeeplProTranslate, DeeplFreeTranslate
from .youdao import YoudaoTranslate
from .baidu import BaiduTranslate
from .microsoft import MicrosoftEdgeTranslate


builtin_engines = (
    GoogleFreeTranslate, GoogleBasicTranslate, GoogleAdvancedTranslate,
    ChatgptTranslate, AzureChatgptTranslate, DeeplTranslate, DeeplProTranslate,
    DeeplFreeTranslate, MicrosoftEdgeTranslate, YoudaoTranslate,
    BaiduTranslate)
