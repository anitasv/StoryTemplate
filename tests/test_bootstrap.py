"""Bootstrap prompt regressions; no network, real clones, or package installs."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/bootstrap.sh"


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bootstrap-test-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        bin_dir = self.project / "bin"
        bin_dir.mkdir()
        # Force the optional macOS confirmation on every host. Mock git creates
        # only a fixture initializer; nothing touches the actual template repo.
        commands = {
            "uname": "#!/bin/sh\nprintf 'Darwin\\n'\n",
            "typst": "#!/bin/sh\nexit 0\n",
            "git": """#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_ROOT/git.log"
if [ "$1" = clone ]; then
  folder="${@: -1}"
  mkdir -p "$folder/scripts"
  printf '#!/bin/sh\nprintf "%%s\\n" "$@" > metadata.args\n' > "$folder/scripts/template-init.sh"
  chmod +x "$folder/scripts/template-init.sh"
fi
""",
        }
        for name, content in commands.items():
            path = bin_dir / name
            path.write_text(content)
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin",
                        TEST_ROOT=str(self.project))

    def run_installer(self, answers, command_string=True):
        # bash -c receives the downloaded script as an argument, not stdin.
        # Supplying its contents locally tests that behavior without networking.
        command = (["bash", "-c", SCRIPT.read_text()] if command_string
                   else ["bash", str(SCRIPT)])
        return subprocess.run(
            command, input=answers, text=True, capture_output=True,
            cwd=self.project, env=self.env, timeout=10,
        )

    def test_custom_answers_with_command_string_and_direct_execution(self):
        for command_string in (True, False):
            with self.subTest(command_string=command_string):
                folder = "CommandBook" if command_string else "DirectBook"
                result = self.run_installer(
                    f"n\nA Different Story\n{folder}\nTest Author\nfr\nSome rights reserved\n",
                    command_string=command_string,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Project folder [ADifferentStory]", result.stderr)
                self.assertEqual(
                    (self.project / folder / "metadata.args").read_text().splitlines(),
                    ["--title", "A Different Story", "--author", "Test Author",
                     "--language", "fr", "--rights", "Some rights reserved"],
                )
                self.assertFalse((self.project / "MyAwesomeNovel").exists())

    def test_enter_explicitly_accepts_defaults(self):
        result = self.run_installer("\n" * 6)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.project / "MyAwesomeNovel/metadata.args").read_text().splitlines(),
            ["--title", "My Awesome Novel", "--author", "My Pen Name",
             "--language", "en", "--rights", "All rights reserved"],
        )

    def test_eof_does_not_accept_defaults(self):
        # Exercise EOF at the optional confirmation and each metadata prompt.
        for answers in ("", "n\n", "n\nTitle\n", "n\nTitle\nFolder\n",
                        "n\nTitle\nFolder\nAuthor\n",
                        "n\nTitle\nFolder\nAuthor\nen\n"):
            with self.subTest(answers=answers):
                result = self.run_installer(answers)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("could not read an answer", result.stderr)
                self.assertFalse((self.project / "git.log").exists())
                self.assertFalse((self.project / "Folder").exists())
                self.assertFalse((self.project / "MyAwesomeNovel").exists())


if __name__ == "__main__":
    unittest.main()
