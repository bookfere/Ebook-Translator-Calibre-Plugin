# Ebook Translator (A Calibre plugin)

A Calibre plugin to translate ebook into a specified language (optionally keeping the original content).

---

## Features

* Support languages supported by the selected translation engine (e.g. Google Translate supports 134 languages)
* Support multiple translation engines, including Google Translate, ChatGPT, and DeepL
* Support all ebook formats supported by Calibre (48 input formats, 20 output formats)
* Support to translate more than one ebooks. The translation process of each book is carried out simultaneously without affecting one another
* Support caching translated content, with no need to re-translate after request failure or network interruption
* Provide a large number of customization settings, such as saving translated ebooks to Calibre library or designated location

---

## Settings

You can customize the plugin through "Content" and "Setting" panels.

### Content

__[ Translation Position ]__

* __Add after original__ [default]: Add the translation text after original text
* __Add before original__: Add the translation text before original text
* __Add without original__: Add the translation text and delete original text

__[ Translation Color ]__

* __Color Value__: CSS color value, e.g., #666666, grey, rgb(80, 80, 80)

You can click the [Select] button to select a color from color palette, or enter the color value manually. Please refer to "[color value](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value)" on MDN documentation for details. If left blank no customized color will be used.

__[ Do not Translate ]__

* __Normal__ [default]: Exclude content by keyword (one keyword per line)
* __Normal(case-sensitive)__: Exclude content by case-sensitive keyword (one keyword per line)
* __Regular Expression__: Exclude content by Regular Expression rule (one rule per line)

For regular expression syntax, please refer to "[Regular Expression Syntax](https://docs.python.org/3/library/re.html#regular-expression-syntax)" on Python documentation.

### Setting

__[ Output Path ]__

* __Library__ [default]: After the ebook is translated, it will be placed in Calibre library
* __Path__: After the ebook is translated, it will be stored in specified directory

__[ Translation Engine ]__

* __Google__ [default]: Free translation engine
* __ChatGPT__: API key required
* __DeepL__: API key required
* __DeepL(Pro)__: API key required

Except for Google, who does not require an API key, other translation engines require you to register a corresponding account and pay to obtain an API key.

According to the response information sample provided by DeepL official website, the program can run properly, but due to the lack of DeepL's API key, the actual operation status is unknown.

If you opt for a paid translation engine, we recommend you to refer to its official documentation for pricing rules. For example, ChatGPT uses its official tool, [Tokenizer](https://platform.openai.com/tokenizer), to estimate the number of tokens required to translate a given amount of text in order to provide a cost estimate.

__[ ChatGPT Prompt ]__

* __For auto detecting source language__: Customize ChatGPT prompt to translate from 'Auto detect' source language
* __For specifying source language__: Customize ChatGPT prompt to translate from specified source language

__[ Network Proxy ]__

* __Enable__ [default unchecked]: Enable network proxy
* __Host__: Support IP and domain name
* __Port__: Range 0-65536
* __Test__: Test the connectivity of proxy

__[ Cache ]__

* __Enable__ [default checked]: Enable to cache translated content
* __Clear__: Delete all caches

Enabling the caching function can avoid re-translation of translated content after request failure or network interruption. You can also check the amount of disk space occupied by the cache here, and click [Clear] button to delete all caches. Note that if a translation job is currently in progress, the [Clear] button will be disabled to use.

__[ Request ]__

* __Attempt Times__ [default 3]: The number of times to attempt if failed to request translation engine
* __Maximum Interval__ [default 5 seconds]: The maximum time interval to request translation engine

A single request to translation engine can last up to 300 seconds. After the timeout, it will retry according to the specified attempt times, and the waiting time for each retry will be gradually increased. The request interval will be a random number between 1 and the specified maximum interval.

When using Google Translate API, which is currently available for free, we recommend you to increase the "Maximum Interval" to an appropriate value (more than 5 seconds is recommended) to prevent it from being flagged as abusive behavior, which could lead to translation interruptions or denial of service. For paid translation engines, the "Maximum Interval" can be set to 1.

__[ Log ]__

* __Display translation__ [Default checked]: The translation content will be displayed in real time from the respective log window of the translation job

---

## License

[GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html)

---

* GitHub: [https://github.com/bookfere/Ebook-Translator-Calibre-Plugin](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin)
* MobileRead: [https://www.mobileread.com/forums/showthread.php?t=353052](https://www.mobileread.com/forums/showthread.php?t=353052)
* Release: [https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/releases](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/releases)
* Donate: [https://www.paypal.com/paypalme/bookfere](https://www.paypal.com/paypalme/bookfere)
