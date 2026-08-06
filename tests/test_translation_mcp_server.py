import importlib.util
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = PROJECT_ROOT / "skills" / "translate-patch-notes" / "mcp_server"
SERVER_PATH = MCP_ROOT / "server.py"


def _load_server_module():
    if not SERVER_PATH.exists():
        return None

    sys.path.insert(0, str(MCP_ROOT))
    specification = importlib.util.spec_from_file_location(
        "translation_mcp_server",
        SERVER_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Unable to load translation MCP server")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


# Describe: project-scoped FastMCP server registration
class TranslationMcpServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_registers_the_seven_translation_tools(self) -> None:
        # Given the project translation MCP module
        server_module = _load_server_module()
        self.assertIsNotNone(server_module)

        # When FastMCP reports its available tools
        tools = await server_module.mcp.list_tools()

        # Then Codex receives the complete translation workflow
        self.assertEqual(
            {
                "prepare_locale",
                "record_terminology",
                "submit_locale",
                "audit_locale",
                "compare_locale",
                "translation_status",
                "finalize_translations",
            },
            {tool.name for tool in tools},
        )

    async def test_tools_expose_descriptions_for_agent_assisted_use(self) -> None:
        # Given the registered server tools
        server_module = _load_server_module()

        # When their MCP metadata is inspected
        tools = await server_module.mcp.list_tools()

        # Then every tool tells Codex what operation it performs
        self.assertTrue(all(tool.description for tool in tools))


if __name__ == "__main__":
    unittest.main()
