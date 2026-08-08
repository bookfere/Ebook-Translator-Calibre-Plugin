import unittest
import socket
from unittest.mock import patch
from types import GeneratorType

from lxml import etree  # type: ignore

from ...vendor.cssselect import SelectorError

from ...lib.utils import (
    ns, css, css_to_xpath, create_xpath, uid, trim, chunk, group, open_file,
    request, keepalive_socket, _KeepAliveSocket, original_socket)


module_name = 'calibre_plugins.ebook_translator.lib.utils'


class TestUtils(unittest.TestCase):
    def test_css(self):
        self.assertEqual("self::x:div[@id = 'id']", css('div#id'))
        self.assertIsNone(css('div>>p'))  # omit invalid selector

    def test_css_to_xpath(self):
        self.assertEqual([], css_to_xpath([]))
        self.assertEqual([], css_to_xpath(['div>>p']))  # omit invalid selector
        self.assertEqual(["self::x:*[@id = 'test']"], css_to_xpath(['#test']))
        self.assertEqual(
            [
                "self::x:div[@id = 'test']",
                "(self::x:span or self::*[local-name()=\"span\"])"
            ],
            css_to_xpath(["div>>p", 'div#test', 'span']))

    def test_create_xpath(self):
        pattern = create_xpath(('p', 'math',))
        self.assertEqual(
            pattern,
            './/*[(self::x:p or self::*[local-name()="p"]) or '
            '(self::x:math or self::*[local-name()="math"])]')

        # A sample code to test XPath pattern matching with MathML elements
        # that have independent namespaces.
        xhtml = etree.XML("""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body>
    <p>Test MathML element</p>
    <math xmlns="http://www.w3.org/1998/Math/MathML">
        <munder>
            <mo>∑</mo>
            <mi>A</mi>
        </munder>
        <munder displaystyle="true">
            <mo>∑</mo>
            <mi>A</mi>
        </munder>
        <munder>
            <mo>∑</mo>
            <mi scriptlevel="0">A</mi>
        </munder>
    </math>
</body>
</html>""".encode())
        body = xhtml.find('./x:body', namespaces=ns)
        elements = body.xpath(pattern, namespaces=ns)

        self.assertEqual(2, len(elements))
        self.assertEqual('p', etree.QName(elements[0]).localname)
        self.assertEqual('math', etree.QName(elements[1]).localname)

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


class TestKeepAliveSocket(unittest.TestCase):
    """Tests for the TCP keepalive helper used by novel-mode structured
    output (see lib/novel.py::_translate_with_retry_structured)."""

    def test_class_is_a_socket_subclass(self):
        # _KeepAliveSocket must be usable as a drop-in replacement for
        # socket.socket wherever a factory is expected.
        self.assertTrue(issubclass(_KeepAliveSocket, socket.socket))

    def test_can_be_instantiated(self):
        # Instantiation must not fail (does not open a real connection).
        s = _KeepAliveSocket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.assertGreater(s.fileno(), 0)
        finally:
            s.close()

    def test_keepalive_socket_swaps_and_restores(self):
        # Context manager must swap socket.socket while inside the block
        # and put the original one back on exit.
        before = socket.socket
        try:
            with keepalive_socket(enable=True):
                self.assertIs(socket.socket, _KeepAliveSocket)
            self.assertIs(socket.socket, before)
        finally:
            # Safety net: force restore in case the test fails midway so
            # we do not pollute subsequent tests.
            socket.socket = before

    def test_keepalive_socket_disabled_is_noop(self):
        before = socket.socket
        with keepalive_socket(enable=False):
            self.assertIs(socket.socket, before)
        self.assertIs(socket.socket, before)

    def test_keepalive_socket_restores_on_exception(self):
        before = socket.socket
        with self.assertRaises(RuntimeError):
            with keepalive_socket(enable=True):
                self.assertIs(socket.socket, _KeepAliveSocket)
                raise RuntimeError('boom')
        self.assertIs(socket.socket, before)

    def test_keepalive_socket_skips_when_already_patched(self):
        # If someone else (e.g. socks_proxy) has already patched
        # socket.socket, we must NOT overwrite their patch.
        class _AlreadyPatched(socket.socket):
            pass

        before = socket.socket
        socket.socket = _AlreadyPatched
        try:
            with keepalive_socket(enable=True):
                # Our wrapper must have detected the existing patch and
                # left socket.socket untouched.
                self.assertIs(socket.socket, _AlreadyPatched)
        finally:
            socket.socket = before
