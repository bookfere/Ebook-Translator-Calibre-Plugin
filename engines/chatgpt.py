import json

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class ChatgptTranslate(Base):
    def get_endpoint(self):
        return 'https://api.openai.com/v1/chat/completions'

    def translate(self, text):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % self.api_key
        }

        content = 'Translate the content from {} to {}: {}'.format(
                  self.source_lang, self.target_lang, text)
        if self._is_auto_lang():
            content = 'Translate the content into {}: {}'.format(
                      self.target_lang, text)

        data = json.dumps({
            'model': 'gpt-3.5-turbo',
            'messages': [{
                'role': 'user',
                'content': content
            }]
        })

        response = self.request(data, method='POST', headers=headers)
        return json.loads(response)['choices'][0]['message']['content']
