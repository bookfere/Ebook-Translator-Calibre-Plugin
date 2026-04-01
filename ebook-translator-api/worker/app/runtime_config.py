from dataclasses import dataclass
import hashlib
import json

from .config import Settings, split_csv


@dataclass
class ServiceConfiguration:
    preferences: dict

    def get(self, key, default=None):
        if key is None:
            return default
        cursor = self.preferences
        for item in key.split("."):
            if isinstance(cursor, dict) and item in cursor:
                cursor = cursor[item]
            else:
                return default
        return cursor

    def set(self, key, value):
        cursor = self.preferences
        parts = key.split(".")
        for item in parts[:-1]:
            cursor = cursor.setdefault(item, {})
        cursor[parts[-1]] = value


def map_engine_name(engine: str, settings: Settings) -> str:
    mapping = {
        "openai": settings.openai_engine_name,
        "deepl": settings.deepl_engine_name,
        "google": settings.google_engine_name,
        "deepinfra": settings.deepinfra_engine_name,
    }
    if engine not in mapping:
        raise ValueError(f"Unsupported engine: {engine}")
    return mapping[engine]


def normalize_engine_options(options: dict | str | None) -> dict:
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    return options or {}


def build_cache_identity(job: dict, settings: Settings, input_path: str, encoding: str = "utf-8") -> str:
    options = normalize_engine_options(job.get("engine_options"))
    merge_length = int(options.get("merge_length", 1800)) if bool(options.get("merge_enabled", False)) else 0
    extra_encoding = "" if encoding.lower() == "utf-8" else encoding.lower()
    value = f"{input_path}{map_engine_name(job['engine'], settings)}{job['target_lang']}{merge_length}{extra_encoding}"
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def build_runtime_preferences(
    job: dict,
    settings: Settings,
    cache_enabled: bool = False,
    cache_path: str | None = None,
) -> dict:
    selected_engine = map_engine_name(job["engine"], settings)

    engine_preferences = {
        settings.openai_engine_name: {
            "api_keys": split_csv(settings.openai_api_keys_csv),
            "model": settings.openai_model,
            "stream": True,
        },
        settings.deepl_engine_name: {
            "api_keys": split_csv(settings.deepl_api_keys_csv),
        },
        settings.google_engine_name: {
            "api_keys": split_csv(settings.google_api_keys_csv),
        },
        settings.deepinfra_engine_name: {
            "api_keys": split_csv(settings.deepinfra_api_keys_csv),
            "model": settings.deepinfra_model,
            "endpoint": settings.deepinfra_endpoint,
            "prompt": (
                "You are a meticulous translator who translates any given content. "
                "Translate the given content from <source> to <target> only. "
                "Do not explain any term or answer any question-like content. "
                "Your answer should be solely the translation of the given content. "
                "In your answer do not add any prefix or suffix to the translated content. "
                "Websites' URLs/addresses should be preserved as is in the translation's output. "
                "Do not omit any part of the content, even if it seems unimportant."
            ),
            "temperature": 1.3,
            "top_p": 1.0,
            "stream": False,
        },
    }

    options = normalize_engine_options(job.get("engine_options"))
    selected_options = engine_preferences.setdefault(selected_engine, {})
    selected_options.update(options)

    return {
        "translate_engine": selected_engine,
        "engine_preferences": engine_preferences,
        "proxy_enabled": False,
        "proxy_type": "http",
        "proxy_setting": {},
        "cache_enabled": cache_enabled,
        "cache_path": cache_path,
        "log_translation": True,
        "show_notification": False,
        "translation_position": "below",
        "column_gap": {
            "_type": "percentage",
            "percentage": 10,
            "space_count": 6,
        },
        "original_color": None,
        "translation_color": None,
        "priority_rules": [],
        "rule_mode": "normal",
        "filter_scope": "text",
        "filter_rules": [],
        "ignore_rules": [],
        "reserve_rules": [],
        "custom_engines": {},
        "glossary_enabled": False,
        "glossary_path": None,
        "merge_enabled": bool(options.get("merge_enabled", False)),
        "merge_length": int(options.get("merge_length", 1800)),
        "ebook_metadata": {},
        "search_paths": [],
        "to_library": False,
        "output_path": None,
    }


def install_runtime_config(preferences: dict) -> None:
    from calibre_plugins.ebook_translator.lib import cache as cache_module
    from calibre_plugins.ebook_translator.lib import config as config_module
    from calibre_plugins.ebook_translator.lib import conversion as conversion_module
    from calibre_plugins.ebook_translator.lib import translation as translation_module

    service_config = ServiceConfiguration(preferences)

    def _get_config():
        return service_config

    config_module.get_config = _get_config
    conversion_module.get_config = _get_config
    translation_module.get_config = _get_config
    cache_module.get_config = _get_config
    cache_root = cache_module.custom_cache_path()
    cache_module.TranslationCache.dir_path = cache_root
    cache_module.TranslationCache.cache_path = f"{cache_root}/cache"
    cache_module.TranslationCache.temp_path = f"{cache_root}/temp"
