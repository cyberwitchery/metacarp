#!/usr/bin/env python3
"""Process and PTY checks for the real session/JIT REPL."""
import errno
import argparse
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import tempfile
import time
import unittest

from screen import Screen

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("binary")
parser.add_argument("core")
parser.add_argument("--subcommand")
options, remaining = parser.parse_known_args()
sys.argv = [sys.argv[0], *remaining]
BINARY = str(Path(options.binary).resolve())
CORE = str(Path(options.core).resolve())
COMMAND = [BINARY, *([options.subcommand] if options.subcommand else [])]


class Terminal:
    def __init__(self, *options, color=True):
        self.options = options
        self.color = color

    def __enter__(self):
        self.child, self.master = pty.fork()
        if self.child == 0:
            os.environ["TERM"] = "xterm-256color"
            os.environ["METACARP_HISTORY"] = ""
            os.environ.pop("NO_COLOR", None)
            if not self.color:
                os.environ["NO_COLOR"] = "1"
            os.execv(BINARY, [*COMMAND, "--core", CORE, *self.options])
        self.initial_terminal = termios.tcgetattr(self.master)
        self.buffer = b""
        self.raw = b""
        self.screen = Screen()
        self.until("λ> ".encode())
        return self

    def send(self, keys):
        os.write(self.master, keys)

    def until_style(self, marker, timeout=5):
        deadline = time.monotonic() + timeout
        while marker not in self.raw:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.master], [], [], remaining)[0]:
                raise AssertionError(f"missing style {marker!r}: {self.raw!r}")
            chunk = os.read(self.master, 65536)
            if not chunk:
                raise AssertionError("terminal closed while waiting for analysis")
            self.raw += chunk
            self.screen.feed(chunk)
            self.buffer += chunk
            self.buffer = re.sub(rb"\x1b\[[0-9;]*m", b"", self.buffer)

    def until(self, marker, timeout=None):
        if timeout is None:
            timeout = float(os.environ.get("REPL_TEST_TIMEOUT", "5"))
        deadline = time.monotonic() + timeout
        while marker not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.master], [], [], remaining)[0]:
                raise AssertionError(f"missing {marker!r}: {self.buffer!r}")
            try:
                chunk = os.read(self.master, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                chunk = b""
            if not chunk:
                raise AssertionError(f"terminal closed before {marker!r}: {self.buffer!r}")
            self.buffer += chunk
            self.raw += chunk
            self.screen.feed(chunk)
            self.buffer = re.sub(rb"\x1b\[[0-9;]*m", b"", self.buffer)
        before, self.buffer = self.buffer.split(marker, 1)
        return before

    def wait_screen(self, predicate, description, timeout=None):
        deadline = time.monotonic() + (timeout or float(os.environ.get("REPL_TEST_TIMEOUT", "5")))
        while not predicate():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.master], [], [], remaining)[0]:
                raise AssertionError(f"missing {description}: {self.screen.text()!r}")
            chunk = os.read(self.master, 65536)
            if not chunk:
                raise AssertionError("terminal closed while waiting for screen state")
            self.raw += chunk
            self.buffer += chunk
            self.screen.feed(chunk)
            self.buffer = re.sub(rb"\x1b\[[0-9;]*m", b"", self.buffer)

    def displayed(self, text, timeout=None):
        if isinstance(text, bytes):
            text = text.decode()
        self.wait_screen(lambda: text in self.screen.text(False), repr(text), timeout)

    def read_for(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], .02)[0]:
                chunk = os.read(self.master, 65536)
                if not chunk:
                    raise AssertionError("terminal closed while observing updates")
                self.raw += chunk
                self.buffer += chunk
                self.screen.feed(chunk)
                self.buffer = re.sub(rb"\x1b\[[0-9;]*m", b"", self.buffer)

    def cursor_at(self, row, column):
        self.wait_screen(lambda: (self.screen.row, self.screen.column) == (row, column), f"cursor at {row},{column}")

    def resize(self, rows, columns):
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
        self.screen.resize(rows, columns)
        os.kill(self.child, signal.SIGWINCH)

    def result(self, keys, value):
        self.send(keys + b"\r")
        self.until(value + b"\r\n")
        self.until("λ> ".encode())

    def next_prompt(self):
        self.until(b"\x1b[?2004l")
        self.until("λ> ".encode())

    def __exit__(self, *unused):
        os.close(self.master)
        if self.child is not None:
            child, _ = os.waitpid(self.child, os.WNOHANG)
            if not child:
                os.kill(self.child, signal.SIGKILL)
                os.waitpid(self.child, 0)


class ScreenTests(unittest.TestCase):
    def test_partial_overwrite_and_tail_erasure(self):
        screen = Screen(3, 8)
        screen.feed(b"abcdef\r\x1b[2CXY\x1b[K")
        self.assertEqual(screen.line(0), "abXY")
        self.assertEqual((screen.row, screen.column), (0, 4))

    def test_rendition_is_per_cell_and_reset_does_not_erase_text(self):
        screen = Screen(3, 8)
        screen.feed(b"\x1b[3mx\x1b[0my")
        self.assertEqual(screen.line(0), "xy")
        self.assertEqual(screen.cells[0][0][1], (False, True, None))
        self.assertEqual(screen.cells[0][1][1], (False, False, None))

    def test_utf8_combining_and_pending_wrap(self):
        screen = Screen(3, 4)
        data = "é🐟x".encode()
        for byte in data:
            screen.feed(bytes([byte]))
        self.assertEqual(screen.line(0), "é🐟x")
        screen.feed(b"y")
        self.assertEqual(screen.line(1), "y")


