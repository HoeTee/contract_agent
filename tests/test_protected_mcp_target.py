import unittest

from mcp_service.client.client import resolve_stdio_target


class ProtectedMcpTargetTests(unittest.TestCase):
    def test_module_target_uses_current_runtime_executable(self) -> None:
        command, arguments = resolve_stdio_target(
            "module:mcp_service.server.server",
            executable="/app/loader",
        )
        self.assertEqual(command, "/app/loader")
        self.assertEqual(arguments, ["-m", "mcp_service.server.server"])

    def test_empty_module_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "module name"):
            resolve_stdio_target("module:", executable="/app/loader")


if __name__ == "__main__":
    unittest.main()
