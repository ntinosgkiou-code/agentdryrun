"""The version and the names must agree in every place a user can install from. No network: python -m unittest"""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Versions(unittest.TestCase):
    def test_every_manifest_names_the_same_version(self):
        py = re.search(r'^version = "([^"]+)"', read("pyproject.toml"), re.M).group(1)
        npm = json.loads(read("package.json"))["version"]
        plugin = json.loads(read(".claude-plugin", "plugin.json"))["version"]
        cff = re.search(r"^version: (\S+)", read("CITATION.cff"), re.M).group(1)
        self.assertEqual({py, npm, plugin, cff}, {py}, (py, npm, plugin, cff))

    def test_the_readme_pins_the_current_action_version(self):
        py = re.search(r'^version = "([^"]+)"', read("pyproject.toml"), re.M).group(1)
        self.assertIn(f"agentdryrun@v{py}", read("README.md"))


class ClaudeCodePlugin(unittest.TestCase):
    def test_marketplace_lists_the_plugin_under_its_own_name(self):
        plugin = json.loads(read(".claude-plugin", "plugin.json"))
        market = json.loads(read(".claude-plugin", "marketplace.json"))
        self.assertEqual([p["name"] for p in market["plugins"]], [plugin["name"]])
        self.assertEqual(market["plugins"][0]["source"], "./")

    def test_the_scan_skill_is_user_invoked_and_read_only(self):
        text = read("skills", "scan", "SKILL.md")
        head = text.split("---")[1]
        self.assertIn("disable-model-invocation: true", head)             # Claude must not start a history scan on its own
        self.assertIn("--no-previews", text)                              # the page it writes has no command text
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", text)
        self.assertNotIn("--rules", text)                                 # it runs the shipped pack only


if __name__ == "__main__":
    unittest.main()
