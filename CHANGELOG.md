## v2.1.4

Fixed bugs and added feature:

1. Fixed the bug that caused malformed requests due to language variants.
2. Fixed the bug that caused unexpected termination of the translation process.
3. Added the cache status indicator for the advanced mode.

---

## v2.1.3

Fixed bugs as follows:

1. Fixed BOM-caused glossary's first word bug. #67
2. Fixed a bug that prevented cache removal and deletion. #90
3. Fixed a bug that prevented the proper storage of translated ebooks. #106
4. Fixed an asyncio-related bug that was crashing the translation process. #110
5. Removed special characters from translation. #112
6. Fixed the bug where the queue couldn't get the event loop. #115
7. Fixed the bug where settings could not be displayed properly. #116
8. Speed up cache storage on windows.

---

## v2.1.2

Enhanced features and fixed bugs:

1. Terminate translation if error occurs in batch mode.
2. Keep hyperlinks when choosing translation position as "Add without original."
3. Fixed a cache-related bug that caused the plugin to crash.
4. Fixed a bug that prevented the restoration of words in the glossary.

---

## v2.1.1

1. Fixed the bug that caused the saving of setting to not work.

---

## v2.1.0

Added/enhanced features and fixed bugs as follows:

1. Optimized concurrency to speed up the translation process.
2. Added the concurrency feature for lower versions of Calibre.
3. Added Cache Manager for cache management (moving/deleting cache).
4. Optimized the glossary feature to be compatible with multiple platforms.
5. Fixed the bug that was unable to parse DeepL responses.
6. Other bug fixing and feature enhancement. 969659e...deac58c

---

## v2.0.3

Fixed bugs and improved features as follows:

1. Changed the setting of HTTP Request from general to engine-specific.
2. Modified the Request Interval from a random value to a fixed value.
3. Fixed the bug that was unable to disable translation logging.
4. Fixed the bug that special characters in ebook titles caused an output error.
5. Fixed the bug in the restoration of the default endpoint for ChatGPT.
6. Fixed the bug that caused conversion interrupts due to invalid escapes.
7. Fixed the bug that caused subsequent jobs to fail after a failed job.
8. Changed the model names for Azure ChatGPT.

---

## v2.0.2

Fixed bugs, improved, and added features as follows:

1. Added Microsoft Edge Translator to built-in engines. PR by @wanghaosjtu
2. Added support to set Target Language and subjects for ebook metadata.
3. Optimized the performance of filtering elements.
4. Fixed the bug that cannot save custom engine data properly.
5. Removed ignored paragraphs during merge translation.

---


## v2.0.1

Optimized features and fixed bugs as follows:

1. Fixed the bug that could not split the translation by ID properly.
2. Fixed the bug that could not handle incomplete read of the stream response.
3. Fixed the bug where the auto-switch API Keys feature did not work properly.
4. Fixed the bug where the original was not removed when turned on "translation only".
5. Fixed the bug that could not remove the Ruby Fallback Parenthesis element.
6. Fixed the bug where translation engines were breaking the glossary markup.
7. Fixed the bug that could not filter out empty content.
8. Optimized the cache and glossary features.

---

## v2.0.0

Added/improved features and fixed bugs:

1. Added "Advanced Mode" for translation fine-grain control. resolved #18, resolved #24
2. Added more options such as endpoint/sampling/model to ChatGPT. resolved #34, resolved #46
3. Supported multiple API keys for all built-in translation engines. resolved #37
4. Added "Ignore Element" feature for excluding unneeded elements. resolved #41
5. Enhanced cache feature to include more information for reviewing. resolved #42
6. Added preferred input/output formats and preferred source language options. resolved #44
7. Added Azure ChatGPT to built-in translation engines. resolved #49
8. Added "Preferred Mode" for clicking icon button in general settings.
9. Added "Timeout" option to "HTTP Request" setting.
10. Optimized ChatGPT prompt for more accurate translating.
11. Fixed the bug that cannot filter paragraphs properly. fixed #41, fixed #45
12. Optimized user experiences, improved features and fix bugs.

---

## v1.3.8

Fixed the following bugs:

1. Fixed the bug that prevented the storage of "Ignore Paragraph" rules.
2. Fixed the bug that caused paragraph translations to be skipped or ignored.
3. Fixed the bug that caused translation interruptions while handling certain content. fixed #40

---

## v1.3.7

Added and improved features as follows:

1. Supported concurrent requests (only for Calibre 5.0 or higher).
2. Added filter scope options to the "Ignore Paragraph" feature.
3. Supported to ignore the translation of pre/code elements.

---

## v1.3.6

Improved functionality and fixed bugs:

1. Removed the old approach for extracting elements to avoid missing translate.
2. Limited the length of filenames to 200 characters to prevent storage errors.
3. Fixed bug when updating plugin to latest version from lower version.
4. Made the plugin compatible with lower versions of Calibre.

---

## v1.3.5

Improved functionality and added test suites:

1. "Merge to Translate" was allowed in the custom translation engine.
2. Optimized "Merge to Translate" for ChatGPT and the custom translator.
3. Added some test cases for key functionality like elements extraction.

---

## v1.3.4

1. Fixed the bug that ChatGPT couldn't retain marks on "Merge to Translate".

---

## v1.3.3

Added features and fixed bug as follows:

1. Added new translation engines: Google (Basic), Google (Advanced).
2. Changed request method to GET for Google (Free) due to "Too Many Requests" error.
3. Added retry timestamp in translation log.

---

## v1.3.2

Fixed the following bugs:

1. Bug that affected plugin usability when handling images.
2. Bug that caused the engine setting to display an incorrect name.
3. Bug that prevented inputting URI scheme into the proxy host.

---

## v1.3.1

1. Remove the restriction on inputting key for Baidu.

---

## v1.3.0

Added the following new features and enhanced functionality:

1. Added "Merge to Translate (Beta)" feature.
2. Supported to set preferred target language.
3. Supported to use glossary file to define precise translation.
4. Added public version of DeepL translation engine.
5. Added server-sent events support for ChatGPT.

---

## v1.2.2

1. Optimized the feature of custom translation engine.

---

## v1.2.1

1. Fixed the bug that caused DeepL to not work properly. fixed #16

---

## v1.2.0

Added the following features:

1. Added custom translation engine feature. resolved #6, resolved #13
2. Added translation engine testing feature.
3. Added the display of usage information for some translation engine. resolved #8

---

## 1.1.0

Added/improved features and fixed bugs:

1. Supported to customize translation text position and delete original content. resolved #7
2. Supported to exclude original content by keyword and regular expression. resolved #2
3. Added Baidu and Youdao translation engines. resolved #3
4. Changed to save translated ebooks as a new book in Calibre library.
5. Supported to customize the color of translation text.
6. Supported to customize ChatGPT prompt word. resolved #4
7. Ignored to translate phonetic symbols (e.g. Japanese). fixed #3
8. Added Spanish as supported interface language. resolved #5
9. Added diagnosis information to log.
10. Added "lang" attribute at translation element.
11. Fixed plugin icon disappearance when changing Calibre interface language.
12. Improved the functionality to extract original text.

---

## v1.0.2

1. Resolved translation loss during mobi to mobi conversion.
2. Optimized the attempt intervals for failed requests.
3. Changed output file extension from uppercase to lowercase.

---

## v1.0.1

Fixed the bug on clicking YES to open ebook on finish notification.

---

## v1.0.0

First release.
