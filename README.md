__English__ · [简体中文](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/blob/master/README.zh-CN.md) · [正體中文](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/blob/master/README.zh-TW.md)

---

# Ebook Translator (A Calibre plugin)

![Ebook Translator Calibre Plugin](images/logo.png)

A Calibre plugin to translate ebook into a specified language (optionally keeping the original content).

![Translation illustration](images/sample-en.png)

---

## Features

* Support languages supported by the selected translation engine (e.g. Google Translate supports 134 languages)
* Support multiple translation engines, including Google Translate, ChatGPT, and DeepL
* Support for custom translation engines (you can configure to parse response in JSON or XML format)
* Support all ebook formats supported by Calibre (48 input formats, 20 output formats)
* Support to translate more than one ebooks. The translation process of each book is carried out simultaneously without affecting one another
* Support caching translated content, with no need to re-translate after request failure or network interruption
* Provide a large number of customization settings, such as saving translated ebooks to Calibre library or designated location

---

## Installation

Please make sure __[Calibre](https://calibre-ebook.com/)__ is installed on your OS, and install the plugin via either ways below:

__[ Install from Calibre ]__

1. Click Calibre Menu __[Preference... → Plug-ins → Get new plugins]__.
2. Select Ebook Translator from the plugin list, and click __[Install]__.
3. Reboot Calibre.

__[ Load from file ]__

1. Download the plugin zip file from __[releases page](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/releases)__.
2. Click Calibre Menu __[Preference... → Plug-ins → Load plug-in from file]__, and choose the zip file you downloaded.
3. Reboot Calibre.

If you want to install the latest plugin, run the following commands to download the latest plugin file from GitHub repository:

<pre><code>git clone https://github.com/bookfere/Ebook-Translator-Calibre-Plugin.git
cd Ebook-Translator-Calibre-Plugin
git archive --format zip --output ../Ebook-Translator-Calibre-Plugin.zip master</code></pre>

If the "Translate Book" plugin is not showing up on Calibre menu, you need to add it from __[Preference... → Toolbars & menus]__, choose __[The main toolbar]__, find the plugin and click __[>]__, and __[Apply]__.

---

## Usage

1. Select the ebook(s), and click the plugin icon "Translate Book".
2. Select the Target Language (and Output Format if needed).
3. Click __[TRANSLATE]__ button.

After that, you can check the translation process by clicking "Jobs" at the bottom right. Double clicking the job item, you can check the real-time translation log from the window it prompts.

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

You can click the __[Select]__ button to select a color from color palette, or enter the color value manually. Please refer to "__[color value](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value)__" on MDN documentation for details. If left blank no customized color will be applied.

__[ Merge to Translate ]__

* __Enable__ [default unchecked]: Enable to merge to translate

You can specify the number of characters to translate at one time, default value is 2000.

__[ Translation Glossary ]__

* __Enable__ [default unchecked]: Enable to use the selected translation glossary file

A translation glossary serves to define precise translations for particular terms and to direct the translation engine to exclude specific terms from translation.

The glossary file is a plain text file with extension .txt. It has the following format: if a term requires a specific translation, it is presented as a pair of two lines, the first one with the original term and the second one with its translation; If a term needs to be ignored in translation, it is presented as a single line per term. The groups of terms are separated by a blank line.

<pre>La Torre Eiffel
The Eiffel Tower

La Estatua de la Libertad</pre>

__[ Do not Translate ]__

* __Normal__ [default]: Exclude paragraph by keyword (one keyword per line)
* __Normal(case-sensitive)__: Exclude paragraph by case-sensitive keyword (one keyword per line)
* __Regular Expression__: Exclude paragraph by Regular Expression rule (one rule per line)

For regular expression syntax, please refer to "__[Regular Expression Syntax](https://docs.python.org/3/library/re.html#regular-expression-syntax)__" on Python documentation.

### Setting

__[ Output Path ]__

* __Library__ [default]: After the ebook is translated, it will be placed in Calibre library
* __Path__: After the ebook is translated, it will be stored in specified directory

__[ Translation Engine ]__

* __Google (Free)__ [default]: Free translation engine
* __Google (Basic)__: API key or JSON key file required ([obtain](https://console.cloud.google.com/apis/credentials))
* __Google (Advanced)__: Project ID and JSON key file required ([obtain](https://console.cloud.google.com/apis/credentials))
* __ChatGPT__: API key required ([obtain](https://platform.openai.com/account/api-keys))
* __DeepL__: API key required ([obtain](https://www.deepl.com/pro?cta=header-pro-button/))
* __DeepL (Pro)__: API key required ([obtain](https://www.deepl.com/pro?cta=header-pro-button/))
* __DeepL (Free)__: Free translation engine (unstable)
* __Youdao__: APP key and secret required ([obtain](https://ai.youdao.com/console/#/app-overview/create-application))
* __Baidu__: APP id and key required ([obtain](https://api.fanyi.baidu.com/register))
* __[Custom]__: Customize your own translation engine

Except for Google(Free) and DeepL(Free), who does not require an API key, other built-in translation engines require you to register a corresponding account and pay to obtain an API key.

If you intend to use a JSON key file with the Google translation engine, you will also need to install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install-sdk) on your operating system and ensure that the `gcloud` command is working properly.

If you opt for a paid translation engine, we recommend you to refer to its official documentation for pricing rules. For example, ChatGPT uses its official tool, __[Tokenizer](https://platform.openai.com/tokenizer)__, to estimate the number of tokens required to translate a given amount of text in order to provide a cost estimate.

You can click the __[Test]__ button to test the selected translation engine. If translation engine provides quota information, it will be displayed at the bottom of Test Translation Engine window.

Click the __[Custom]__ button, you will enter the "Custom Translation Engine" interface, where you can add, delete and configure a translation engine.

The data to configure a custom translation engine is in JSON format. Each time you add a new custom translation engine, a data template, as shown below, will be displayed for your reference:

<pre><code>{
    "name": "New Engine - 36e05",
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
            "source": "&lt;source&gt;",
            "target": "&lt;target&gt;",
            "text": "&lt;text&gt;"
        }
    },
    "response": "response"
}</code></pre>

The above data template contains 4 name/value pairs, which will be explained as below. You can update the template as needed.

* `name`: The name of the translation engine displayed on the UI, for example, Bing.
* `languages`: The language codes supported by the translation engine. The format is `{'Language Name': 'language code'}`. Please refer to the documentation of the translation engine API for details. You can also specify the source language and target language respectively.
    * `source`: The source language. The format is the same as for languages.
    * `target`: The target language. The format is the same as for languages.
* `request`: Request data, including the following name/value pairs:
    * `url`: The API URL, as specified in the documentation of the translation engine API.
    * `method`: The request method (optional), with a default value of `GET`.
    * `headers`: The request header (optional). You can refer to the documentation of the translation engine API for details.
* `data`: Request data, can be either a `dict` object which will be encoded and sent as application/`x-www-form-urlencoded` data or a string which will be sent as is. If you use a string you should also set the `Content-Type` header appropriately. It includes 3 built-in variables: `<source>`, `<target>`, and `<text>`. `<source>` and `<target>` correspond to the language codes set earlier, and can be ignored if not needed; `<text>` refers to the original text sent to the translation engine, which must be included to save. Please refer to the documentation of the translation engine API for details.
* `response`: The expression used to parse the response data to obtain the translation text. The response data is included in the `response` variable, which is a __[JSON](https://docs.python.org/3/library/json.html#encoders*and*decoders)__ object (if the response from the translation engine is in JSON format) or an __[Element](https://lxml.de/apidoc/lxml.etree.html#lxml.etree.ElementBase)__ object of lxml (if the response from the translation engine is in XML format).

Once you have completed the data for the custom translation engine, you can click the __[Verify]__ button to check whether the data format is valid, and click the __[Save]__ button to save all the changes.

__[ ChatGPT Prompt ]__

* __For auto detecting source language__: Customize ChatGPT prompt to translate from 'Auto detect' source language
* __For specifying source language__: Customize ChatGPT prompt to translate from specified source language

__[ Preferred Language ]__

* __Target Language__ [default UI language]：Set the preferred target language.

__[ Network Proxy ]__

* __Enable__ [default unchecked]: Enable network proxy
* __Host__: IP or domain name
* __Port__: Range 0-65536
* __Test__: Test the connectivity of proxy

__[ Cache ]__

* __Enable__ [default checked]: Enable to cache translated content
* __Clear__: Delete all caches

Enabling the caching function can avoid re-translation of the translated content after request failure or network interruption. You can also check the amount of disk space occupied by the cache here, and click __[Clear]__ button to delete all caches. Note that if a translation job is currently in progress, the __[Clear]__ button will be disabled to use.

__[ Request ]__

* __Attempt Times__ [default 3]: The number of times to attempt if failed to request translation engine
* __Maximum Interval__ [default 5 seconds]: The maximum time interval to request translation engine

A single request to translation engine can last up to 300 seconds. After the timeout, it will retry according to the specified attempt times, and the waiting time for each retry will be gradually increased. The request interval will be a random number between 1 and the maximum interval specified.

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
