# 电子书翻译器（Calibre 插件）

一个可以将电子书翻译成指定语言（原文译文对照）的插件。

---

其他语言：[English](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/blob/master/README.md) · [正體中文](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/blob/master/README.zh-TW.md)

---

## 主要功能

* 支持所选翻译引擎所支持的语言（如 Google 翻译支持 134 种）
* 支持多种翻译引擎，包括 Google 翻译、ChatGPT 以及 DeepL
* 支持自定义翻译引擎（支持解析 JSON 和 XML 格式响应）
* 支持所有 Calibre 所支持的电子书格式（输入格式 48 种，输出格式 20 种）
* 支持批量翻译电子书，每本书的翻译过程同时进行互不影响
* 支持缓存翻译内容，在请求失败或网络中断后无需重新翻译
* 提供大量自定义设置，如将翻译的电子书存到 Calibre 书库或指定位置

---

## 安装插件

首先确保你的操作系统已经安装了 [Calibre](https://calibre-ebook.com/)。

1. 首先在[插件发布页面](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/releases))下载插件文件；
2. 然后打开 Calibre 并依次点击其菜单【首选项 → 插件 → 从文件加载插件】，弹出的对话框中选择下载的后缀名为 .zip 的插件文件完成安装（请留意，首次安装此插件时，要选择把图标显示在主工具栏上）；
3. 最后关闭并重新打开 Calibre 即可正常使用。

如果安装插件后，插件图标未出现在 Calibre 的主工具栏上，可以依次点击 Calibre 的菜单【首选项 → 工具与菜单】，在弹出的对话框中点击下拉菜单并选择“主工具栏”，然后在左栏找到并选中插件图标，点击中间的右箭头按钮【>】将其添加到右栏，最后点击【应用】按钮即可。

---

## 使用方法

1. 在 Calibre 书库中选中要推送的电子书；
2. 点击 Calibre 主工具栏上的【翻译书籍】图标按钮弹出插件主界面，在这里你可以修改“书名”（作为保存文件时使用的文件名），分别为每一本书选择“输入格式”、“输出格式”、“来源语言”（一般情况下“自动探测”即可满足需求）、“目标语言”（默认使用 Calibre 界面当前所用的语言）；
3. 点击下方的【翻译】按钮即可开始翻译。

插件会将每本电子书的翻译任务推送添加到 Calibre 的任务队列，你可以通过点击 Calibre 右下角的【任务】查看推送详情，双击任务条目可以进入日志实时查看正在翻译的内容。

---

## 设置说明

你可以通过“内容”和“设置”选项定制插件功能。

### 内容

__【 译文位置 】__

* __加在原文后__ [默认]：将译文添加到原文后
* __加在原文前__：将译文添加到原文前
* __不保留原文__：删除原文只保留译文

__【 译文颜色 】__

* __颜色值__：CSS 颜色值，如 #666666, gry, rgb(80, 80, 80)

你可以通过点击【选择】按钮从调色盘选取颜色，也可以手动输入颜色值，颜色值可参考 MDN 有关“[颜色值](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value)”的文档。如果留空则不使用自定义颜色。

__【 忽略翻译 】__

* __关键词__：排除带关键词的内容（一行一条关键词）
* __关键词（区分大小写）__：排除带关键词的内容，字母区分大小写（一行一条关键词）
* __正则表达式__：排除匹配正则表达式规则的内容（一行一条规则）

