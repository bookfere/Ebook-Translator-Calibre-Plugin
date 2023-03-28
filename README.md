# Ebook Translator (A Calibre plugin)

A Calibre plugin to translate ebook into a specified language (the translated text will be added after original text).

---

## Features

* Support languages supported by the selected translation engine (e.g. Google Translate supports 134 languages)
* Support multiple translation engines, including Google Translate, ChatGPT, and DeepL
* Support all ebook formats supported by Calibre (48 input formats, 20 output formats)
* Support to translate more than one ebooks, the translation process of each book is carried out simultaneously without affecting one another
* Support caching translated content, no need to re-translate after request failure or network interruption
* Provide a large number of customization settings, such as saving translated ebooks to Calibre library or designated location

---

## Settings

__[Output Path]__

* Library [default]: After the ebook is translated, it will be placed in Calibre library
* Path: After the ebook is translated, it will be stored in specified directory

When translating an ebook, you need to pay attention to the selected output format. If the selected output format is an existing format in Calibre library, the original input format file will be backed up by renaming. Therefore, it is not recommended to select the same output format as the input format. If you really need to use the same format for output, it is recommended to specify the path to store.

__[Translation Engine]__

* Google [default]: Free translation engine
* ChatGPT: API key required
* DeepL: API key required
* DeepL(Pro): API key required

Except for Google, who does not require an API key, other translation engines require you to register a corresponding account and pay to obtain an API key.

According to the response information sample provided by DeepL official website, the program can run properly, but due to the lack of DeepL's API key, the actual operation status is unknown.

If you choose to use a translation engine that requires payment, it is recommended to go to its official documentation to check the pricing rules. For example, ChatGPT uses its official tool [Tokenizer](https://platform.openai.com/tokenizer) to estimate how many tokens will be consumed to translate the amount of words in order to estimate the cost.

__[Network Proxy]__

* Enable [default unchecked]: Enable network proxy
* Host: Support IP and domain name
* Port: Range 0-65536
* Test: Test the connectivity of proxy

__[Cache]__

* Enable [default checked]: Enable to cache translated content
* Clear: Delete all caches

Enabling the caching function can avoid re-translation of translated content after request failure or network interruption. You can also check the amount of disk space occupied by the cache here, and click [Clear] button to delete all caches. Note that if a translation job is currently in progress, the [Clear] button will be disabled to use.

__[Request]__

* Attempt Times [default 3]: The number of times to attempt if the request to translation engine fails
* Maximum Interval [default 5 seconds]: The maximum time interval to request translation engine

A single request to translation engine can last up to 300 seconds. After the timeout, it will retry according to the specified attempt times, and the waiting time for each retry will be gradually increased. The request interval will be a random number between 0 and the specified maximum interval.

When using Google Translate API, which is currently available for free, it is recommended to increase the "Maximum Interval" to an appropriate value (more than 5 seconds is recommended) to prevent it from being flagged as abusive behavior by Google, which could lead to translation interruptions or denial of service. For paid translation engines, the "Maximum Interval" can be set to 0.

__[Log]__

* Display translation [Default checked]: The translation content will be displayed in real time from the respective log window of the translation job

---

## License

[GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html)

---

* GitHub: [https://github.com/bookfere/Ebook-Translator-Calibre-Plugin](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin)
* Release: [https://bookfere.com/post/1057.html](https://bookfere.com/post/1057.html)
* Donate: [https://bookfere.com/donate](https://bookfere.com/donate)
