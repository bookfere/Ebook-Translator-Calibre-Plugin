from .google import (
    GoogleFreeTranslate, GoogleBasicTranslate, GoogleBasicTranslateADC,
    GoogleAdvancedTranslate, GeminiPro)
from .openai import ChatgptTranslate
from .anthropic import ClaudeTranslate
from .deepl import DeeplTranslate, DeeplProTranslate, DeeplFreeTranslate
from .youdao import YoudaoTranslate
from .baidu import BaiduTranslate
from .microsoft import MicrosoftEdgeTranslate, AzureChatgptTranslate
from .papago import PapagoTranslate

builtin_engines = (
    GoogleFreeTranslate, GoogleBasicTranslate, GoogleBasicTranslateADC,
    GoogleAdvancedTranslate, ChatgptTranslate, AzureChatgptTranslate,
    GeminiPro, ClaudeTranslate, DeeplTranslate, DeeplProTranslate,
    DeeplFreeTranslate, MicrosoftEdgeTranslate, YoudaoTranslate,
    BaiduTranslate, PapagoTranslate)
