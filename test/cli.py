#!/usr/bin/env python3
"""Exercise the combined command through its public process interface."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BINARY = str(Path(sys.argv.pop(1)).resolve())
CORE = str(Path(sys.argv.pop(1)).resolve())


class CommandTests(unittest.TestCase):
    def invoke(self, *arguments, source="", env=None, cwd=None):
        environment = dict(os.environ, CARP_DIR=str(Path(CORE).parent), METACARP_HISTORY="")
        if env:
            environment.update(env)
        return subprocess.run(
            [BINARY, *arguments], input=source, text=True,
            capture_output=True, env=environment, cwd=cwd, timeout=90,
        )

    def test_help_explains_both_modes_without_loading_core(self):
        result = self.invoke("--help", env={"CARP_DIR": "/nonexistent"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("metacarp repl", result.stdout)
        self.assertIn("<source.carp>", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_repl_help_without_loading_core(self):
        result = self.invoke("repl", "--help", env={"CARP_DIR": "/nonexistent"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--history", result.stdout)
        self.assertIn(":inspect", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_default_is_a_persistent_repl_with_error_recovery(self):
        result = self.invoke(source="(def x 40)\n(no-such-function)\n(Int.+ x 2)\n:q\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("x : Int", result.stdout)
        self.assertIn("42", result.stdout)
        self.assertIn("no-such-function", result.stderr)
        self.assertNotIn("λ>", result.stdout)

    def test_explicit_repl_accepts_core_and_history_options(self):
        result = self.invoke("repl", "--core", CORE, "--no-history", source="(Int.+ 20 22)\n:q\n",
                             env={"CARP_DIR": "/nonexistent"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("42", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_repl_option_errors_are_not_compiler_inputs(self):
        for option, diagnostic in [("--history", "needs a file"), ("--core", "needs a directory"),
                                   ("--unknown", "unknown option")]:
            with self.subTest(option=option):
                result = self.invoke("repl", option)
                self.assertEqual(result.returncode, 2)
                self.assertIn(diagnostic, result.stderr)
                self.assertNotIn("cannot read", result.stderr)

    def test_private_worker_entry_requires_its_inherited_context(self):
        result = subprocess.run(
            [BINARY, "repl", "--repl-worker", CORE, "/tmp", "0"],
            capture_output=True, text=True, timeout=10, start_new_session=True,
        )
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_version_names_the_combined_command(self):
        result = self.invoke("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("metacarp "), result.stdout)

    def test_file_arguments_still_compile_and_execute(self):
        with tempfile.TemporaryDirectory(prefix="metacarp-cli-") as directory:
            path = Path(directory, "program.carp")
            path.write_text('(defn main [] (IO.println "compiled through metacarp"))\n')
            emitted = self.invoke("--core", CORE, str(path))
            self.assertEqual(emitted.returncode, 0, emitted.stderr)
            self.assertIn("int main(", emitted.stdout)
            output = str(Path(directory, "program"))
            built = self.invoke("--core", CORE, "-b", "-o", output, str(path))
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([output], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "compiled through metacarp\n")
            executed = self.invoke("--core", CORE, "-x", str(path), cwd=directory)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(executed.stdout, "compiled through metacarp\n")

    def test_compiler_option_errors_do_not_start_a_repl(self):
        result = self.invoke("--unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option", result.stderr)
        self.assertNotIn("λ>", result.stdout)

    def test_named_package_file_and_local_override_load_together(self):
        with tempfile.TemporaryDirectory(prefix="metacarp-cli-load-") as directory:
            root = Path(directory)
            cache = root / "cache"
            packages = cache / "carp/libs/example.org_COLON_packages"
            selected = packages / "selected/development"
            selected.mkdir(parents=True)
            (selected / "selected.carp").write_text('(defn selected [] 1000)\n')
            (selected / "entry.carp").write_text('(defn selected [] 40)\n')
            extra = packages / "extra/development"
            extra.mkdir(parents=True)
            (extra / "extra.carp").write_text('(defn extra [] 1000)\n')
            override = root / "override.carp"
            override.write_text('(defn extra [] 2)\n')
            source = root / "program.carp"
            source.write_text(
                '(load "git@example.org:packages/selected@development" "entry.carp")\n'
                '(load "git@example.org:packages/extra@development")\n'
                '(defn main [] (IO.println &(Int.str (Int.+ (selected) (extra)))))\n'
            )
            result = self.invoke(
                "--core", CORE, "--package-override",
                f"git@example.org:packages/extra@development={override}", "-x", str(source),
                env={"XDG_CACHE_HOME": str(cache), "CARP_PACKAGE_OVERRIDES": ""},
                cwd=directory,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "42\n")


if __name__ == "__main__":
    unittest.main()
