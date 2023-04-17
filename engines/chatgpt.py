import json

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class ChatgptTranslate(Base):
    name = 'ChatGPT'
    support_lang = 'google.json'
    endpoint = 'https://api.openai.com/v1/chat/completions'

    prompts = {
        'auto': 'Translate the content into {tlang}: {text}',
        'lang': 'Translate the content from {slang} to {tlang}: {text}',
    }

    def set_prompt(self, auto=None, lang=None):
        if auto is not None:
            self.prompts.update(auto=auto)
        if lang is not None:
            self.prompts.update(lang=lang)

    def translate(self, text):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % self.api_key
        }

        if self._is_auto_lang():
            content = self.prompts.get('auto').format(
                tlang=self.target_lang, text=text)
        else:
            content = self.prompts.get('lang').format(
                slang=self.source_lang, tlang=self.target_lang, text=text)

        data = json.dumps({
            'model': 'gpt-3.5-turbo',
            'messages': [{'role': 'user', 'content': content}]
        })

        return self.get_result(self.endpoint, data, headers, method='POST')

    def parse(self, data):
        return json.loads(data)['choices'][0]['message']['content']
