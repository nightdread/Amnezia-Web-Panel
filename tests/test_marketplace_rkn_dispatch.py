"""Execute the marketplace Install onclick, not just search the template text.

The RKN Block card used to compute a host-level `action` and then ignore it:
the button interpolated `installFromMarketplace('${app.proto}')`. A source
search for the literal `installFromMarketplace('rknblock'` still passed.
These tests render the real `renderMarketplace()` body and run the attribute
that ends up on the button.
"""
import json
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def marketplace_harness(proto='rknblock', installed=False, multi=False):
    source = (ROOT / 'templates' / 'server.html').read_text(encoding='utf-8')
    start = source.index('    function marketplaceAppStatus(')
    end = source.index('    function openMarketplaceModal(', start)
    stubs = """
const MARKETPLACE_CATEGORIES = [{id: 'vpn', icon: '', titleKey: 'vpn'}];
const MARKETPLACE_APPS = [%s];
const rknBlockStatus = %s;
const calls = [];
function _(key) { return key; }
function baseInstalled(name) { return name !== 'rknblock' && %s; }
function isMultiInstanceBase() { return %s; }
function closeModal(name) { calls.push(['close', name]); }
function installRknBlock() { calls.push(['rkn']); }
function installFromMarketplace() { calls.push(['protocol'].concat([].slice.call(arguments))); }
""" % (
        json.dumps({
            'proto': proto,
            'category': 'vpn',
            'title': proto,
            'icon': '',
            'descKey': 'description',
        }),
        json.dumps({'installed': installed}),
        json.dumps(installed),
        json.dumps(multi),
    )
    return stubs + source[start:end]


class MarketplaceCardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self.badges = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button':
            self.buttons.append(attrs)
        if tag == 'span' and 'badge' in attrs.get('class', ''):
            self.badges.append(attrs['class'])


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class MarketplaceRknDispatchTests(unittest.TestCase):
    def render(self, **kwargs):
        harness = marketplace_harness(**kwargs)
        script = harness + """
const target = {innerHTML: ''};
const document = {getElementById: function () { return target; }};
renderMarketplace();
console.log(JSON.stringify({html: target.innerHTML}));
"""
        result = subprocess.run(
            ['node', '-e', script], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        html = json.loads(result.stdout)['html']
        parser = MarketplaceCardParser()
        parser.feed(html)
        self.assertEqual(len(parser.buttons), 1)
        return parser, harness

    def click(self, parser, harness):
        button = parser.buttons[0]
        handler = '' if 'disabled' in button else button.get('onclick', '')
        result = subprocess.run(
            ['node', '-e', harness + '\n' + handler + ';console.log(JSON.stringify(calls));'],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_rkn_install_onclick_runs_host_level_installer(self):
        parser, harness = self.render()
        calls = self.click(parser, harness)
        self.assertEqual(calls, [['close', 'marketplaceModal'], ['rkn']])
        self.assertNotIn('protocol', [call[0] for call in calls])
        self.assertTrue(any('badge-warn' in cls for cls in parser.badges))

    def test_installed_rkn_is_disabled_with_installed_badge(self):
        parser, harness = self.render(installed=True)
        self.assertIn('disabled', parser.buttons[0])
        self.assertEqual(self.click(parser, harness), [])
        self.assertTrue(any('badge-success' in cls for cls in parser.badges))

    def test_regular_protocol_still_uses_generic_installer(self):
        cases = (
            (False, False, [['protocol', 'awg', False]]),
            (True, False, []),
            (True, True, [['protocol', 'awg', True]]),
        )
        for installed, multi, expected in cases:
            with self.subTest(installed=installed, multi=multi):
                parser, harness = self.render(proto='awg', installed=installed, multi=multi)
                self.assertEqual(self.click(parser, harness), expected)


if __name__ == '__main__':
    unittest.main()
