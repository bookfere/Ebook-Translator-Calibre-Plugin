[English](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/blob/master/README.md) · [简体中文](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/blob/master/README.zh-CN.md) · __正體中文__

---

# 電子書翻譯工具 (Calibre 外掛程式)

![Ebook Translator Calibre Plugin](images/logo.png)

一個可以將電子書翻譯成指定語言 (原文譯文對照) 的 Calibre 外掛程式。

![Translation illustration](images/sample-tc.png)

---

## 主要功能

* 支援所選翻譯引擎所支援的語言 (如 Google 翻譯支援 134 種)
* 支援多種翻譯引擎，包括 Google 翻譯、ChatGPT 以及 DeepL
* 支援自訂翻譯引擎 (可剖析 JSON 和 XML 格式回應)
* 支援所有 Calibre 所支援的電子書格式 (輸入格式 48 種，輸出格式 20 種)
* 支援批次翻譯電子書，每本書的翻譯過程同時進行互不影響
* 支援快取翻譯內容，在要求失敗或網路中斷後無需重新翻譯
* 提供大量自訂設定，如將翻譯的電子書儲存至 Calibre 書庫或指定位置

---

## 安裝外掛程式

首先確保您的作業系統已經安裝了 [Calibre](https://calibre-ebook.com/)，然後透過以下任意方式安裝此外掛程式。

【 __透過 Calibre 安裝__ 】

1. 首先開啟 Calibre 並依次按下其選單【 __偏好設定...__ → __外掛__ → __取得新的外掛__ 】；
2. 然後在插件清單中選取【 __Ebook Translator__ 】，再點擊【 __安裝__ 】按鈕 (請留意，首次安裝此外掛程式時，要選擇將圖示顯示在主工具列上)；
3. 最後關閉並重新開啟 Calibre 即可正常使用。

【 __透過外掛檔案安裝__ 】

1. 首先在[外掛程式發佈頁面](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin/releases)下載外掛程式檔案；
2. 然後開啟 Calibre 並依次按下其選單【偏好設定 → 外掛 → 從檔案載入外掛】，彈出的對話方塊中選取下載的副檔名為 .zip 的外掛程式檔案完成安裝 (請留意，首次安裝此外掛程式時，要選擇將圖示顯示在主工具列上)；
3. 最後關閉並重新開啟 Calibre 即可正常使用。

如果您想安裝最新外掛程式，可以執行以下命令從 GitHub 存放庫中下載最新的外掛程式：

<pre><code>git clone https://github.com/bookfere/Ebook-Translator-Calibre-Plugin.git
cd Ebook-Translator-Calibre-Plugin
git archive --format zip --output ../Ebook-Translator-Calibre-Plugin.zip master</code></pre>

如果安裝外掛程式後，外掛程式圖示未出現在 Calibre 的主工具列上，可以依次按下 Calibre 的選單【偏好設定 → 工具列和選單】，在彈出的對話方塊中按下下拉選單並選擇「主工具列」，然後在左欄找到並選中外掛程式圖示，按下中間的右箭頭按鈕【>】將其新增到右欄，最後按下【儲存】按鈕即可。

---

## 使用方法

1. 在 Calibre 書庫中選中要推送的電子書；
2. 按下 Calibre 主工具列上的【翻譯書籍】圖示按鈕彈出外掛程式主介面，在這裡您可以修改「書名」(作為儲存檔案時使用的檔案名稱)，分別為每一本書選擇「輸入格式」、「輸出格式」、「來源語言」(一般狀況下「自動偵測」即可滿足需求)、「目標語言」(預設使用 Calibre 介面目前使用的語言)；
3. 按下下方的【翻譯】按鈕即可開始翻譯。

外掛程式會將每本電子書的翻譯工作推送新增至 Calibre 的工作佇列，您可以透過按下 Calibre 右下角的【工作】檢視推送詳細資料，按兩下工作條目可以進入記錄實時檢視正在翻譯的內容。

---

## 設定說明

您可以透過「內容」和「設定」選項自訂外掛程式功能。

### 內容

__【 譯文位置 】__

* __加在原文後__ [預設]：將譯文新增至原文後
* __加在原文前__：將譯文新增至原文前
* __僅保留譯文__：刪除原文僅保留譯文

__【 譯文色彩 】__

* __色彩值__：CSS 色彩值，如 #666666, gry, rgb(80, 80, 80)

您可以透過按下【選取】按鈕從調色盤選取色彩，也可以手動輸入色彩值，色彩值可參考 MDN 有關「[色彩值](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value)」的文件。如果留空則不使用自訂色彩。

__【 合併翻譯 】__

* __启用__ [默认不勾选]：啟用合併翻譯功能

您可以在這裡設置單次要翻譯的字元數量，預設值為 2000。

__【 翻譯詞彙表 】__

* __啟用__ [預設不勾選]：啟用選取的翻譯詞彙表

翻譯詞彙表的作用是為某些詞彙指定特定翻譯，或讓翻譯引擎忽略翻譯某些詞彙。

詞彙表是一個純文字檔案，其副檔名為 .txt，格式如下：如果詞彙需要指定翻譯，則兩行為一組，上為原文，下為譯文，如果需要保持詞彙不被翻譯，則一行為一組，每組之間由一個空行分隔。

<pre>The Eiffel Tower
艾菲爾鐵塔

The Statue of Liberty</pre>

__【 忽略翻譯 】__

* __關鍵詞__：依關鍵字排除內容 (每行一條關鍵字)
* __關鍵詞 (區分大小寫)__：依關鍵字排除內容，字母區分大小寫 (每行一條關鍵字)
* __規則運算式__：依規則運算式模式排除內容 (每行一條模式)

規則運算式語法可參考 Python 官方文件中的「[規則運算式語法](https://docs.python.org/3/library/re.html#regular-expression-syntax)」。

### 設定

__【 輸出路徑 】__

* __書庫__ [預設]：電子書翻譯完成後會放入 Calibre 書庫中
* __路徑__：電子書翻譯完成後會存放到指定目錄中

__【 翻譯引擎 】__

* __Google (Free)__ [預設]：免費的翻譯引擎
* __Google (Basic)__：需要 API 金鑰（[取得](https://console.cloud.google.com/apis/credentials)）
* __Google (Advanced)__：需要專案 ID 和 JSON 金鑰檔案（[取得](https://console.cloud.google.com/apis/credentials)）
* __ChatGPT__：需要 API 金鑰（[取得](https://platform.openai.com/account/api-keys)）
* __DeepL__：需要 API 金鑰（[取得](https://www.deepl.com/pro?cta=header-pro-button/)）
* __DeepL (Pro)__：需要 API 金鑰（[取得](https://www.deepl.com/pro?cta=header-pro-button/)）
* __Deep (Free)__：免費的翻譯引擎 (不穩定)
* __Youdao__：需要應用程式金鑰和秘密（[取得](https://ai.youdao.com/console/#/app-overview/create-application)）
* __Baidu__：需要應用程式 ID 和 金鑰（[取得](https://api.fanyi.baidu.com/register)）
* __[自訂]__：自訂任意翻譯引擎

注意，除了 Google(Free) 和 DeepL(Free) 不需要 API 金鑰外，其他內建翻譯引擎都需要您註冊對應帳戶 (可能需要付費) 取得 API 金鑰才能使用。另外，由於外掛程式在開發時缺少 DeepL 的 API 金鑰，依據其官網提供的回應資訊範例，程式可以正常執行，實際執行狀況未知。

如果選擇使用需要付費的翻譯引擎，建議前往對應的官方文件查看計費規則。比如，ChatGPT，可以使用其官方提供的工具 [Tokenizer](https://platform.openai.com/tokenizer) 估算要翻譯字數大約會消耗多少權杖以便預估費用。

您可以按下【測試】按鈕對目前選取的翻譯引擎進行測試。如果翻譯引擎的 API 提供了配額資訊，會在測試翻譯引擎介面下方顯示。

按下【自訂】按鈕可進入「自訂翻譯引擎」介面，在這裡可以新增、刪除或修改翻譯引擎。

設定自訂翻譯引擎的資料格式為 JSON 格式，每次新增一個自訂翻譯引擎後都會看到如下所示的資料範本：

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

其中包含 4 個名稱/值組，分別是 `name`、`languages`、`request` 和 `response`，其含義分別如下，您需要依實際狀況進行修改：

* `name`：顯示在介面上的名稱。如「Bing」
* `languages`：翻譯引擎支援的語言代碼。格式為 `{"語言名稱": "語言代碼"}`。更多詳細資料需參考翻譯引擎 API 文件。也可以分別填寫來源語言和目標語言。
    * `source`：來源語言。格式同上
    * `target`：目標語言。格式同上
* `request`：要求資訊。包含如下名稱/值組
    * `url`：API URL。具體資訊需參考翻譯引擎 API 文件
    * `method`：要求方法 (選用)。省略會預設使用 `GET`
    * `headers`：要求標頭 (選用)。可參考翻譯引擎 API 文件填寫
    * `data`：要求資料。可以是一個 `dict` 物件也可以是字串，如果使用字串需要同時指定適當的要求標頭 `Content-Type`。其中包含 3 個內建變數，其中 `<source>` 和 `<target>` 分別對應之前填寫的語言代碼，如不需要可省略，`<text>` 表示傳送至翻譯引擎的文字，必須保留。其他具體要求資訊需參考翻譯引擎 API 文件。
* `response`：依據自己的需要填寫解析回應資訊的運算式，以提取其中的譯文文字。回應資訊包含在變數 `response` 中，它是一個 [JSON](https://docs.python.org/3/library/json.html#encoders-and-decoders) 對象 (如果翻譯引擎返回的資料是 JSON 格式) 或 lxml 的 [Element](https://lxml.de/apidoc/lxml.etree.html#lxml.etree.ElementBase) 對象 (如果翻譯引擎返回的資料是 XML 格式)。

自訂翻譯引擎資料填寫完成後可以按下介面下方的【驗證】按鈕檢查資料是否有效，最後按下【儲存】按鈕儲存所有的變更。

__【 ChatGPT 提示 】__

* __自動偵測來源語言時的提示__：自訂來源語言為「自動偵測」時的翻譯提示
* __指定來源語言時的提示__：自訂來源語言為指定語言時的翻譯提示

__【 偏好語言 】__

* __目標語言__ [預設介面語言]：設定目標語言的首選語言

__【 網路代理 】__

* __開啟__ [預設不勾選]：開啟網路代理
* __主機__：支援 IP 和網域
* __連接埠__：範圍 0-65536
* __測試__：測試代理的連通性

__【 快取 】__

* __開啟__ [預設勾選]：開啟翻譯內容的快取功能
* __清除__：刪除所有快取

開啟快取功能可以避免要求失敗或網路中斷後對已翻譯過的內容進行重新翻譯。另外，您還可以在這裡看到快取對磁碟空間的佔用量，按下【清除】按鈕可刪除所有快取。注意，如果目前有正在進行的翻譯工作，則清除按鈕無法使用。

__【 要求 】__

* __重試次數__ [預設 3 次]：在要求翻譯引擎失敗後要重試的次數
* __最大間隔__ [預設 5 秒]：向翻譯引擎傳送要求的最大時間間隔

外掛程式對翻譯引擎的每次要求最長可持續 300 秒，逾時後會依指定的次數進行重試，每次重試的等候時間會逐次加長。要求的時間間隔為 1 到指定最大間隔之間的隨機數。

對於 Google 翻譯這種目前可以免費使用的 API，建議酌情加長時間間隔 (建議 5 秒以上)，以免被 Google 翻譯視為濫用，從而導致翻譯中斷或拒絕服務。付費翻譯引擎則可以設為 1。

__【 記錄 】__

* __顯示翻譯__ [預設勾選]：可以在翻譯工作各自的記錄視窗實時檢視翻譯內容

---

## 授權

[GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html)

---

* GitHub：[https://github.com/bookfere/Ebook-Translator-Calibre-Plugin](https://github.com/bookfere/Ebook-Translator-Calibre-Plugin)
* MobileRead: [https://www.mobileread.com/forums/showthread.php?t=353052](https://www.mobileread.com/forums/showthread.php?t=353052)
* 發佈頁面：[https://bookfere.com/post/1057.html](https://bookfere.com/post/1057.html)
* 捐助頁面：[https://www.paypal.com/paypalme/bookfere](https://www.paypal.com/paypalme/bookfere)
