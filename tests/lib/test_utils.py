import unittest
from unittest.mock import patch
from types import GeneratorType

from ...lib.utils import (
    css_to_xpath, uid, trim, chunk, group, open_file, request)


module_name = 'calibre_plugins.ebook_translator.lib.utils'


class TestUtils(unittest.TestCase):
    def test_css_to_xpath(self):
        self.assertEqual(["self::x:*[@id = 'id']"], css_to_xpath(['#id']))

    def test_uid(self):
        self.assertEqual('202cb962ac59075b964b07152d234b70', uid('123'))
        self.assertEqual('202cb962ac59075b964b07152d234b70', uid(b'123'))
        self.assertEqual('e10adc3949ba59abbe56e057f20f883e', uid('123', '456'))

    def test_trim(self):
        self.assertEqual('abc', trim('   abc   '))
        self.assertEqual('a b c', trim(' a b c '))
        self.assertEqual('a b c', trim(' a    b   c '))

        # &#160;
        content = '{0}{0}{1}{1}a{2}{2}{1}b{2}{0}{2}c{1}{1}{0}{0}'.format(
            '\xa0', '\x1a', u'\u3000')
        self.assertEqual('a b c', trim(content))

    def test_chunk(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
        self.assertIsInstance(chunk(data, 3), GeneratorType)
        self.assertEqual([data], list(chunk(data, 1)))
        self.assertEqual(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9, 0]], list(chunk(data, 3)))
        self.assertEqual(
            [[1, 2], [3, 4], [5, 6], [7, 8], [9, 0]], list(chunk(data, 5)))
        self.assertEqual(
            [[1], [2, 3], [4, 5], [6], [7, 8], [9, 0]],
            list(chunk(data, 6)))
        self.assertEqual(
            [[1], [2], [3], [4], [5], [6], [7], [8], [9], [0]],
            list(chunk(data, 10)))
        self.assertEqual(
            [[1], [2], [3], [4], [5], [6], [7], [8], [9], [0]],
            list(chunk(data, 10000000)))
        self.assertEqual(
            [[1], [2], [3], [4], [5], [6], [7], [8], [9], [0]],
            list(chunk(data, 0)))

    def test_group(self):
        self.assertEqual(
            [(1, 1), (3, 3), (5, 5)], group([1, 5, 3]))
        self.assertEqual(
            [(1, 7)], group([1, 2, 3, 4, 5, 6, 7]))
        self.assertEqual(
            [(1, 3), (5, 7), (9, 9)], group([1, 2, 3, 5, 6, 7, 9]))

    @patch(module_name + '.open')
    def test_open_file(self, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = 'a'
        self.assertEqual(open_file('/path/to/file'), 'a')
        mock_open.assert_called_with(
            '/path/to/file', 'r', encoding='utf-8', newline=None)

    @patch(module_name + '.open')
    def test_open_file_with_encoding(self, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = 'a'
        self.assertEqual(open_file('/path/to/file', 'ascii'), 'a')
        mock_open.assert_called_once_with(
            '/path/to/file', 'r', encoding='ascii', newline=None)

    @patch(module_name + '.ssl')
    @patch(module_name + '.Request')
    @patch(module_name + '.Browser')
    def test_request_output_as_string(
            self, mock_browser, mock_request, mock_ssl):
        browser = mock_browser()
        mock_ssl.create_default_context.side_effect = TypeError

        self.assertIs(
            request('https://example.com/api', 'test data'),
            browser.response().read().decode('utf-8').strip())

        browser.set_handle_robots.assert_called_once_with(False)
        mock_ssl._create_unverified_context.assert_called_once_with(
            cert_reqs=mock_ssl.CERT_NONE)
        browser.set_ca_data.assert_called_once_with(
            context=mock_ssl._create_unverified_context())

        mock_request.assert_called_once_with(
            'https://example.com/api', 'test data', headers={}, timeout=30,
            method='GET')
        browser.open.assert_called_once_with(mock_request())

    @patch(module_name + '.ssl')
    @patch(module_name + '.Request')
    @patch(module_name + '.Browser')
    def test_request_output_as_raw_object(
            self, mock_browser, mock_request, mock_ssl):
        browser = mock_browser()
        mock_ssl.create_default_context.side_effect = TypeError

        self.assertIs(
            request('https://example.com/api', 'test data', raw_object=True),
            browser.response())

        browser.set_handle_robots.assert_called_once_with(False)
        mock_ssl._create_unverified_context.assert_called_once_with(
            cert_reqs=mock_ssl.CERT_NONE)
        browser.set_ca_data.assert_called_once_with(
            context=mock_ssl._create_unverified_context())

        mock_request.assert_called_once_with(
            'https://example.com/api', 'test data', headers={}, timeout=30,
            method='GET')
        browser.open.assert_called_once_with(mock_request())

    @patch(module_name + '.ssl')
    @patch(module_name + '.Request')
    @patch(module_name + '.Browser')
    def test_request_with_proxy(self, mock_browser, mock_request, mock_ssl):
        browser = mock_browser()

        self.assertIs(
            request(
                'https://example.com/api', 'test data',
                headers={'User-Agent': 'Test/Agent'}, method='POST',
                timeout=30, proxy_uri='http://127.0.0.1:1234'),
            browser.response().read().decode('utf-8').strip())

        browser.set_handle_robots.assert_called_once_with(False)
        mock_ssl.create_default_context.assert_called_once()
        mock_ssl_context = mock_ssl.create_default_context()
        self.assertTrue(mock_ssl_context.check_hostname)
        self.assertEqual(mock_ssl_context.verify_mode, mock_ssl.CERT_REQUIRED)
        browser.set_ca_data.assert_called_once_with(context=mock_ssl_context)
        browser.set_proxies.assert_called_once_with({
            'http': 'http://127.0.0.1:1234', 'https': 'http://127.0.0.1:1234'})

        mock_request.assert_called_once_with(
            'https://example.com/api', 'test data',
            headers={'User-Agent': 'Test/Agent'}, timeout=30, method='POST')
        browser.open.assert_called_once_with(mock_request())