class ReplTests(unittest.TestCase):
    def test_c_inspects_support_for_the_last_cell(self):
        result = self.run_repl('[1 2]\n:c\n:q\n')
        self.assertEqual(result.stderr, "")
        self.assertIn("// C support artifact", result.stdout)
        self.assertIn("// input repl:1 revision 1", result.stdout)
        self.assertIn("_carpabi", result.stdout)
        self.assertIn("// Array.delete :", result.stdout)
        self.assertNotIn("// Array.str :", result.stdout)
        self.assertNotIn("#include", result.stdout)
        self.assertNotIn("Random", result.stdout)

    def test_c_reports_llvm_only_and_uncompiled_definitions(self):
        result = self.run_repl(':c\n(def x 1)\n:c x\n(println* x)\n:c x\n:q\n')
        self.assertEqual(result.stderr, "")
        self.assertIn("no evaluated cell", result.stdout)
        self.assertIn("x: not compiled yet", result.stdout)
        self.assertIn("no generated C support for x", result.stdout)
        self.assertNotIn("#include", result.stdout)

    def test_c_full_is_the_published_support_translation_unit(self):
        focused = self.run_repl('[1 2]\n:c\n:q\n')
        complete = self.run_repl('[1 2]\n:c --full\n:q\n')
        self.assertEqual(focused.stderr + complete.stderr, "")
        self.assertIn("// C support artifact", complete.stdout)
        self.assertIn("#include", complete.stdout)
        self.assertIn("carp_llvm_malloc", complete.stdout)
        self.assertNotIn("int main(", complete.stdout)

    def test_c_rejects_source_without_mutating_runtime_or_last_cell(self):
        result = self.run_repl('(def x 1)\n[1 2]\n:c (do (set! x 99) x)\n:c\n(println* x)\n:q\n')
        self.assertIn("usage: :c", result.stderr)
        self.assertIn("// input repl:2 revision 2", result.stdout)
        self.assertTrue(result.stdout.endswith("1\n"), result.stdout)

    def test_c_render_labels_an_alternate_compilation_and_preserves_artifacts(self):
        result = self.run_repl('(def x 1)\n[1 2]\n:c-render (do (set! x 99) x)\n:c\n(println* x)\n:q\n')
        self.assertEqual(result.stderr, "")
        self.assertIn("// Alternate C-backend rendering; not executed by the REPL.", result.stdout)
        self.assertIn("#include", result.stdout)
        self.assertIn("// input repl:2 revision 2", result.stdout)
        self.assertTrue(result.stdout.endswith("1\n"), result.stdout)

    def test_c_selects_native_templates_through_published_function_dependencies(self):
        result = self.run_repl('''(deftemplate native-add (Fn [Int] Int) "int $NAME(int x)" "$DECL { return x + 1; }")
(defn applied [x] (native-add x))
:c applied
(applied 41)
:c applied
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertIn("applied: not compiled yet", result.stdout)
        self.assertIn("// native-add : (Fn [Int] Int)", result.stdout)
        self.assertIn("// source repl:1 revision 1", result.stdout)
        self.assertIn("return x + 1;", result.stdout)
        self.assertNotIn("Pointer", result.stdout)
        self.assertNotIn("Random", result.stdout)

    def test_c_render_restores_compiler_settings_after_failure(self):
        result = self.run_repl('''(def x 1)
:c-render (do (add-cflag "-fmetacarp-missing-flag") (missing-render-function))
[1 2]
:c
(println* x)
:q
''')
        self.assertIn("resolve:", result.stderr)
        self.assertNotIn("clang", result.stderr)
        self.assertIn("// input repl:2 revision 2", result.stdout)
        self.assertTrue(result.stdout.endswith("1\n"), result.stdout)

    def test_c_ignores_auxiliary_and_failed_publications(self):
        result = self.run_repl('[1 2]\n:inspect 1 0\n(missing-function)\n:c\n:q\n')
        self.assertIn("resolve:", result.stderr)
        self.assertIn("// input repl:1 revision 1", result.stdout)
        self.assertNotIn("// input repl:inspect", result.stdout)

    def test_c_support_provenance_survives_mixed_session_replacement(self):
        result = self.run_repl('''(deftemplate native-mixed (Fn [] Int) "int $NAME(void)" "$DECL { return 11; }") (native-mixed)
(deftemplate native-mixed (Fn [] Int) "int $NAME(void)" "$DECL { return 22; }") (native-mixed)
:c native-mixed
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertEqual(re.findall(r"^(11|22)$", result.stdout, re.M), ["11", "22"])
        actual = int(re.findall(r"^(11|22)$", result.stdout, re.M)[-1])
        shown = int(re.search(r"return (11|22);", result.stdout)[1])
        self.assertEqual(shown, actual, result.stdout)
        self.assertIn("// source repl:2 revision 2", result.stdout)
        self.assertEqual(result.stdout.count("// source repl:"), 1)

    def test_c_source_origin_uses_the_active_compiler_definition(self):
        result = self.run_repl('''(deftemplate native-origin (Fn [] Int) "int $NAME(void)" "$DECL { return 11; }")
(deftemplate native-origin (Fn [] Int) "int $NAME(void)" "$DECL { return 22; }")
(native-origin)
:c native-origin
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertIn("return 22;", result.stdout)
        self.assertIn("// source repl:2 revision 2", result.stdout)
        self.assertNotIn("// source repl:1 revision 1", result.stdout)

    def test_discarded_staged_session_retires_its_c_support(self):
        result = self.run_repl('''(deftemplate staged-native (Fn [] Int) "int $NAME(void)" "$DECL { return 11; }") (register staged-missing (Fn [] Int) "metacarp_staged_missing") (ignore (staged-native)) (staged-missing)
(deftemplate staged-native (Fn [] Int) "int $NAME(void)" "$DECL { return 22; }") (staged-native)
:c staged-native
:q
''')
        self.assertIn("jit:", result.stderr)
        self.assertEqual(re.findall(r"^(11|22)$", result.stdout, re.M), ["22"])
        actual = int(re.findall(r"^(11|22)$", result.stdout, re.M)[-1])
        shown = int(re.search(r"return (11|22);", result.stdout)[1])
        self.assertEqual(shown, actual, result.stdout)
        self.assertIn("// input repl:2 revision 2", result.stdout)
        self.assertNotIn("// input repl:1 revision 0", result.stdout)

    def test_native_template_redefinition_replaces_executable_code(self):
        result = self.run_repl('''(deftemplate native-replace (Fn [] Int) "int $NAME(void)" "$DECL { return 11; }")
(native-replace)
(deftemplate native-replace (Fn [] Int) "int $NAME(void)" "$DECL { return 22; }")
(native-replace)
:c native-replace
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertEqual(re.findall(r"^(11|22)$", result.stdout, re.M), ["11", "22"])
        self.assertIn("return 22;", result.stdout)
        self.assertNotIn("return 11;", result.stdout)

    def test_native_support_calls_llvm_closures_in_the_same_publication(self):
        result = self.run_repl('''(deftemplate native-callback (Fn [(Fn [] Int)] Int) "int $NAME(Lambda f)" "$DECL { return ((int (*)(void *))f.callback)(f.env); }")
(let [x 41] (native-callback (fn [] (Int.inc x))))
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_native_support_state_persists_until_its_generation_is_retired(self):
        definition = '(deftemplate native-counter (Fn [] Int) "int $NAME(void)" "$DECL { static int calls; return ++calls; }")\n'
        extra = '(deftemplate native-extra (Fn [] Int) "int $NAME(void)" "$DECL { return 9; }")\n'
        result = self.run_repl(definition + extra + '(native-counter)\n(native-extra)\n(native-counter)\n:reset\n' + definition + '(native-counter)\n:q\n')
        self.assertEqual(result.stderr, "")
        self.assertRegex(result.stdout, r"(?m)^9$")
        self.assertEqual(re.findall(r"^[12]$", result.stdout, re.M), ["1", "2", "1"])

    def test_reset_retires_c_code_and_artifacts_together(self):
        result = self.run_repl('''(deftemplate native-reset (Fn [] Int) "int $NAME(void)" "$DECL { return 11; }")
(native-reset)
:reset
(deftemplate native-reset (Fn [] Int) "int $NAME(void)" "$DECL { return 22; }")
(native-reset)
:c native-reset
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertEqual(re.findall(r"^(11|22)$", result.stdout, re.M), ["11", "22"])
        self.assertIn("return 22;", result.stdout)
        self.assertNotIn("return 11;", result.stdout)

    def test_llvm_inspects_published_global_storage_and_initializer(self):
        result = self.run_repl("(def x 1)\n(println* x)\n:llvm x\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("; source repl:1 revision 1", result.stdout)
        self.assertIn("generation 0", result.stdout)
        self.assertIn("@C1_x__I = global i32 0", result.stdout)
        self.assertIn("store i32 1, ptr @C1_x__I", result.stdout)
        self.assertNotIn("Random", result.stdout)
        self.assertNotIn("repl-inspection", result.stdout)

    def test_bare_llvm_inspects_the_last_executed_cell(self):
        result = self.run_repl("(println* 42)\n:llvm\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("; cell repl:1 revision 1", result.stdout)
        self.assertIn("define i32 @carp_llvm_roots_", result.stdout)
        self.assertIn("i32 42", result.stdout)
        self.assertNotIn("Random", result.stdout)

    def test_llvm_reports_unmaterialized_targets_without_compiling(self):
        result = self.run_repl(":llvm\n(defn unused [x] x)\n:llvm unused\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("no evaluated cell", result.stdout)
        self.assertIn("unused: not compiled yet", result.stdout)
        self.assertNotIn("define ", result.stdout)

    def test_llvm_retains_source_initialization_and_preserves_live_values(self):
        result = self.run_repl("(def x 1)\n(set! x 9)\n:llvm x\n(println* x)\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("store i32 1, ptr @C1_x__I", result.stdout)
        self.assertTrue(result.stdout.endswith("9\n"), result.stdout)

    def test_llvm_lists_actual_polymorphic_instances(self):
        result = self.run_repl("(defn identity [x] x)\n(identity 1)\n(identity true)\n:llvm identity\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("(Fn [Int] Int)", result.stdout)
        self.assertIn("(Fn [Bool] Bool)", result.stdout)
        self.assertEqual(result.stdout.count("; source repl:1 revision 1"), 2)

    def test_llvm_retired_artifacts_do_not_survive_reset(self):
        result = self.run_repl("(def x 1)\n(println* x)\n:reset\n(def x 2)\n:llvm x\n:llvm\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("x: not compiled yet", result.stdout)
        self.assertIn("no evaluated cell", result.stdout)
        self.assertNotIn("store i32 1", result.stdout)

    def test_llvm_support_and_full_module_are_explicit(self):
        focused = self.run_repl("(def x 1)\n(defn read-x [] x)\n(read-x)\n:llvm read-x\n:q\n")
        dependencies = self.run_repl("(def x 1)\n(defn read-x [] x)\n(read-x)\n:llvm --deps read-x\n:q\n")
        complete = self.run_repl("(def x 1)\n(println* x)\n:llvm --full x\n:q\n")
        self.assertEqual(focused.stderr + dependencies.stderr + complete.stderr, "")
        self.assertNotIn("@C1_x__I = global", focused.stdout)
        self.assertIn("@C1_x__I = global", dependencies.stdout)
        self.assertIn("store i32 1, ptr @C1_x__I", dependencies.stdout)
        self.assertIn("; ModuleID = 'carp-jit-cell-", complete.stdout)
        self.assertIn("; source repl:1 revision 1", complete.stdout)
        self.assertIn("Random", complete.stdout)

    def test_llvm_ignores_auxiliary_inspection_publications(self):
        result = self.run_repl("[1 2]\n:inspect 1 0\n:llvm\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("; cell repl:1 revision 1", result.stdout)
        self.assertNotIn("; cell repl:inspect", result.stdout)

    def test_llvm_preserves_the_last_cell_after_failed_submission(self):
        result = self.run_repl("(println* 42)\n(no-such-function)\n:llvm\n:q\n")
        self.assertIn("resolve:", result.stderr)
        self.assertIn("; cell repl:1 revision 1", result.stdout)
        self.assertIn("i32 42", result.stdout)

    def test_llvm_rejects_source_arguments_without_execution(self):
        result = self.run_repl("(def x 1)\n(println* x)\n:llvm (do (set! x 100) x)\n(println* x)\n:q\n")
        self.assertIn("usage: :llvm", result.stderr)
        self.assertTrue(result.stdout.endswith("1\n"), result.stdout)
        self.assertNotIn("; LLVM artifact", result.stdout)

    def test_llvm_definition_revisions_follow_successful_edits(self):
        result = self.run_repl("(def x 1)\n(println* x)\n:edit 1\n(def x 2)\n(println* x)\n:llvm x\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("; source repl:1 revision 3", result.stdout)
        self.assertIn("generation 0", result.stdout)
        self.assertRegex(result.stdout, r"store i32 2, ptr @carp_session_resident\d+_x95__C1_x__I")
        self.assertNotIn("store i32 1", result.stdout)

    def test_documentation_at_a_parameter_declaration_uses_its_identity(self):
        with Terminal() as terminal:
            terminal.send(b"(fn [Int.inc] (Int.+ Int.inc 1))\x01")
            terminal.send(b"\x06" * len("(fn [Int.inc"))
            terminal.send(b"\x1bOP")
            terminal.until(b"Int.inc : Int")
            terminal.send(b"\x03")
            terminal.next_prompt()

    def test_type_annotations_do_not_query_the_value_namespace(self):
        with Terminal() as terminal:
            terminal.send(b"(let [a 42] (the a a))\x01")
            terminal.send(b"\x06" * len("(let [a 42] (the a"))
            terminal.send(b"\x1bOP")
            terminal.until(b"a : type parameter")
            self.assertNotIn(b"a : Int", terminal.buffer)
            terminal.send(b"\x03")
            terminal.next_prompt()

    def test_type_completion_and_documentation_use_type_identities(self):
        with Terminal() as terminal:
            terminal.send(b'(doc ToolType "type documentation")\r')
            terminal.next_prompt()
            terminal.send(b"(deftype ToolType [value Int])\r")
            terminal.next_prompt()
            terminal.send(b"(def ToolValue 42)\r")
            terminal.next_prompt()
            terminal.send(b"(the ToolT\t")
            terminal.displayed("(the ToolType")
            terminal.cursor_at(terminal.screen.row, 3 + len("(the ToolType"))
            terminal.send(b"\x1bOP")
            terminal.until(b"ToolType : type")
            terminal.until(b"type documentation")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.send(b"(the ToolV\t")
            terminal.read_for(.7)
            self.assertNotIn("(the ToolValue", terminal.screen.text())

    def test_builtin_type_completion_is_available_in_incomplete_annotations(self):
        with Terminal() as terminal:
            terminal.send(b"(the (Arr\t")
            terminal.displayed("(the (Array")
            terminal.cursor_at(terminal.screen.row, 3 + len("(the (Array"))
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.send(b"(the Dou\t")
            terminal.displayed("(the Double")
            terminal.cursor_at(terminal.screen.row, 3 + len("(the Double"))

    def test_type_completion_sees_uncommitted_type_declarations(self):
        with Terminal() as terminal:
            terminal.send(b"(do (deftype PendingType [value Int]) (the PendingT\t")
            terminal.displayed("(the PendingType")
            terminal.cursor_at(terminal.screen.row,
                               3 + len("(do (deftype PendingType [value Int]) (the PendingType"))

    def test_type_completion_hides_retired_generation_identities(self):
        with Terminal() as terminal:
            terminal.resize(24, 200)
            source = ("(do (deftype RevisionType [x Int]) "
                      "(sig earlier (Fn [RevisionType] RevisionType)) "
                      "(deftype RevisionType [y Bool]) (the RevisionT")
            terminal.send(source.encode() + b"\t")
            terminal.displayed("(the RevisionType")
            self.assertNotIn("--gen", terminal.screen.text())
            terminal.cursor_at(terminal.screen.row, 3 + len(source) + 3)

    def test_type_completion_includes_the_current_signature_parameters(self):
        with Terminal() as terminal:
            terminal.send(b"(sig polymorphic (Fn [element] elem\t")
            terminal.displayed("[element] element")

    def test_metadata_only_inputs_preserve_documentation(self):
        result = self.run_repl('(doc Described "first documentation")\n'
                               '(deftype Described [x Int])\n'
                               ':doc Described\n'
                               '(doc Described "updated documentation")\n'
                               ':doc Described\n:q\n')
        self.assertEqual(result.stderr, "")
        self.assertIn("first documentation", result.stdout)
        self.assertIn("updated documentation", result.stdout)

    def test_failed_nested_macro_preserves_verified_outer_scope(self):
        with Terminal() as terminal:
            terminal.send(b'(defmacro Broken [] (macro-error "broken"))\r')
            terminal.next_prompt()
            terminal.send(b"(fn [outer] (Broken outer))\x01")
            terminal.send(b"\x06" * len("(fn [outer] (Broken out"))
            terminal.send(b"\t")
            terminal.displayed("(Broken outer)")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_missing_macro_body_is_reported_before_submission(self):
        with Terminal() as terminal:
            terminal.send(b"(defmacro incomplete [x])")
            terminal.until(b"defmacro expects a name, parameter array, and body")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.result(b"(Int.+ 20 22)", b"42")
    def test_host_commands_and_embedded_source_have_distinct_contexts(self):
        with Terminal() as terminal:
            terminal.send(b":he\t")
            terminal.displayed(b":help")
            terminal.send(b"\r")
            terminal.next_prompt()
            terminal.send(b":type (let [embedded-local 41] (Int.inc embedded-lo\t")
            terminal.displayed(b"(Int.inc embedded-local")
            terminal.send(b"))\r")
            terminal.until(b"\x1b[?2004l")
            terminal.until(b"Int\r\n")
            terminal.until("λ> ".encode())
            terminal.send(b":doc Int.in\t")
            terminal.displayed(b":doc Int.inc")
            terminal.send(b"\r")
            terminal.until(b"increments an Int")
            terminal.until("λ> ".encode())
    def test_completion_uses_the_current_lexical_scope(self):
        with Terminal() as terminal:
            terminal.send(b"(let [lexical-local 41] (Int.inc lexical-lo\t")
            terminal.displayed(b"(Int.inc lexical-local")
            terminal.result(b"))", b"42")

    def test_documentation_distinguishes_a_local_named_if(self):
        with Terminal() as terminal:
            terminal.send(b"(let [if 41] (Int.inc if))\x02\x02\x1bOP")
            terminal.until(b"if : Int")
            terminal.result(b"\x05", b"42")

    def test_macro_parameter_completion_uses_compile_time_scope(self):
        with Terminal() as terminal:
            terminal.send(b"(defmacro identity [macro-argument] macro-arg\t")
            terminal.displayed(b"] macro-argument")
            terminal.send(b")\r")
            terminal.next_prompt()
            terminal.result(b"(identity 42)", b"42")

    def test_quoted_data_does_not_complete_lexical_bindings(self):
        with Terminal() as terminal:
            terminal.send(b"(let [quoted-local 41] (quote quoted-lo\t")
            terminal.until(b"quoted syntax")
            self.assertNotIn(b"] (quote quoted-local", terminal.raw)
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_a_local_shadows_the_identity_of_a_retained_result(self):
        with Terminal() as terminal:
            terminal.result(b"41", b"41")
            terminal.send(b"(let [_1 true] _1)\x02\x1bOP")
            terminal.until(b"_1 : Bool")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.result(b"(Int.inc _1)", b"42")

    def test_typing_and_cancel_survive_an_unbounded_macro_preview(self):
        with Terminal() as terminal:
            terminal.send(b"(defmacro spin [] (while true 0))\r")
            terminal.next_prompt()
            terminal.send(b"(spin)")
            terminal.displayed(b"(spin)")
            time.sleep(.03)
            started = time.monotonic()
            terminal.send(b" ")
            terminal.displayed(b"(spin) ")
            self.assertLess(time.monotonic() - started, .25)
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_automatic_analysis_requires_an_explicit_compile_time_read(self):
        with Terminal() as terminal:
            terminal.send(b'(defmacro preview-read [] (do (read-file "/no-such-preview-file") 42))\r')
            terminal.next_prompt()
            terminal.send(b"(preview-read)")
            terminal.until(b"compile-time effect requires an explicit query")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_replay_is_explicit_and_preserves_current_globals(self):
        result = self.run_repl('''(def counter 0)
(do (set! counter (Int.inc counter)) counter)
(defn unrelated [] 3)
counter
:replay 2
counter
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual([line for line in result.stdout.splitlines() if line.isdecimal()],
                         ["1", "1", "2", "2"])

    def test_edit_can_replace_a_declaration_with_an_expression(self):
        result = self.run_repl('''(defn old [] 3)
:edit 1
42
:defs
(old)
(Int.+ 20 22)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("resolve:", result.stderr)
        self.assertEqual(result.stdout.count("old :"), 1)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_declaration_removal_by_edit_keeps_dependents_atomic(self):
        result = self.run_repl('''(defn old [] 3)
(defn dependent [] (old))
(def counter 0)
(set! counter 7)
:edit 1
(do (IO.println "must-not-run") 42)
(old)
counter
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("resolve:", result.stderr)
        self.assertNotIn("must-not-run", result.stdout)
        self.assertTrue(result.stdout.endswith("3\n7\n"), result.stdout)

    def test_reset_cancels_the_selected_edit(self):
        result = self.run_repl('''(defn old [] 3)
:edit 1
:reset
42
:history
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("2 [ok]  42", result.stdout)

    def test_result_capacity_displays_and_releases_temporary_owners(self):
        closure = '(let [captured 40] (fn [x] (Int.+ captured x)))'
        result = self.run_repl("\n".join([
            *map(str, range(1, 34)), closure, ":results", ":inspect 33",
            ":drop 1", closure, "(@_33 2)", ":q", "",
        ]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "repl: no live result _33\n")
        self.assertEqual(result.stdout.count("<function> {captured: 40}\n"), 2)
        self.assertIn("_32 : Int", result.stdout)
        self.assertNotIn("_33 : Int", result.stdout)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_owned_callbacks_across_replacements_and_resets(self):
        source = []
        for iteration in range(3):
            source.extend([
                '(defn retained-version [] 1)',
                '[(String.copy "left") (String.copy "right")]',
                '(defn retained-version [] 2)',
                '[(String.copy "left") (String.copy "right")]',
                ':reset',
            ])
        result = self.run_repl("\n".join([*source, "(Int.+ 20 22)", ":q", ""]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count('[@"left" @"right"]'), 6, result.stdout)
        self.assertEqual(result.stdout.count("session reset"), 3)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_expansion_and_ownership_errors_leave_the_loop_usable(self):
        result = self.run_repl('''(defn consume [s] (String.length &s))
(let [owned (String.copy "hi") borrow &owned] (do (ignore (consume owned)) (String.length borrow)))
(Int.+ 20 22)
(defmacro broken [] (macro-error "intentional expansion failure"))
(broken)
(Int.+ 20 22)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ownership:", result.stderr)
        self.assertIn("borrow is used after its owner is moved", result.stderr)
        self.assertIn("expand:", result.stderr)
        self.assertIn("intentional expansion failure", result.stderr)
        self.assertEqual(result.stdout.count("42\n"), 2)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_undo_and_color_opt_out(self):
        with Terminal(color=False) as terminal:
            terminal.send(b"(Int.+ 20 22)3")
            terminal.displayed(b"(Int.+ 20 22)3")
            terminal.send(b"\x1f")
            terminal.displayed(b"(Int.+ 20 22)")
            terminal.result(b"", b"42")
            self.assertNotRegex(terminal.raw, rb"\x1b\[[0-9;]*m")

    def test_checking_a_definition_never_commits_it(self):
        with Terminal() as terminal:
            terminal.send(b"(defn unsubmitted [] 42)\x1bOQ")
            terminal.until(b"unsubmitted : (Fn [] Int)")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.send(b"(unsubmitted)\r")
            terminal.until(b"resolve:")
            terminal.until("λ> ".encode())
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_completion_docs_and_check_in_the_editor(self):
        with Terminal() as terminal:
            terminal.send(b"(Int.in\t")
            terminal.displayed(b"(Int.inc")
            terminal.send(b"\x1bOP")
            terminal.until(b"increments an Int")
            terminal.result(b" 41)", b"42")
            terminal.send(b"(do (IO.println \"not-run\") 17)\x1bOQ")
            terminal.until(b"\r\nInt")
            terminal.send(b"\x03")
            terminal.next_prompt()
            self.assertNotIn(b"\r\nnot-run\r\n", terminal.raw)

    def test_completion_replaces_the_whole_word_at_midpoint(self):
        with Terminal() as terminal:
            terminal.send(b"(Int.inx 41)\x01" + b"\x06" * 7 + b"\t")
            terminal.displayed(b"(Int.inc 41)")
            terminal.result(b"\x05", b"42")

    def test_highlighting_explicit_newline_and_force_submit(self):
        with Terminal() as terminal:
            terminal.send(b"(if true 42 0)")
            terminal.displayed(b"42 0)")
            terminal.until_style(b"\x1b[35m")
            terminal.until_style(b"\x1b[1;36m")
            terminal.send(b"\x0a")
            terminal.until("·> ".encode())
            self.assertNotIn(b"\r\n42\r\n", terminal.raw)
            terminal.result(b"", b"42")
            terminal.send(b"(Int.+ 1\x1b\r")
            terminal.until(b"parse:")
            terminal.until("λ> ".encode())
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_removal_requires_current_preview_and_removes_dependents(self):
        result = self.run_repl('''(def counter 0)
(defn base [x] (Int.+ x 1))
(defn dependent [x] (base x))
(set! counter 7)
:remove! 2
:remove 2
counter
:remove! 2
:remove 2
:remove! 2
:defs
counter
(dependent 2)
(Int.+ 20 22)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("preview this revision"), 2, result.stderr)
        self.assertIn("3  dependent", result.stdout)
        self.assertIn("inputs removed; expressions were not replayed", result.stdout)
        self.assertNotIn("native state reset", result.stdout)
        self.assertIn("counter : Int", result.stdout)
        self.assertNotIn("dependent :", result.stdout.split("inputs removed", 1)[1])
        self.assertIn("resolve:", result.stderr)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_inspection_navigates_owned_values_without_reexecution(self):
        result = self.run_repl('''(def counter 0)
(do (set! counter (Int.inc counter)) [[10 20] [30 40]])
:inspect 1 1 0
:inspect 1 9 0
:inspect 1 -1
:inspect 1 2147483648
:inspect 1 4294967296
counter
(deftype Point [x Int y Int])
(Point.init 7 8)
:inspect 3 x
:inspect 3 z
:drop 3
:inspect 3 x
(Int.+ 20 22)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("_1 1 0 : (Ref Int)\n30", result.stdout)
        self.assertIn("index out of bounds", result.stderr)
        self.assertIn("_3 x : (Ref Int)\n7", result.stdout)
        self.assertIn("nonnegative integer indices", result.stderr)
        self.assertIn("no field z in Point; fields: x y", result.stderr)
        self.assertIn("no live result _3", result.stderr)
        self.assertIn("\n1\n", result.stdout)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_failed_edit_is_not_an_active_removal_target(self):
        result = self.run_repl('''(defn kept [] 42)
:edit 1
(defn kept [] (Int.+ true 1))
:remove 2
(kept)
:edit 2
(defn kept [] 43)
:history
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("input 2 has no active definitions", result.stderr)
        self.assertIn("42\n", result.stdout)
        self.assertIn("1 [superseded, stale]", result.stdout)

    def test_closure_results_retain_callable_storage(self):
        result = self.run_repl('''(let [captured 40] (fn [x] (Int.+ captured x)))
:inspect 1
(@_1 2)
:drop 1
(Int.+ 20 22)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("_1 : (Fn [Int] Int)\n<function>", result.stdout)
        self.assertEqual(result.stdout.count("42\n"), 2)

    def test_inspection_is_bounded_on_unicode_boundaries(self):
        result = self.run_repl('"' + "λ" * 5000 + '"\n:inspect 1\n:q\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        inspection = result.stdout.split("_1 : String\n", 1)[1]
        self.assertIn("… truncated", inspection)
        self.assertLess(len(inspection), 4130)

    def test_inspection_reads_active_sum_payloads(self):
        result = self.run_repl("""(Maybe.Just [10 20])
:inspect 1 0 1
(the (Maybe (Array Int)) (Maybe.Nothing))
:inspect 2 0
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Maybe.Just", result.stdout)
        self.assertIn("_1 0 1 : (Ref Int)\n20", result.stdout)
        self.assertIn("Maybe.Nothing", result.stdout)
        self.assertIn("no field 0", result.stderr)

    def test_inspection_reads_closure_captures_without_moving_them(self):
        result = self.run_repl("""(let [secret [11 22]] (fn [x] (Int.+ x @(Array.unsafe-nth &secret 1))))
:inspect 1 secret 0
(@_1 20)
:drop 1
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("secret: [11 22]", result.stdout)
        self.assertIn("_1 secret 0 : (Ref Int)\n11", result.stdout)
        self.assertIn("\n42\n", result.stdout)

    def test_inspection_pages_large_values_without_reexecution(self):
        result = self.run_repl("""(def visits 0)
(do (set! visits (Int.inc visits)) (Array.repeat 1000000 &(fn [] 7)))
:inspect 1 --offset 999997 --count 3
_1
(Array.length _1)
visits
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("_1 : (Array Int)\n[7 7 7]", result.stdout)
        self.assertEqual(result.stdout.count("…]"), 2)
        self.assertIn("\n1000000\n", result.stdout)
        self.assertLess(len(result.stdout), 1000)
        self.assertTrue(result.stdout.endswith("1\n"), result.stdout)

    def test_inspection_preserves_padding_unit_fields_and_nested_strings(self):
        result = self.run_repl("""(deftype Packet [flag Bool unit () word Long data (Array String)])
(Packet.init true () 99l [(String.copy "a b") (String.copy "λ")])
:inspect 1 unit
:inspect 1 word
:inspect 1 data 1
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn('data: [@"a b" @"λ"]', result.stdout)
        self.assertIn("_1 unit : (Ref Unit)\n()", result.stdout)
        self.assertIn("_1 word : (Ref Long)\n99", result.stdout)
        self.assertIn("_1 data 1 : (Ref String)\nλ", result.stdout)

    def test_macro_declarations_are_classified_after_expansion(self):
        result = self.run_repl('''(defmacro make-answer [] `(do (defn answer [] 42) (defn other [] 7)))
(make-answer)
(answer)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("answer : (Fn [] Int)", result.stdout)
        self.assertIn("\n42\n", result.stdout)

    def test_mixed_macro_commits_declarations_and_runs_roots_once(self):
        result = self.run_repl('''(defmacro mixed [] `(do (defn from-mixed [] 41) (IO.println "macro-effect") (Int.inc (from-mixed))))
(mixed)
(Int.+ _1 1)
(defn unrelated-after-mixed [] 7)
(from-mixed)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count("macro-effect\n"), 1, result.stdout)
        self.assertIn("\n42\n43\n", result.stdout)
        self.assertTrue(result.stdout.endswith("41\n"), result.stdout)

    def test_failed_mixed_macro_preserves_definitions_and_live_values(self):
        result = self.run_repl('''(def counter 0)
(defmacro broken-mixed [] `(do (defn leaked-mixed [] 9) (IO.println "must-not-run") (Int.+ true 1)))
(set! counter 7)
(broken-mixed)
counter
(leaked-mixed)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("must-not-run", result.stdout)
        self.assertIn("infer:", result.stderr)
        self.assertIn("unknown binding leaked-mixed", result.stderr)
        self.assertTrue(result.stdout.endswith("7\n"), result.stdout)

    def test_mixed_macro_uses_one_expansion_for_generated_names(self):
        result = self.run_repl('''(defmacro fresh-mixed [] (let [name (gensym)] `(do (defn %name [] 42) (%name))))
(fresh-mixed)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_mixed_macro_check_does_not_execute_or_commit(self):
        with Terminal() as terminal:
            terminal.send(b'(defmacro checked-mixed [] `(do (defn checked-answer [] 42) (IO.println "must-not-run") (checked-answer)))\r')
            terminal.next_prompt()
            terminal.raw = b""
            terminal.send(b"(checked-mixed)\x1bOQ")
            terminal.until(b"checked-answer : (Fn [] Int)")
            self.assertNotIn(b"\r\nmust-not-run\r\n", terminal.raw)
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.send(b"(checked-answer)\r")
            terminal.until(b"unknown binding checked-answer")
            terminal.until("λ> ".encode())
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_mixed_macro_can_commit_types_functions_and_macros(self):
        result = self.run_repl('''(defmacro bundle [] `(do (deftype MixedBox [value Int]) (defn make-mixed-box [] (MixedBox.init 42)) (defmacro bundled-answer [] 43) (make-mixed-box)))
(bundle)
:defs
:inspect 1 value
(bundled-answer)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("MixedBox : type", result.stdout)
        self.assertIn("make-mixed-box : (Fn [] MixedBox)", result.stdout)
        self.assertIn("bundled-answer : macro", result.stdout)
        self.assertIn("_1 value : (Ref Int)\n42", result.stdout)
        self.assertTrue(result.stdout.endswith("43\n"), result.stdout)

    def test_top_level_sequences_support_mixed_macro_output(self):
        result = self.run_repl('''(defmacro sequenced [] `(do (defn from-sequence [] 42) (from-sequence)))
(do (sequenced))
(do (defn direct-sequence [] 43) (direct-sequence))
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("42\n43\n"), result.stdout)

    def test_failed_mixed_macro_native_publication_is_atomic(self):
        result = self.run_repl('''(def counter 0)
(defmacro absent-mixed [] `(do (register absent-generated (Fn [] Int) "metacarp_repl_missing_generated_symbol") (IO.println "must-not-run") (absent-generated)))
(set! counter 7)
(absent-mixed)
counter
:defs
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("jit:", result.stderr)
        self.assertNotIn("must-not-run", result.stdout)
        self.assertNotIn("absent-generated :", result.stdout)
        self.assertIn("\n7\n", result.stdout)

    def test_mixed_macro_history_edits_and_export_preserve_caller_source(self):
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory, "active.carp")
            removed = Path(directory, "removed.carp")
            result = self.run_repl(f'''(defmacro history-bundle [n] `(do (defn history-answer [] %n) (IO.println "export-effect") (history-answer)))
  (history-bundle 42)
:edit 2
  (history-bundle 43)
:export {active}
:edit 2
45
(history-answer)
:export {removed}
:q
''')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("export-effect\n"), 2, result.stdout)
            self.assertIn("unknown binding history-answer", result.stderr)
            exported = active.read_text()
            self.assertIn("\n  (history-bundle 43)\n", exported)
            self.assertNotIn("(history-bundle 42)", exported)
            self.assertEqual(exported.count("(defn history-answer"), 1)
            self.assertNotIn("(history-bundle 43)", removed.read_text())
            replay = self.run_repl(exported + "(history-answer)\n:q\n")
            self.assertEqual(replay.stderr, "")
            self.assertEqual(replay.stdout.count("export-effect\n"), 1, replay.stdout)
            self.assertTrue(replay.stdout.endswith("43\n43\n"), replay.stdout)

    def test_runtime_macro_can_use_live_results_and_return_an_owned_string(self):
        result = self.run_repl('''(defmacro passthrough [form] form)
[10 20]
(passthrough (Array.length _1))
"abc"
(passthrough _3)
:inspect 4
:results
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("\n2\n", result.stdout)
        self.assertIn("_4 : String\nabc\n", result.stdout)
        self.assertIn("_1 : (Array Int)", result.stdout)
        self.assertIn("_4 : String", result.stdout)

    def test_mixed_macro_preserves_module_scope_without_replaying_effects(self):
        result = self.run_repl('''(defmacro scoped-bundle [] `(defmodule ScopedBundle (private secret) (defn secret [] 41) (defn answer [] (secret)) (defn __repl_scope_0 [] 100) (IO.println "scoped-effect") (Int.inc (secret))))
(scoped-bundle)
(defn after-scoped [] 9)
(ScopedBundle.answer)
(ScopedBundle.__repl_scope_0)
:inspect 1
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count("scoped-effect\n"), 1, result.stdout)
        self.assertIn("\n42\n", result.stdout)
        self.assertIn("\n41\n100\n", result.stdout)
        self.assertTrue(result.stdout.endswith("_1 : Int\n42\n"), result.stdout)

    def test_mixed_macro_preserves_nested_module_imports_and_live_aliases(self):
        result = self.run_repl('''(defmodule MixedSource (defn answer [] 41))
(defmacro imported-bundle [] `(defmodule MixedImports (use MixedSource) (defn value [] (answer)) (defmodule Inner (IO.println "nested-effect") (Int.+ (Array.length _1) (MixedImports.value)))))
[10]
(imported-bundle)
(defn after-imports [] 0)
(MixedImports.value)
:inspect 2
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count("nested-effect\n"), 1, result.stdout)
        self.assertTrue(result.stdout.endswith("_2 : Int\n42\n"), result.stdout)

    def test_mixed_macro_mutates_native_globals_only_when_executed(self):
        result = self.run_repl('''(def counter 0)
(defmacro mutate-and-define [] `(do (defn after-mutation [] 42) (set! counter (Int.inc counter)) counter))
(set! counter 7)
(mutate-and-define)
(defn after-macro [] 9)
counter
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count("8\n"), 2, result.stdout)
        self.assertTrue(result.stdout.endswith("8\n"), result.stdout)

    def test_view_queries_refresh_bounds_and_source_between_results(self):
        result = self.run_repl('''(deftype Tag [value Int])
(defview show-tag [tag Tag] (=> (View.text) (View.title @"Tag") (View.content (fmt "tag=%d" @(Tag.value tag)))))
(Tag.init 17)
(Tag.init 29)
:inspect 1 --view show-tag
:inspect 2 --view show-tag --bytes 5
:inspect 1 --view missing
:inspect 1 --view show-tag
:reset
(Int.+ 20 22)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no applicable view missing", result.stderr)
        self.assertGreaterEqual(result.stdout.count("tag=17"), 3)
        self.assertIn("tag=2", result.stdout)
        self.assertTrue(result.stdout.endswith("42\n"))

    def test_defview_is_shared_with_notebook_views(self):
        result = self.run_repl('''(deftype Point [x Int y Int])
(defview coordinates [p Point] (=> (View.text) (View.title @"Coordinates") (View.content (fmt "point(%d, %d)" @(Point.x p) @(Point.y p)))))
(Point.init 3 7)
:inspect 1 --views
:inspect 1 --view coordinates
:inspect 1 --raw
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("point(3, 7)", result.stdout)
        self.assertIn("coordinates : Coordinates (text, 1)", result.stdout)
        self.assertIn("Point.init {x: 3, y: 7}", result.stdout)

    def test_views_use_specific_interface_dispatch(self):
        result = self.run_repl('''(defview integer-items [xs (Array Int)] (=> (View.text) (View.title @"Integers") (View.content @"specific")))
[1 2]
:inspect 1 --views
:inspect 1 --view integer-items
:inspect 1 --raw
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("specific", result.stdout)
        self.assertIn("integer-items : Integers (text, 1)", result.stdout)
        self.assertIn("_1 : (Array Int)\n[1 2]", result.stdout)

    def test_source_aware_view_receives_bounds_and_reset_preserves_api(self):
        result = self.run_repl('''(deftype Badge [value Int])
(defview show-badge [badge Badge] (=> (View.text) (View.title @"Badge") (View.value-content (fn [value request] (fmt "badge=%d count=%d" @(Badge.value value) @(ViewRequest.count request))))))
(Badge.init 42)
:inspect 1 --count 2
:inspect 1 --raw
:reset
(View.request @"" 0 1 2 3)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("badge=42 count=32", result.stdout)
        self.assertIn("badge=42 count=2", result.stdout)
        self.assertIn("Badge.init {value: 42}", result.stdout)

    def run_repl(self, source):
        return subprocess.run(
            [*COMMAND, "--core", CORE], input=source, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            env={**os.environ, "METACARP_HISTORY": ""},
        )

    def test_history_survives_restart_without_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "state" / "history"
            with Terminal("--history", str(history)) as terminal:
                terminal.result(b'(Int.+ 40\r2)', b'42')
            self.assertTrue(history.is_file())
            self.assertEqual(history.stat().st_mode & 0o777, 0o600)
            with Terminal("--history", str(history)) as terminal:
                self.assertNotIn(b"42\r\n", terminal.buffer)
                terminal.result(b"\x1b[A", b"42")

    def test_history_and_cursor_respond_before_enter(self):
        with Terminal() as terminal:
            terminal.send(b"\r")
            terminal.next_prompt()
            terminal.result(b"(Int.+ 40 2)", b"42")
            terminal.send(b"\x1b[A")
            terminal.displayed(b"(Int.+ 40 2)")
            self.assertFalse(termios.tcgetattr(terminal.master)[3] & termios.ICANON)
            terminal.send(b"\x1b[D\x1b[D\x04" + b"3")
            terminal.displayed(b"3)")
            terminal.send(b"\r")
            terminal.until(b"43\r\n")
            terminal.until("λ> ".encode())

    def test_definitions_replacement_and_error_recovery(self):
        result = self.run_repl("""(defn twice [x] (Int.* 2 x))
(twice 21)
(defn twice [x] (Int.+ true x))
(twice 21)
(defn twice [x] (Int.* 3 x))
(twice 21)
(Int.+ 1]
(twice 14)
(no-such-function 1)
(twice 2)
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = [line for line in result.stdout.splitlines() if line.isdecimal()]
        self.assertEqual(values, ["42", "42", "63", "42", "6"], result.stdout)
        self.assertIn("infer:", result.stderr)
        self.assertIn("parse:", result.stderr)
        self.assertIn("resolve:", result.stderr)
        self.assertIn("repl:", result.stderr)
        self.assertNotIn("λ>", result.stdout)

    def test_globals_queries_and_reset(self):
        result = self.run_repl("""(def counter 0)
counter
(set! counter 7)
counter
:type (do (set! counter 99) counter)
counter
:doc Int.+
:complete Int.+
:defs
:reset
counter
(Int.+ 2 3)
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0\n7\nInt\n7\n", result.stdout)
        self.assertIn("adds two integers.", result.stdout)
        self.assertIn("counter : Int", result.stdout)
        self.assertIn("session reset", result.stdout)
        self.assertTrue(result.stdout.endswith("5\n"), result.stdout)
        self.assertIn("resolve:", result.stderr)
        self.assertNotIn("jit:", result.stderr)

    def test_ownership_expansion_and_code_queries_do_not_execute(self):
        result = self.run_repl('''(def counter 0)
(defn greet [name] (String.append name "!"))
(defmacro answer [] `(Int.+ 40 2))
:ownership greet
:expand-1 (answer)
:c-render (do (set! counter 99) counter)
counter
:llvm counter
counter
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("ownership greet", result.stdout)
        self.assertIn("Int.+", result.stdout)
        self.assertIn("#include", result.stdout)
        self.assertIn("store i32 0, ptr @C7_counter__I", result.stdout)
        self.assertTrue(result.stdout.endswith("0\n"), result.stdout[-200:])

    def test_multiline_macro_and_owned_result(self):
        result = self.run_repl("""(defmacro twice [x] `(Int.+ %x %x))
(twice
  21)
(String.append "Grüße " "🐟")
:history
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("42\n", result.stdout)
        self.assertIn("Grüße 🐟", result.stdout)
        self.assertIn("(twice\n  21)", result.stdout)

    def test_capturing_closures_across_cells(self):
        result = self.run_repl('''(let [base 40 f (fn [x] (Int.+ base x))] (f 2))
(let [base 41 f (fn [x] (Int.+ base x))] (f 1))
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "42\n42\n")

    def test_replacement_preserves_unrelated_globals_and_historical_values(self):
        result=self.run_repl('''(def counter 0)
(defn base [] 41)
(defn answer [] (Int.inc (base)))
(set! counter 7)
[10 20]
(fn [] (base))
(answer)
(defn base [] 42)
(answer)
counter
:inspect 1
(@_2)
:q
''')
        self.assertEqual(result.stderr,'')
        self.assertNotIn('native state reset',result.stdout)
        self.assertIn('\n43\n7\n_1 : (Array Int)\n[10 20]\n41\n',result.stdout)

    def test_global_replacement_refreshes_dependents_and_preserves_unrelated_state(self):
        result=self.run_repl('''(def unrelated 0)
(def base 10)
(defn answer [] (Int.inc base))
(set! unrelated 7)
(answer)
(def base 20)
(answer)
unrelated
:q
''')
        self.assertEqual(result.stderr,'')
        self.assertNotIn('native state reset',result.stdout)
        self.assertTrue(result.stdout.endswith('21\n7\n'),result.stdout)

    def test_replacement_preserves_native_template_static_state(self):
        result=self.run_repl('''(deftemplate stable-counter (Fn [] Int) "int $NAME(void)" "$DECL { static int calls; return ++calls; }")
(defn base [] 41)
(stable-counter)
(base)
(defn base [] 42)
(base)
(stable-counter)
:q
''')
        self.assertEqual(result.stderr,'')
        self.assertNotIn('native state reset',result.stdout)
        self.assertTrue(result.stdout.endswith('42\n2\n'),result.stdout)

    def test_failed_mixed_publication_restores_active_native_versions(self):
        result=self.run_repl('''(register missing-target (Fn [] Int) "metacarp_missing_invalidation_target")
(defn base [] 41)
(defn answer [] (base))
[10 20]
(answer)
(do (defn base [] 42) (missing-target))
(answer)
:inspect 1
:q
''')
        self.assertIn('jit:',result.stderr)
        self.assertTrue(result.stdout.endswith('41\n_1 : (Array Int)\n[10 20]\n'),result.stdout)

    def test_inspection_uses_current_binding_without_compiling_old_generations(self):
        result=self.run_repl('''(defn answer [] 41)
(answer)
(defn answer [] 42)
:llvm answer
(answer)
(IO.println "LATEST-IR")
:llvm answer
:q
''')
        self.assertEqual(result.stderr,'')
        self.assertIn('not compiled yet',result.stdout)
        latest=result.stdout.split('LATEST-IR\n')[-1]
        self.assertIn('ret i32 42',latest)
        self.assertNotIn('ret i32 41',latest)

    def test_edit_preserves_unchanged_initializers_in_the_same_input(self):
        result = self.run_repl('''(do (def counter 0) (defn answer [] 41))
(set! counter 7)
(answer)
:edit 1
(do (def counter 0) (defn answer [] 42))
(answer)
counter
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertNotIn("native state reset", result.stdout)
        self.assertTrue(result.stdout.endswith("42\n7\n"), result.stdout)

    def test_native_revision_names_cannot_collide_with_source_names(self):
        result = self.run_repl('''(defn resident3_target [] 99)
(defn target [] 1)
(resident3_target)
(target)
(defn target [] 2)
(target)
(resident3_target)
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("2\n99\n"), result.stdout)

    def test_repeating_a_value_declaration_initializes_that_binding_again(self):
        result = self.run_repl('''(def counter 0)
(set! counter 7)
(def counter 0)
counter
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("0\n"), result.stdout)

    def test_revision_follows_concrete_interface_implementation_edges(self):
        result = self.run_repl('''(definterface revised-score (Fn [(Ref a)] Int))
(deftype RevisedRecord [value Int])
(defn record-score [value] @(RevisedRecord.value value))
(implements revised-score record-score)
(defn read-score [value] (revised-score value))
(RevisedRecord.init 41)
(read-score _1)
(defn record-score [value] (Int.inc @(RevisedRecord.value value)))
(read-score _1)
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertNotIn("native state reset", result.stdout)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_revision_updates_all_polymorphic_instances(self):
        result = self.run_repl('''(def calls 0)
(defn marked [value] (do (set! calls (Int.inc calls)) value))
(marked 10)
(marked @"old")
calls
(defn marked [value] (do (set! calls (Int.+ calls 10)) value))
(marked 20)
(marked @"new")
calls
:inspect 2
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertIn("\n2\n", result.stdout)
        self.assertTrue(result.stdout.endswith("22\n_2 : String\nold\n"), result.stdout)

    def test_revisions_can_switch_between_functions_and_function_values(self):
        result = self.run_repl('''(defn selected [] 41)
(defn call-selected [] (selected))
(call-selected)
(def selected (fn [] 42))
(call-selected)
(defn selected [] 43)
(call-selected)
:q
''')
        self.assertEqual(result.stderr, "")
        values = re.findall(r"^\d+$", result.stdout, re.M)
        self.assertEqual(values, ["41", "42", "43"], result.stdout)
        self.assertNotIn("native state reset", result.stdout)

    def test_signature_revisions_preserve_historical_function_types(self):
        result = self.run_repl('''(defn answer [] 41)
(defn call-answer [] (answer))
(fn [] (answer))
(call-answer)
(defn answer [] @"new")
(call-answer)
(@_1)
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertNotIn("native state reset", result.stdout)
        self.assertTrue(result.stdout.endswith("new\n41\n"), result.stdout)

    def test_global_revisions_keep_storage_used_by_historical_closures(self):
        result = self.run_repl('''(def xs [1 2])
(fn [] (Array.length &xs))
(def xs [10 20 30])
(Array.length &xs)
(@_1)
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertNotIn("native state reset", result.stdout)
        self.assertTrue(result.stdout.endswith("3\n2\n"), result.stdout)

    def test_revision_initializes_affected_globals_once(self):
        result = self.run_repl('''(def calls 0)
(defn base [] 41)
(def value (do (set! calls (Int.inc calls)) (base)))
value
calls
(defn base [] 42)
value
calls
calls
:q
''')
        self.assertEqual(result.stderr, "")
        values = re.findall(r"^\d+$", result.stdout, re.M)
        self.assertEqual(values, ["41", "1", "42", "2", "2"], result.stdout)

    def test_view_queries_follow_redefined_provider_dependencies(self):
        result = self.run_repl('''(deftype RevisedBadge [])
(defn badge-label [] @"before")
(defview revised-badge [value RevisedBadge] (do (ignore value) (=> (View.text) (View.content (badge-label)))))
(RevisedBadge.init)
:inspect 1
:browse 1
(defn badge-label [] @"after")
:inspect 1
:browse 1
:q
''')
        self.assertEqual(result.stderr, "")
        self.assertNotIn("native state reset", result.stdout)
        self.assertEqual(re.findall(r"^(before|after)$", result.stdout, re.M),
                         ["before", "before", "before", "after", "after"], result.stdout)

    def test_owned_results_survive_additions_and_replacement(self):
        result = self.run_repl('''(Int.+ 40 2)
(Int.+ _ 1)
(String.copy "kept")
:inspect 3
(defn plus-one [x] (Int.+ x 1))
(plus-one _1)
:results
(defn plus-one [x] (Int.+ x 2))
:inspect 3
(plus-one 40)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("42\n43\nkept\n_3 : String\nkept", result.stdout)
        self.assertIn("_1 : Int", result.stdout)
        self.assertIn("_3 : String", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("native state reset", result.stdout)
        self.assertTrue(result.stdout.endswith("42\n"), result.stdout)

    def test_result_release_preserves_older_values(self):
        result = self.run_repl('''[1 2 3]
(Int.+ 20 22)
:drop 2
:inspect 1
:inspect 2
(Array.length _1)
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("_1 : (Array Int)", result.stdout)
        self.assertIn("no live result _2", result.stderr)
        self.assertTrue(result.stdout.endswith("3\n"), result.stdout)

    def test_edit_history_tracks_dependents_and_exports_active_source(self):
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory) / "active.carp"
            transcript = Path(directory) / "transcript.carp"
            result = self.run_repl(f'''(defn answer [] 41)
(defn next-answer [] (Int.+ (answer) 1))
(next-answer)
:edit 1
(defn answer [] 42)
:history
:export {active}
:export-transcript {transcript}
(next-answer)
:q
''')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertIn("2 [ok, stale]", result.stdout)
            self.assertIn("3 [ok, stale]", result.stdout)
            self.assertTrue(result.stdout.endswith("43\n"), result.stdout)
            self.assertNotIn("41", active.read_text())
            self.assertNotIn("(next-answer)\n", active.read_text())
            replay = self.run_repl(active.read_text() + "\n(next-answer)\n:q\n")
            self.assertEqual(replay.stderr, "")
            self.assertTrue(replay.stdout.endswith("43\n"), replay.stdout)
            self.assertIn("; input 3:", transcript.read_text())

    def test_edit_seeds_the_terminal_without_submitting(self):
        with Terminal() as terminal:
            terminal.send(b"(defn answer [] 41)\r")
            terminal.until(b"answer :")
            terminal.until("λ> ".encode())
            terminal.send(b":edit 1\r")
            terminal.until("λ[1]> ".encode())
            terminal.displayed(b"(defn answer [] 41)")
            terminal.send(b"\x01\x0b(defn answer [] 42)\r")
            terminal.until(b"answer :")
            terminal.until("λ> ".encode())
            terminal.result(b"(answer)", b"42")

    def test_mixed_input_commits_then_executes_once(self):
        result = self.run_repl("(def hidden-value 42) hidden-value\n:defs\n:q\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "42\nhidden-value : Int\n")

    def test_failed_mixed_preparation_keeps_current_state_and_does_not_execute(self):
        result = self.run_repl('''(def counter 0)
(set! counter 7)
(defn bad [] 42) (do (IO.println "must-not-run") (Int.+ true 1))
counter
(register absent (Fn [] Int) "metacarp_repl_missing_native_symbol") (do (IO.println "must-not-run") (absent))
counter
:defs
:q
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("must-not-run", result.stdout)
        self.assertNotIn("bad :", result.stdout)
        self.assertNotIn("absent :", result.stdout)
        self.assertEqual(result.stdout.count("7\n"), 2, result.stdout)
        self.assertIn("infer:", result.stderr)
        self.assertIn("jit:", result.stderr)

    def test_final_line_and_unfinished_eof(self):
        result = self.run_repl("(Int.+ 20 22)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "42\n")
        result = self.run_repl("(Int.+ 20")
        self.assertEqual(result.returncode, 1)
        self.assertIn("parse:", result.stderr)

    def test_comments_and_indented_commands(self):
        result = self.run_repl("""(defn answer [] 41) ; first definition
(defn answer [] 42) ; replacement
  :type (answer)
(answer)
  :q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("Int\n42\n", result.stdout)
        self.assertEqual(result.stdout.count("answer :"), 2)

    def test_dependent_error_uses_its_committed_source(self):
        result = self.run_repl("""(defn choose [] 1)
(defn uses-choose []
  (Int.+ 1 (choose)))
(defn choose [] true)
(uses-choose)
:q
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("infer:", result.stderr)
        self.assertIn("repl:2:2:", result.stderr)
        self.assertTrue(result.stdout.endswith("2\n"), result.stdout)

    def test_help_and_bad_options_do_not_load_core(self):
        result = subprocess.run([*COMMAND, "--help"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn(":help", result.stdout)
        result = subprocess.run([*COMMAND, "--core"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("needs a directory", result.stderr)

    def test_browse_navigation_keeps_parent_state_and_returns_to_editing(self):
        with Terminal() as terminal:
            terminal.resize(10, 80)
            terminal.send(b"[10 20 30 40 50 60 70 80 90 100]\r")
            terminal.next_prompt()
            terminal.send(b":browse 1\r")
            terminal.displayed("[gtRawFor]  depth 1", timeout=15)
            terminal.send(b"\t")
            terminal.displayed("[array-items]  depth 1")
            terminal.send(b"\x1b[B\x1b[B\r")
            terminal.displayed("depth 2")
            terminal.displayed("30")
            terminal.send(b"\x1b[D")
            terminal.displayed("[array-items]  depth 1")
            terminal.displayed("> 2 | 30")
            terminal.send(b" ")
            terminal.displayed("offset 6")
            terminal.resize(8, 60)
            terminal.read_for(.25)
            terminal.displayed("offset 6")
            terminal.raw = b""
            terminal.read_for(.35)
            self.assertEqual(terminal.raw, b"", "an idle view must not repaint")
            terminal.send(b"q")
            terminal.next_prompt()
            terminal.send(b"(+ 20 22)\r")
            terminal.until(b"42\r\n")
            terminal.until("λ> ".encode())

    def test_browse_switches_declared_views_and_ctrl_c_closes(self):
        with Terminal(color=False) as terminal:
            terminal.resize(10, 80)
            terminal.send(b'"hello"\r')
            terminal.next_prompt()
            terminal.send(b":browse 1\r")
            terminal.displayed("[gtRawFor]", timeout=15)
            terminal.send(b"\t")
            terminal.displayed("[string-value]")
            terminal.send(b"\t")
            terminal.displayed("[string-bytes]")
            terminal.displayed("104")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.send(b":drop 1\r")
            terminal.next_prompt()

    def test_browse_renders_native_bitmap_pixels(self):
        with Terminal() as terminal:
            terminal.resize(10, 80)
            terminal.send(b"(deftype BrowseSwatch [])\r")
            terminal.next_prompt()
            terminal.send(b'(defview swatch [x BrowseSwatch] (do (ignore x) (=> (View.bitmap) (View.extent 1 1) (View.pixels [255b 0b 0b 255b]))))\r')
            terminal.next_prompt()
            terminal.send(b"(BrowseSwatch.init)\r")
            terminal.next_prompt()
            terminal.raw = b""
            terminal.send(b":browse 1\r")
            terminal.displayed("1 x 1 RGBA", timeout=15)
            terminal.until_style(b"\x1b[38;2;255;0;0m")
            terminal.send(b"q")
            terminal.next_prompt()

    def test_browse_accepts_native_selectors(self):
        result = self.run_repl("[10 20 30]\n:browse 1 1\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("Int : Raw", result.stdout)
        self.assertIn("\n20\n", result.stdout)

    def test_browse_pipe_is_bounded_plain_output(self):
        result = self.run_repl("[10 20 30]\n:browse 1\n:q\n")
        self.assertEqual(result.stderr, "")
        self.assertIn("gtRawFor", result.stdout)
        self.assertRegex(result.stdout, r">\s*0\s*\|\s*Int\s*\|\s*10")
        self.assertNotIn("\x1b", result.stdout)

    def test_long_command_output_pages_and_quit_preserves_the_repl(self):
        with Terminal() as terminal:
            terminal.resize(8, 60)
            terminal.send(b":help\r")
            terminal.until(b"lines 1-")
            terminal.displayed("q close")
            idle = len(terminal.raw)
            terminal.read_for(.25)
            self.assertEqual(len(terminal.raw), idle, "idle paging must not repaint")
            before = len(terminal.raw)
            terminal.send(b" ")
            terminal.read_for(.15)
            self.assertNotIn(b"\x1b[J", terminal.raw[before:])
            terminal.send(b"q")
            terminal.until("λ> ".encode())
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_repeated_resize_keeps_editing_and_paging_usable(self):
        with Terminal() as terminal:
            for cycle in range(8):
                terminal.send(b"x")
                terminal.displayed("λ> x")
                terminal.resize(8 + cycle % 3, 60 + cycle % 5)
                terminal.read_for(.03)
                terminal.send(b"\x03")
                terminal.next_prompt()
                terminal.send(b":help\r")
                terminal.until(b"lines 1-")
                terminal.resize(9 + cycle % 3, 62 + cycle % 5)
                terminal.read_for(.03)
                terminal.send(b"q")
                terminal.until("λ> ".encode())
            terminal.result(b"(Int.+ 20 22)", b"42")

    def test_pager_search_and_cancel_return_to_editing(self):
        with Terminal() as terminal:
            terminal.resize(8, 60)
            terminal.send(b":help\r")
            terminal.until(b"lines 1-")
            terminal.send(b"/History\r")
            terminal.displayed("History persists")
            terminal.resize(12, 42)
            terminal.displayed("History persists")
            terminal.send(b"\x03")
            terminal.until("λ> ".encode())
            terminal.result(b"(Int.+ 6 7)", b"13")

    def test_termination_during_paging_restores_terminal_mode(self):
        with Terminal() as terminal:
            terminal.resize(8, 60)
            terminal.send(b":help\r")
            terminal.until(b"lines 1-")
            os.kill(terminal.child, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                child, status = os.waitpid(terminal.child, os.WNOHANG)
                if child:
                    terminal.child = None
                    self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGTERM)
                    break
                time.sleep(.05)
            self.assertIsNone(terminal.child, "REPL did not terminate during paging")
            self.assertEqual(termios.tcgetattr(terminal.master), terminal.initial_terminal)

    def test_pipe_output_never_enters_the_pager(self):
        result = self.run_repl(":help\n:q\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)
        self.assertNotIn("lines 1-", result.stdout)
        self.assertNotIn("\x1b", result.stdout)

    def test_up_down_and_draft_restore(self):
        with Terminal() as terminal:
            terminal.result(b"(Int.+ 40 2)", b"42")
            terminal.result(b"\x1b[A", b"42")
            terminal.result(b"(Int.+ 10 2)", b"12")
            terminal.result(b"\x1b[A\x1b[A\x1b[B", b"12")
            terminal.result(b"(Int.+ 20 1)\x1b[A\x1b[B", b"21")

    def test_cursor_delete_kill_yank_and_search(self):
        with Terminal() as terminal:
            terminal.result(b"(Int.+ 40 1)\x1b[D\x1b[D\x1b[3~2\x05", b"42")
            terminal.result(b"(Int.+ 40 2)\x1b[H(do \x1b[F)", b"42")
            terminal.result(b"(Int.+ 40 12\x7f\x7f2)", b"42")
            terminal.result(b"(Int.+ 20 1)\x01\x0b\x19\x05", b"21")
            terminal.result(b"(Int.+ 10 nope\x17" + b"2)", b"12")
            terminal.result(b"\x1240\x05", b"42")

    def test_continuation_prompt_keeps_indentation_and_history_source(self):
        with Terminal(color=False) as terminal:
            terminal.send(b"(Int.+ 40\r")
            terminal.until("·>   ".encode())
            terminal.result(b"2)", b"42")
            terminal.result(b"\x1b[A", b"42")

    def test_enter_aligns_open_binding_vectors_from_reader_structure(self):
        with Terminal(color=False) as terminal:
            terminal.send(b"(let [x 40\r")
            terminal.until(("·> " + " " * 6).encode())
            terminal.send(b"y 2]\r")
            terminal.until("·>   ".encode())
            terminal.result(b"(Int.+ x y))", b"42")

    def test_enter_does_not_add_whitespace_to_multiline_strings(self):
        with Terminal(color=False) as terminal:
            terminal.send(b'(String.copy "hello\r')
            terminal.until("·> ".encode())
            terminal.result(b'world")', b"hello\r\nworld")

    def test_function_declaration_style_survives_incomplete_body_edits(self):
        with Terminal() as terminal:
            edits = [b"(defn x [] ", b"(", b"let", b"\x7f" * 3, b"\x7f"]
            sources = ["(defn x [] ", "(defn x [] (", "(defn x [] (let",
                       "(defn x [] (", "(defn x [] "]
            for edit, source in zip(edits, sources):
                with self.subTest(source=source):
                    terminal.send(edit)
                    terminal.displayed(source.rstrip())
                    terminal.cursor_at(terminal.screen.row, 3 + len(source))
                    # Include the final semantic reply, not just provisional paint.
                    terminal.read_for(.7)
                    row, column = terminal.screen.find("x []")
                    self.assertEqual(terminal.screen.cells[row][column][1],
                                     (False, False, 34))

    def test_incomplete_function_declaration_does_not_style_its_parameter_as_a_function(self):
        with Terminal() as terminal:
            for edit in [b"(defn x [x] ", b"(let"]:
                terminal.send(edit)
                terminal.displayed("x [x]")
                terminal.read_for(.7)
                row, column = terminal.screen.find("x [x]")
                self.assertEqual(terminal.screen.cells[row][column][1],
                                 (False, False, 34))
                self.assertEqual(terminal.screen.cells[row][column + 3][1],
                                 (False, True, None))

    def test_quoted_function_declaration_names_have_no_semantic_function_style(self):
        with Terminal() as terminal:
            terminal.send(b"(quote (defn x [] ")
            terminal.displayed("x []")
            terminal.read_for(.7)
            row, column = terminal.screen.find("x []")
            self.assertEqual(terminal.screen.cells[row][column][1],
                             (False, False, None))

    def test_analysis_updates_preserve_untouched_binding_styles_and_visible_text(self):
        with Terminal() as terminal:
            source = "(fn [x] (Int.+ x 1))"
            terminal.send(source.encode())
            terminal.displayed(source)
            row, start_column = terminal.screen.find(source)
            column = start_column + source.rindex("x")
            terminal.wait_screen(
                lambda: terminal.screen.cells[row][column][1] != (False, False, None),
                "the compiler's parameter style",
            )
            style = terminal.screen.cells[row][column][1]
            start = len(terminal.raw)
            terminal.send(b" ")
            deadline = time.monotonic() + .7
            while time.monotonic() < deadline:
                if select.select([terminal.master], [], [], .02)[0]:
                    chunk = os.read(terminal.master, 65536)
                    terminal.raw += chunk
                    terminal.buffer += chunk
                    terminal.screen.feed(chunk)
                    self.assertIn(source, terminal.screen.line(row))
                    self.assertEqual(terminal.screen.cells[row][column][1], style)
            self.assertNotIn(b"\x1b[K", terminal.raw[start:])
            self.assertNotIn(b"\x1b[J", terminal.raw[start:])

    def test_editing_repaints_changed_rows_without_clearing_the_frame(self):
        with Terminal(color=False) as terminal:
            terminal.send(b"(Int.+ 40")
            terminal.displayed(b"(Int.+ 40")
            start = len(terminal.raw)
            terminal.send(b" ")
            row, start_column = terminal.screen.find("(Int.+ 40")
            terminal.cursor_at(row, start_column + len("(Int.+ 40 "))
            update = terminal.raw[start:]
            self.assertNotIn(b"\x1b[J", update)
            self.assertNotIn(b"\x1b[2J", update)
            self.assertNotIn(b"\x1b[K", update)
            terminal.result(b"2)", b"42")

    def test_editing_a_continuation_leaves_the_first_row_in_place(self):
        with Terminal(color=False) as terminal:
            terminal.send(b"(Int.+\r")
            terminal.until("·>   ".encode())
            start = len(terminal.raw)
            terminal.send(b"40")
            terminal.displayed(("·> " + " " * 2 + "40").encode())
            self.assertNotIn(b"(Int.+", terminal.raw[start:])
            terminal.result(b" 2)", b"42")

    def test_scrolled_multiline_input_keeps_source_and_edits_without_frame_clears(self):
        with Terminal(color=False) as terminal:
            terminal.resize(6, 12)
            source = b"(Int.+ 40\n" + b"\n" * 20 + b"  2)"
            terminal.send(b"\x1b[200~" + source + b"\x1b[201~")
            terminal.until("·>   2)".encode())
            start = len(terminal.raw)
            terminal.result(b"\x1b[D\x1b[D\x1b[3~3\x05", b"43")
            self.assertNotIn(b"\x1b[J", terminal.raw[start:])

    def test_unicode_edit_and_multiline_history(self):
        with Terminal() as terminal:
            keys = '(String.copy "Grüße 🐟")'.encode()
            keys += b"\x1b[D" * 3 + b"\x1b[3~" + "🦀".encode() + b"\x05"
            terminal.result(keys, "Grüße 🦀".encode())
            terminal.result(b"(Int.+ 40\r2)", b"42")
            terminal.result(b"\x1b[A", b"42")

    def test_bracketed_paste_waits_for_enter(self):
        with Terminal() as terminal:
            terminal.send(b"\x1b[200~(Int.+ 40\n2)\n\x1b[201~")
            while select.select([terminal.master], [], [], 0.2)[0]:
                terminal.buffer += os.read(terminal.master, 65536)
            self.assertNotIn(b"42\r\n", terminal.buffer)
            self.assertNotIn(b"parse:", terminal.buffer)
            terminal.result(b"", b"42")

    def test_resize_preserves_the_edited_buffer(self):
        with Terminal() as terminal:
            terminal.send(b"(Int.+ 40 2)")
            terminal.displayed(b"2)")
            terminal.resize(12, 24)
            terminal.result(b"\x1b[D\x1b[D\x1b[3~3\x05", b"43")

    def test_continue_and_resize_signals_preserve_the_edited_buffer(self):
        with Terminal() as terminal:
            terminal.send(b"(Int.+ 40 2)")
            terminal.displayed("λ> (Int.+ 40 2)")
            for _ in range(6):
                os.kill(terminal.child, signal.SIGCONT)
                terminal.resize(12, 80)
                terminal.read_for(.04)
            terminal.result(b"", b"42")

    def test_termination_restores_terminal_mode(self):
        with Terminal() as terminal:
            os.kill(terminal.child, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                child, status = os.waitpid(terminal.child, os.WNOHANG)
                if child:
                    terminal.child = None
                    self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGTERM)
                    break
                time.sleep(0.05)
            self.assertIsNone(terminal.child, "REPL did not terminate")
            self.assertEqual(termios.tcgetattr(terminal.master), terminal.initial_terminal)

    def test_prompt_cancel_abort_and_eof(self):
        with Terminal() as terminal:
            terminal.send(b"(Int.+ 1\r123")
            terminal.displayed(b"123")
            terminal.send(b"\x03")
            terminal.next_prompt()
            terminal.result(b"(Int.+ 40 2)", b"42")
            terminal.send(b"(\r:abort\r")
            terminal.displayed(b":abort")
            terminal.next_prompt()
            terminal.send(b"\x04")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                # macOS tty restoration waits for pending PTY output to drain.
                if select.select([terminal.master], [], [], 0.05)[0]:
                    try:
                        terminal.buffer += os.read(terminal.master, 65536)
                    except OSError as error:
                        if error.errno != errno.EIO:
                            raise
                child, status = os.waitpid(terminal.child, os.WNOHANG)
                if child:
                    terminal.child = None
                    self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                    break
                time.sleep(0.05)
            self.assertIsNone(terminal.child, "REPL did not exit on Ctrl-D")
            self.assertEqual(termios.tcgetattr(terminal.master), terminal.initial_terminal)


if __name__ == "__main__":
    unittest.main()
