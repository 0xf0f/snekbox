import logging
import unittest
from textwrap import dedent

from snekbox.nsjail import MEM_MAX, NsJail


class NsJailTests(unittest.TestCase):
    def setUp(self):
        super().setUp()

        self.nsjail = NsJail()
        self.nsjail.DEBUG = False
        self.logger = logging.getLogger("snekbox.nsjail")

    def test_print_returns_0(self):
        result = self.nsjail.python3("print('test')")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "test\n")
        self.assertEqual(result.stderr, None)

    def test_timeout_returns_137(self):
        code = dedent("""
            while True:
                pass
        """).strip()

        with self.assertLogs(self.logger) as log:
            result = self.nsjail.python3(code)

        self.assertEqual(result.returncode, 137)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, None)
        self.assertIn("run time >= time limit", "\n".join(log.output))

    def test_memory_returns_137(self):
        # Add a kilobyte just to be safe.
        code = dedent(f"""
            x = ' ' * {MEM_MAX + 1000}
        """).strip()

        result = self.nsjail.python3(code)
        self.assertEqual(result.returncode, 137)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, None)

    def test_subprocess_resource_unavailable(self):
        code = dedent("""
            import subprocess
            print(subprocess.check_output('kill -9 6', shell=True).decode())
        """).strip()

        result = self.nsjail.python3(code)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Resource temporarily unavailable", result.stdout)
        self.assertEqual(result.stderr, None)

    def test_read_only_file_system(self):
        code = dedent("""
            open('hello', 'w').write('world')
        """).strip()

        result = self.nsjail.python3(code)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Read-only file system", result.stdout)
        self.assertEqual(result.stderr, None)

    def test_forkbomb_resource_unavailable(self):
        code = dedent("""
            import os
            while 1:
                os.fork()
        """).strip()

        result = self.nsjail.python3(code)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Resource temporarily unavailable", result.stdout)
        self.assertEqual(result.stderr, None)

    def test_sigsegv_returns_139(self):  # In honour of Juan.
        code = dedent("""
            import ctypes
            ctypes.string_at(0)
        """).strip()

        result = self.nsjail.python3(code)
        self.assertEqual(result.returncode, 139)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, None)

    def test_null_byte_value_error(self):
        result = self.nsjail.python3("\0")
        self.assertEqual(result.returncode, None)
        self.assertEqual(result.stdout, "ValueError: embedded null byte")
        self.assertEqual(result.stderr, None)

    def test_log_parser(self):
        log_lines = (
            "[D][2019-06-22T20:07:00+0000][16] void foo::bar()():100 This is a debug message.",
            "[I][2019-06-22T20:07:48+0000] pid=20 ([STANDALONE MODE]) "
            "exited with status: 2, (PIDs left: 0)",
            "[W][2019-06-22T20:06:04+0000][14] void cmdline::logParams(nsjconf_t*)():250 "
            "Process will be UID/EUID=0 in the global user namespace, and will have user "
            "root-level access to files",
            "[W][2019-06-22T20:07:00+0000][16] void foo::bar()():100 This is a warning!",
            "[E][2019-06-22T20:07:00+0000][16] bool "
            "cmdline::setupArgv(nsjconf_t*, int, char**, int)():316 No command-line provided",
            "[F][2019-06-22T20:07:00+0000][16] int main(int, char**)():204 "
            "Couldn't parse cmdline options",
            "Invalid Line"
        )

        with self.assertLogs(self.logger, logging.DEBUG) as log:
            self.nsjail._parse_log(log_lines)

        self.assertIn("DEBUG:snekbox.nsjail:This is a debug message.", log.output)
        self.assertIn("ERROR:snekbox.nsjail:Couldn't parse cmdline options", log.output)
        self.assertIn("ERROR:snekbox.nsjail:No command-line provided", log.output)
        self.assertIn("WARNING:snekbox.nsjail:Failed to parse log line 'Invalid Line'", log.output)
        self.assertIn("WARNING:snekbox.nsjail:This is a warning!", log.output)
        self.assertIn(
            "INFO:snekbox.nsjail:pid=20 ([STANDALONE MODE]) exited with status: 2, (PIDs left: 0)",
            log.output
        )
