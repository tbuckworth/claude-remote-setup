"""python3 -m unittest sync/test_sync_instructions.py  (temporary git repos; nothing is sent)"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_instructions as si  # noqa: E402

BLOCK = "<!-- arrow-board:selected-projects -->\n## Arrow Board\nlocal text\n<!-- /arrow-board:selected-projects -->\n"


def sh(cwd, *args):
    return subprocess.run(list(args), cwd=str(cwd), check=True, capture_output=True, text=True).stdout.strip()


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.origin = self.tmp / "origin.git"
        sh(self.tmp, "git", "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.dev = self.tmp / "dev"  # where changes are made and pushed, as on GitHub
        sh(self.tmp, "git", "clone", "-q", str(self.origin), str(self.dev))
        for d in (self.dev,):
            sh(d, "git", "config", "user.email", "t@example.com")
            sh(d, "git", "config", "user.name", "t")
        (self.dev / "config").mkdir()
        self.commit({"config/AGENTS.shared.md": "# Shared\n", "config/AGENTS.email.md": "# Email v1\n"})
        self.repo = self.tmp / "live"
        sh(self.tmp, "git", "clone", "-q", str(self.origin), str(self.repo))
        self.codex = self.tmp / "codex" / "AGENTS.md"
        self.state = self.tmp / "state" / "status.json"
        self.sent = []
        self.orig = si.email, si.IS_MAC
        si.email = lambda machine, problem: self.sent.append((machine, problem)) or True
        si.IS_MAC = False

    def tearDown(self):
        si.email, si.IS_MAC = self.orig
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def commit(self, files):
        for name, text in files.items():
            (self.dev / name).write_text(text)
        sh(self.dev, "git", "add", "-A")
        sh(self.dev, "git", "commit", "-q", "-m", "change")
        sh(self.dev, "git", "push", "-q", "origin", "HEAD:main")

    def run_once(self):
        si.run(self.repo, self.codex, self.state, check_mac=False)
        return json.loads(self.state.read_text())

    def test_pulls_and_builds_codex(self):
        self.commit({"config/AGENTS.email.md": "# Email v2\n"})
        st = self.run_once()
        self.assertTrue(st["pulled"])
        self.assertIsNone(st["problem"])
        self.assertEqual(self.codex.read_text(), "# Shared\n# Email v2\n")
        self.assertFalse(self.run_once()["codex_rebuilt"])
        self.assertEqual(self.sent, [])

    def test_keeps_marked_block_and_mode(self):
        self.codex.parent.mkdir()
        self.codex.write_text("# Shared\n# old email\n\n" + BLOCK)
        os.chmod(str(self.codex), 0o600)
        self.commit({"config/AGENTS.email.md": "# Email v2\n"})
        self.run_once()
        self.assertEqual(self.codex.read_text(), "# Shared\n# Email v2\n\n" + BLOCK)
        self.assertEqual(self.codex.stat().st_mode & 0o777, 0o600)

    def test_replaces_symlink_without_touching_target(self):
        self.codex.parent.mkdir()
        os.symlink(str(self.repo / "config" / "AGENTS.shared.md"), str(self.codex))
        self.run_once()
        self.assertFalse(self.codex.is_symlink())
        self.assertEqual((self.repo / "config" / "AGENTS.shared.md").read_text(), "# Shared\n")
        self.assertEqual(self.codex.read_text(), "# Shared\n# Email v1\n")

    def test_uncommitted_edit_blocks_pull_and_reports_once(self):
        (self.repo / "config" / "AGENTS.email.md").write_text("# Email local edit\n")
        self.commit({"config/AGENTS.shared.md": "# Shared v2\n"})
        st = self.run_once()
        self.assertFalse(st["pulled"])
        self.assertIn("uncommitted edits to config/AGENTS.email.md", st["problem"])
        # Codex follows the checkout Claude reads, edit included
        self.assertEqual(self.codex.read_text(), "# Shared\n# Email local edit\n")
        self.run_once()
        self.assertEqual(len(self.sent), 1)
        # fixed: the problem clears, and a later problem is reported again
        sh(self.repo, "git", "checkout", "--", "config/AGENTS.email.md")
        st = self.run_once()
        self.assertTrue(st["pulled"])
        self.assertNotIn("reported", st)
        sh(self.repo, "git", "switch", "-q", "-c", "feature")
        self.assertIn("on branch feature", self.run_once()["problem"])
        self.assertEqual(len(self.sent), 2)

    def test_local_commits_block_pull(self):
        sh(self.repo, "git", "config", "user.email", "t@example.com")
        sh(self.repo, "git", "config", "user.name", "t")
        (self.repo / "config" / "AGENTS.email.md").write_text("# local commit\n")
        sh(self.repo, "git", "commit", "-qam", "local")
        self.assertIn("1 commit(s) that are not on GitHub", self.run_once()["problem"])

    def test_untracked_file_in_the_way(self):
        (self.repo / "new.md").write_text("untracked\n")
        self.commit({"new.md": "tracked now\n"})
        st = self.run_once()
        self.assertFalse(st["pulled"])
        self.assertIn("git merge", st["problem"])

    def test_fetch_failure_is_a_problem_only_after_a_day(self):
        sh(self.repo, "git", "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        st = self.run_once()
        self.assertIsNone(st["problem"])
        self.assertTrue(st["fetch_error"])
        st["fetch_failing_since"] -= si.FETCH_GRACE + 60
        self.state.write_text(json.dumps(st))
        self.assertIn("GitHub unreachable since", self.run_once()["problem"])
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
