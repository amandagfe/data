import pathlib
import unittest
from collections import Counter
from html.parser import HTMLParser


ROOT = pathlib.Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class AccessibilityContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "style.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.doc = Document()
        cls.doc.feed(cls.html)
        cls.by_id = {
            attrs["id"]: (tag, attrs)
            for tag, attrs in cls.doc.tags
            if "id" in attrs
        }

    def test_document_has_one_main_and_unique_ids(self):
        self.assertEqual(sum(tag == "main" for tag, _ in self.doc.tags), 1)
        ids = [attrs["id"] for _, attrs in self.doc.tags if "id" in attrs]
        self.assertFalse([key for key, count in Counter(ids).items() if count > 1])

    def test_skip_link_and_search_combobox(self):
        skip = next(attrs for tag, attrs in self.doc.tags if tag == "a" and "skip-link" in attrs.get("class", ""))
        self.assertEqual(skip.get("href"), "#conteudo")
        _, search = self.by_id["busca"]
        self.assertEqual(search.get("role"), "combobox")
        self.assertEqual(search.get("aria-controls"), "busca-res")
        self.assertEqual(search.get("aria-expanded"), "false")
        self.assertEqual(search.get("aria-autocomplete"), "list")

    def test_dynamic_states_are_announced(self):
        for element_id in ("geo-status", "simple-state", "pl-status"):
            _, attrs = self.by_id[element_id]
            self.assertEqual(attrs.get("aria-live"), "polite")
        self.assertIn("aria-busy", self.js)

    def test_disclosures_and_visualisations_have_accessible_contracts(self):
        self.assertGreaterEqual(sum(tag == "details" for tag, _ in self.doc.tags), 5)
        self.assertIn("function applyVizAccessibility()", self.js)
        self.assertIn("globeLabel", self.js)

    def test_motion_contrast_and_touch_support_are_present(self):
        self.assertIn("prefers-reduced-motion:reduce", self.css)
        self.assertIn("forced-colors:active", self.css)
        self.assertIn("min-height:44px", self.css)

    def test_visual_accessibility_preferences_are_keyboard_operable(self):
        _, toggle = self.by_id["a11y-toggle"]
        self.assertEqual(toggle.get("aria-controls"), "a11y-panel")
        self.assertEqual(toggle.get("aria-expanded"), "false")
        controls = [attrs for _, attrs in self.doc.tags if "data-a11y" in attrs]
        self.assertEqual({attrs["data-a11y"] for attrs in controls}, {"text", "contrast", "spacing", "motion"})
        self.assertTrue(all(attrs.get("aria-pressed") == "false" for attrs in controls))
        self.assertIn("localStorage", self.js)
        self.assertIn("e.key==='Escape'", self.js)
        for css_class in ("a11y-large-text", "a11y-high-contrast", "a11y-spacing", "a11y-reduce-motion"):
            self.assertIn(css_class, self.css)

    def test_globe_has_complete_text_alternative(self):
        _, globe = self.by_id["globe"]
        self.assertEqual(globe.get("aria-describedby"), "globe-help")
        _, tip = self.by_id["layer-tip"]
        self.assertEqual(tip.get("role"), "tooltip")
        chips = [attrs for _, attrs in self.doc.tags if "data-l" in attrs]
        expected = {"ev", "risk", "rain", "soil", "haz", "sat"}
        self.assertEqual({attrs["data-l"] for attrs in chips}, expected)
        self.assertIn("function showLayerTip(", self.js)
        self.assertIn("addEventListener('focus'", self.js)
        self.assertIn("gibsTimeNote", self.js)


if __name__ == "__main__":
    unittest.main()