正则表达式语法可参考 Python 官方文档中的“[正则表达式语法](https://docs.python.org/3/library/re.html#regular-expression-syntax)”。

### 设置

__【 输出路径 】__

* __书库__ [默认]：电子书翻译完成后会放入 Calibre 书库中
* __路径__：电子书翻译完成后会存放到指定目录中

__【 翻译引擎 】__

* __Google__ [默认]：免费的翻译引擎
* __ChatGPT__：需要 API 密钥
* __DeepL__：需要 API 密钥
* __DeepL(Pro)__：需要 API 密钥
* __有道__：需要 APP key 和 secret
* __百度__：需要 APP id 和 key
* __自定义__：自定义任意翻译引擎

注意，除了 Google 不需要 API 密钥外，其他翻译引擎都需要你注册相应账户（可能需要付费）获取 API 密钥才能使用。另外，由于插件在开发时缺少 DeepL 的 API 密钥，根据其官网提供的响应信息样例，程序可以正常运行，实际运行情况未知。

如果选择使用需要付费的翻译引擎，建议前往相应的官方文档查看计费规则。比如，ChatGPT，可以使用其官方提供的工具 [Tokenizer](https://platform.openai.com/tokenizer) 估算要翻译字数大约会消耗多少 token 以便预估费用。

你可以点击【测试】按钮对当前所选翻译引擎进行测试。如果翻译引擎的 API 提供了余量信息，会在测试界面下方显示。

点击【自定义】按钮可进入“自定义翻译引擎”界面，在这里可以添加、删除或修改翻译引擎。

配置自定义翻译引擎的数据格式是 JSON 格式，每次新建一个自定义翻译引擎后都会看到如下所示的模板数据：

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

其中包含 4 个键值对，分别是 `name`、`languages`、`request` 和 `response`，其含义分别如下，你需要根据实际情况进行修改：

* `name`：显示在界面上的名称。如“Bing”
* `languages`：翻译引擎支持的语言代码。格式为 `{"语言名称": "语言代码"}`。具体信息需参考翻译引擎 API 文档。也可以分别填写来源语言和目标语言。
    * `source`：来源语言。格式同上
    * `target`：目标语言。格式同上
* `request`：请求信息。包含如下键值对
    * `url`：API 网址。具体信息需参考翻译引擎 API 文档
    * `method`：请求方法（可选）。省略会默认使用 `GET`
    * `headers`：请求标头（可选）。可参考翻译引擎 API 文档填写
    * `data`：请求数据。可以是一个 `dict` 对象也可以是字符串，如果使用字符串需要同时指定合适的请求标头 `Content-Type`。其中包含 3 个内置变量，其中 `<source>` 和 `<target>` 分别对应之前填写的语言代码，如不需要可省略，`<text>` 表示发送给翻译引擎的文本，必须保留。其他具体请求信息需参考翻译引擎 API 文档。
* `response`：根据自己的需要填写解析响应信息的表达式，以抽取其中的译文文本。响应信息包含在变量 `response` 中，它是一个 [JSON](https://docs.python.org/3/library/json.html#encoders-and-decoders) 对象（如果翻译引擎返回的数据是 JSON 格式）或 lxml 的 [Element](https://lxml.de/apidoc/lxml.etree.html#lxml.etree.ElementBase) 对象（如果翻译引擎返回的数据是 XML 格式）。

自定义翻译引擎数据填写完成后可以点击界面下方的【验证】按钮检查数据是否有效，最后点击【保存】按钮保存所有的修改。

__【 ChatGPT提示词 】__

* __自动探测来源语言时的提示词__：自定义当来源语言为“自动探测”时的翻译提示词
* __指定来源语言时的提示词__：自定义当来源语言为指定语言时的翻译提示词

__【 网络代理 】__

* __开启__ [默认不勾选]：开启网络代理
* __主机__：支持 IP 和域名
* __端口__：范围 0-65536
* __测试__：测试代理的连通性

__【 缓存 】__

* __开启__ [默认勾选]：开启翻译内容的缓存功能
* __清除__：删除所有缓存

开启缓存功能可以避免请求失败或网络中断后对已翻译过的内容进行重新翻译。另外，你还可以在这里看到缓存对磁盘空间的占用量，点击【清除】按钮可删除所有缓存。注意，如果当前有正在进行的翻译任务，则清除按钮不可用。

__【 请求 】__

* __重试次数__ [默认 3 次]：当请求翻译引擎失败后要重试的次数
* __最大间隔__ [默认 5 秒]：向翻译引擎发送请求的最大时间间隔

插件对翻译引擎的每次请求最长可持续 300 秒，超时后会按照指定的次数进行重试，每次重试的等待时间会逐次加长。请求的时间间隔为 1 到指定最大间隔之间的随机数。

对于 Google 翻译这种目前可以免费使用的接口，建议酌情加长时间间隔（建议 5 秒以上），以免被 Google 翻译视为滥用，从而导致翻译中断或拒绝服务。付费翻译引擎则可以设为 1。

__【 日志 】__

* __显示翻译__ [默认勾选]：可以在翻译任务各自的日志窗口实时查看翻译内容

---

## 许可证

[GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html)

---

* GitHub：[https://github.com/bookfere/Ebook-Translator-Calibre-Plugin](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin)
* MobileRead: [https://www.mobileread.com/forums/showthread.php?t=353052](https://www.mobileread.com/forums/showthread.php?t=353052)
* 发布页面：[https://bookfere.com/post/1057.html](https://bookfere.com/post/1057.html)
* 赞赏页面：[https://bookfere.com/donate](https://bookfere.com/donate)
