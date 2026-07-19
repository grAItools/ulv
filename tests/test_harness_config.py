"""Guards for the harness MCP wiring (stdlib only, no MCP/browser/network).

The Playwright MCP server is configured twice — `.mcp.json` for Claude
Code, `.opencode/opencode.jsonc` for OpenCode — because the two config
formats differ, so version drift between them is the most likely silent
failure. These tests pin both to the same exact version (ADR 0009).
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# The single source of truth for the pinned server version; bumping it
# means editing both config files and this constant in one commit.
PINNED_SERVER = "@playwright/mcp@0.0.78"

REQUIRED_FLAGS = {"--headless", "--isolated", "--caps=vision"}


class TestClaudeCodeMcpConfig:
    def _args(self):
        config = json.loads((REPO_ROOT / ".mcp.json").read_text())
        return config["mcpServers"]["playwright"]["args"]

    def test_pins_exact_server_version(self):
        args = self._args()
        assert PINNED_SERVER in args
        assert not any("@latest" in arg for arg in args)

    def test_required_flags_present(self):
        assert REQUIRED_FLAGS <= set(self._args())

    def test_runs_via_npx(self):
        config = json.loads((REPO_ROOT / ".mcp.json").read_text())
        assert config["mcpServers"]["playwright"]["command"] == "npx"


class TestOpenCodeMcpConfig:
    def test_same_pinned_version_in_lockstep(self):
        # jsonc (comments) — no json.loads; a substring pin is all the
        # guard needs and formatting churn cannot break it.
        text = (REPO_ROOT / ".opencode" / "opencode.jsonc").read_text()
        assert PINNED_SERVER in text
        assert "@playwright/mcp@latest" not in text

    def test_required_flags_present(self):
        text = (REPO_ROOT / ".opencode" / "opencode.jsonc").read_text()
        for flag in REQUIRED_FLAGS:
            assert flag in text, flag


class TestUiParityCheckSkill:
    def test_skill_file_exists_with_frontmatter(self):
        skill = REPO_ROOT / ".agents" / "skills" / "ui-parity-check" / "SKILL.md"
        text = skill.read_text()
        frontmatter = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
        assert frontmatter, "SKILL.md must start with YAML frontmatter"
        assert re.search(r"^name: ui-parity-check$", frontmatter.group(1), re.M)
        assert re.search(r"^description:", frontmatter.group(1), re.M)
