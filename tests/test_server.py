import os
import pytest
import tempfile
import hashlib
from src.text_editor.server import TextEditorServer, calculate_id, generate_diff_preview


class TestTextEditorServer:
    @pytest.fixture
    def server(self):
        """Create a TextEditorServer instance for testing."""
        server = TextEditorServer()
        server.max_edit_lines = 200
        return server

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write(content)
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def empty_temp_file(self):
        """Create an empty temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def get_tool_fn(self, server, tool_name):
        """Helper to get the tool function from the server."""
        tools_dict = server.mcp._tool_manager._tools
        return tools_dict[tool_name].fn

    @pytest.mark.asyncio
    async def test_set_file_valid(self, server, temp_file):
        """Test setting a valid file path."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        result = await set_file_fn(temp_file)
        assert "File set to:" in result
        assert temp_file in result
        assert server.current_file_path == temp_file

    @pytest.mark.asyncio
    async def test_set_file_invalid(self, server):
        """Test setting a non-existent file path."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        non_existent_path = "/path/to/nonexistent/file.txt"
        result = await set_file_fn(non_existent_path)
        assert "Error: File not found" in result
        assert server.current_file_path is None

    @pytest.mark.asyncio
    async def test_read_no_file_set(self, server):
        """Test getting text when no file is set."""
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(1, 10)
        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_read_entire_file(self, server, temp_file):
        """Test getting the entire content of a file."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(1, 5)
        assert "lines" in result

    async def test_read_line_range(self, server, temp_file):
        """Test getting a specific range of lines from a file."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(2, 4)
        assert "lines" in result
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 4)
        assert "status" in select_result
        assert "id" in select_result
        expected_id = calculate_id("Line 2\nLine 3\nLine 4\n", 2, 4)
        assert expected_id == select_result["id"]

    @pytest.mark.asyncio
    async def test_read_only_end_line(self, server, temp_file):
        """Test getting text with only end line specified."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(1, 2)
        assert "lines" in result
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(1, 2)
        expected_id = calculate_id("Line 1\nLine 2\n", 1, 2)
        assert expected_id == select_result["id"]

    @pytest.mark.asyncio
    async def test_read_invalid_range(self, server, temp_file):
        """Test getting text with an invalid line range."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        read_fn = self.get_tool_fn(server, "read")
        result = await read_fn(4, 2)
        assert "error" in result
        assert "start cannot be greater than end" in result["error"]
        result = await read_fn(0, 3)
        assert "error" in result
        assert "start must be at least 1" in result["error"]

    def test_calculate_id_function(self):
        """Test the calculate_id function directly."""
        text = "Some test content"
        id_no_range = calculate_id(text)
        expected = hashlib.sha256(text.encode()).hexdigest()[:2]
        assert id_no_range == expected
        id_with_range = calculate_id(text, 1, 3)
        assert id_with_range.startswith("L1-3-")
        assert id_with_range.endswith(expected)

    @pytest.mark.asyncio
    async def test_read_large_file(self, server):
        """Test getting text from a file larger than MAX_EDIT_LINES lines."""
        more_than_max_lines = server.max_edit_lines + 10
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(more_than_max_lines):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(large_file_path)
            read_fn = self.get_tool_fn(server, "read")
            result = await read_fn(1, more_than_max_lines)
            assert "lines" in result
            select_fn = self.get_tool_fn(server, "select")
            result = await select_fn(1, more_than_max_lines)
            assert "error" in result
            assert (
                f"Cannot select more than {server.max_edit_lines} lines at once"
                in result["error"]
            )
            result = await select_fn(5, 15)
            assert "status" in result
            assert "id" in result
            result = await read_fn(5, server.max_edit_lines + 10)
            assert "lines" in result
        finally:
            if os.path.exists(large_file_path):
                os.unlink(large_file_path)

    @pytest.mark.asyncio
    async def test_new_file(self, server, empty_temp_file):
        """Test new_file functionality."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(empty_temp_file)
        new_file_fn = self.get_tool_fn(server, "new_file")
        result = await new_file_fn(empty_temp_file)
        assert result["status"] == "success"
        assert "id" in result
        result = await new_file_fn(empty_temp_file)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_file(self, server):
        """Test delete_file tool."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("Test content to delete")
            temp_path = f.name
        try:
            delete_file_fn = self.get_tool_fn(server, "delete_file")
            result = await delete_file_fn()
            assert "error" in result
            assert "No file path is set" in result["error"]
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(temp_path)
            result = await delete_file_fn()
            assert result["status"] == "success"
            assert "successfully deleted" in result["message"]
            assert temp_path in result["message"]
            assert not os.path.exists(temp_path)
            assert server.current_file_path is None
            result = await set_file_fn(temp_path)
            assert "Error: File not found" in result
            assert server.current_file_path is None
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_delete_file_permission_error(self, server, monkeypatch):
        """Test delete_file with permission error."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("Test content")
            temp_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(temp_path)

            def mock_remove(path):
                raise PermissionError("Permission denied")

            monkeypatch.setattr(os, "remove", mock_remove)
            delete_file_fn = self.get_tool_fn(server, "delete_file")
            result = await delete_file_fn()
            assert "error" in result
            assert "Permission denied" in result["error"]
            assert server.current_file_path == temp_path
        finally:
            monkeypatch.undo()
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_find_line_no_file_set(self, server):
        """Test find_line with no file set."""
        find_line_fn = self.get_tool_fn(server, "find_line")
        result = await find_line_fn(search_text="Line")
        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_find_line_basic(self, server, temp_file):
        """Test basic find_line functionality."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        find_line_fn = self.get_tool_fn(server, "find_line")
        result = await find_line_fn(search_text="Line")
        assert "status" in result
        assert result["status"] == "success"
        assert "matches" in result
        assert "total_matches" in result
        assert result["total_matches"] == 5
        for match in result["matches"]:
            assert "line_number" in match
            assert "id" in match
            assert "text" in match
            assert f"Line {match['line_number']}" in match["text"]
        line_numbers = [match["line_number"] for match in result["matches"]]
        assert line_numbers == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_find_line_specific_match(self, server, temp_file):
        """Test find_line with a specific search term."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        find_line_fn = self.get_tool_fn(server, "find_line")
        result = await find_line_fn(search_text="Line 3")
        assert result["status"] == "success"
        assert result["total_matches"] == 1
        assert len(result["matches"]) == 1
        assert result["matches"][0]["line_number"] == 3
        assert "Line 3" in result["matches"][0]["text"]

    @pytest.mark.asyncio
    async def test_find_line_no_matches(self, server, temp_file):
        """Test find_line with a search term that doesn't exist."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        find_line_fn = self.get_tool_fn(server, "find_line")
        result = await find_line_fn(search_text="NonExistentTerm")
        assert result["status"] == "success"
        assert result["total_matches"] == 0
        assert len(result["matches"]) == 0

    @pytest.mark.asyncio
    async def test_find_line_file_read_error(self, server, temp_file, monkeypatch):
        """Test find_line with a file read error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)

        def mock_open(*args, **kwargs):
            raise IOError("Mock file read error")

        monkeypatch.setattr("builtins.open", mock_open)
        find_line_fn = self.get_tool_fn(server, "find_line")
        result = await find_line_fn(search_text="Line")
        assert "error" in result
        assert "Error searching file" in result["error"]
        assert "Mock file read error" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_no_file_set(self, server):
        """Test overwrite when no file is set."""
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "error" in result
        assert "No file path is set" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_basic(self, server, temp_file):
        """Test basic overwrite functionality."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 4)
        assert select_result["status"] == "success"
        assert "id" in select_result
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        new_lines = {"lines": ["New Line 2", "New Line 3", "New Line 4"]}
        result = await overwrite_fn(new_lines=new_lines)
        assert "status" in result
        assert result["status"] == "preview"
        assert "Changes ready to apply" in result["message"]
        decide_fn = self.get_tool_fn(server, "decide")
        decide_result = await decide_fn(decision="accept")
        assert decide_result["status"] == "success"
        assert "Changes applied successfully" in decide_result["message"]
        with open(temp_file, "r") as f:
            file_content = f.read()
        expected_content = "Line 1\nNew Line 2\nNew Line 3\nNew Line 4\nLine 5\n"
        assert file_content == expected_content

    @pytest.mark.asyncio
    async def test_select_invalid_range(self, server, temp_file):
        """Test select with invalid line ranges."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        result = await select_fn(start=0, end=2)
        assert "error" in result
        assert "start must be at least 1" in result["error"]
        result = await select_fn(start=1, end=10)
        assert "end" in result
        assert result["end"] == 5
        result = await select_fn(start=4, end=2)
        assert "error" in result
        assert "start cannot be greater than end" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_id_verification_failed(self, server, temp_file):
        """Test overwrite with incorrect ID (content verification failure)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        with open(temp_file, "w") as f:
            f.write(
                "Modified Line 1\nModified Line 2\nModified Line 3\nModified Line 4\nModified Line 5\n"
            )
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "error" in result
        assert "id verification failed" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_different_line_count(self, server, temp_file):
        """Test overwrite with different line count (more or fewer lines)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        new_lines = {"lines": ["New Line 2", "Extra Line", "New Line 3"]}
        result = await overwrite_fn(new_lines=new_lines)
        assert result["status"] == "preview"
        decide_fn = self.get_tool_fn(server, "decide")
        decide_result = await decide_fn(decision="accept")
        assert decide_result["status"] == "success"
        with open(temp_file, "r") as f:
            file_content = f.read()
        expected_content = (
            "Line 1\nNew Line 2\nExtra Line\nNew Line 3\nLine 4\nLine 5\n"
        )
        assert file_content == expected_content
        select_result = await select_fn(1, 6)
        assert select_result["status"] == "success"
        new_content = "Single Line\n"
        result = await overwrite_fn(new_lines={"lines": ["Single Line"]})
        assert result["status"] == "preview"
        decide_result = await decide_fn(decision="accept")
        assert decide_result["status"] == "success"
        with open(temp_file, "r") as f:
            file_content = f.read()
        assert file_content == "Single Line\n"

    @pytest.mark.asyncio
    async def test_overwrite_empty_text(self, server, temp_file):
        """Test overwrite with empty text (effectively removing lines)."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": []})
        assert result["status"] == "preview"
        decide_fn = self.get_tool_fn(server, "decide")
        decide_result = await decide_fn(decision="accept")
        assert decide_result["status"] == "success"
        with open(temp_file, "r") as f:
            file_content = f.read()
        expected_content = "Line 1\nLine 4\nLine 5\n"
        assert file_content == expected_content

    @pytest.mark.asyncio
    async def test_select_max_lines_exceeded(self, server, temp_file):
        """Test select with a range exceeding max_edit_lines."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        more_than_max_lines = server.max_edit_lines + 10
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            for i in range(more_than_max_lines):
                f.write(f"Line {i + 1}\n")
            large_file_path = f.name
        try:
            await set_file_fn(large_file_path)
            select_fn = self.get_tool_fn(server, "select")
            result = await select_fn(start=1, end=server.max_edit_lines + 1)
            assert "error" in result
            assert (
                f"Cannot select more than {server.max_edit_lines} lines at once"
                in result["error"]
            )
        finally:
            if os.path.exists(large_file_path):
                os.unlink(large_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_file_read_error(self, server, temp_file, monkeypatch):
        """Test overwrite with file read error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        original_open = open

        def mock_open_read(*args, **kwargs):
            if args[1] == "r":
                raise IOError("Mock file read error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_read)
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "error" in result
        assert "Error reading file" in result["error"]
        assert "Mock file read error" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_file_write_error(self, server, temp_file, monkeypatch):
        """Test overwrite with file write error."""
        set_file_fn = self.get_tool_fn(server, "set_file")
        await set_file_fn(temp_file)
        select_fn = self.get_tool_fn(server, "select")
        select_result = await select_fn(2, 3)
        assert select_result["status"] == "success"
        original_open = open
        open_calls = [0]

        def mock_open_write(*args, **kwargs):
            if args[1] == "w":
                raise IOError("Mock file write error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open_write)
        overwrite_fn = self.get_tool_fn(server, "overwrite")
        result = await overwrite_fn(new_lines={"lines": ["New content"]})
        assert "status" in result
        assert result["status"] == "preview"
        decide_fn = self.get_tool_fn(server, "decide")
        decide_result = await decide_fn(decision="accept")
        assert "error" in decide_result
        assert "Error writing to file" in decide_result["error"]
        assert "Mock file write error" in decide_result["error"]

    @pytest.mark.asyncio
    async def test_overwrite_newline_handling(self, server):
        """Test newline handling in overwrite (appends newline when needed)."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3")
            temp_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(temp_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(2, 2)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            result = await overwrite_fn(new_lines={"lines": ["New Line 2"]})
            assert result["status"] == "preview"
            decide_fn = self.get_tool_fn(server, "decide")
            decide_result = await decide_fn(decision="accept")
            assert decide_result["status"] == "success"
            with open(temp_path, "r") as f:
                file_content = f.read()
            expected_content = "Line 1\nNew Line 2\nLine 3"
            assert file_content == expected_content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_overwrite_python_syntax_check_success(self, server):
        """Test Python syntax checking in overwrite succeeds with valid Python code."""
        valid_python_content = (
            "def hello():\n    print('Hello, world!')\n\nresult = hello()\n"
        )
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(valid_python_content)
            py_file_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(py_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 4)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_content = {
                "lines": [
                    "def greeting(name):",
                    "    return f'Hello, {name}!'",
                    "",
                    "result = greeting('World')",
                ]
            }
            result = await overwrite_fn(new_lines=new_content)
            assert result["status"] == "preview"
            decide_fn = self.get_tool_fn(server, "decide")
            decide_result = await decide_fn(decision="accept")
            assert decide_result["status"] == "success"
            assert "Changes applied successfully" in decide_result["message"]
            with open(py_file_path, "r") as f:
                file_content = f.read()
            expected_content = "def greeting(name):\n    return f'Hello, {name}!'\n\nresult = greeting('World')\n"
            assert file_content == expected_content
        finally:
            if os.path.exists(py_file_path):
                os.unlink(py_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_python_syntax_check_failure(self, server):
        """Test Python syntax checking in overwrite fails with invalid Python code."""
        valid_python_content = (
            "def hello():\n    print('Hello, world!')\n\nresult = hello()\n"
        )
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as f:
            f.write(valid_python_content)
            py_file_path = f.name
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(py_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 4)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_python = {
                "lines": [
                    "def broken_function(:",
                    "    print('Missing parenthesis'",
                    "",
                    "result = broken_function()",
                ]
            }
            result = await overwrite_fn(new_lines=invalid_python)
            assert "error" in result
            assert "Python syntax error:" in result["error"]
            with open(py_file_path, "r") as f:
                file_content = f.read()
            assert file_content == valid_python_content
        finally:
            if os.path.exists(py_file_path):
                os.unlink(py_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_javascript_syntax_check_success(self, server, monkeypatch):
        """Test JavaScript syntax checking in overwrite succeeds with valid JS code."""
        valid_js_content = "function hello() {\n  return 'Hello, world!';\n}\n\nconst result = hello();\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(valid_js_content)
            js_file_path = f.name

        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 0
                    self.stderr = ""
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(js_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 5)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_lines = {
                "lines": [
                    "function greeting(name) {",
                    "  return `Hello, ${name}!`;",
                    "}",
                    "",
                    "const result = greeting('World');",
                ]
            }
            result = await overwrite_fn(new_lines=new_lines)
            assert result["status"] == "preview"
            decide_fn = self.get_tool_fn(server, "decide")
            decide_result = await decide_fn(decision="accept")
            assert decide_result["status"] == "success"
            assert "Changes applied successfully" in decide_result["message"]
            with open(js_file_path, "r") as f:
                file_content = f.read()
            expected_content = "function greeting(name) {\n  return `Hello, ${name}!`;\n}\n\nconst result = greeting('World');\n"
            assert file_content == expected_content
        finally:
            if os.path.exists(js_file_path):
                os.unlink(js_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_javascript_syntax_check_failure(self, server, monkeypatch):
        """Test JavaScript syntax checking in overwrite fails with invalid JS code."""
        valid_js_content = "function hello() {\n  return 'Hello, world!';\n}\n\nconst result = hello();\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".js", delete=False) as f:
            f.write(valid_js_content)
            js_file_path = f.name

        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 1
                    self.stderr = "SyntaxError: Unexpected token (1:19)"
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(js_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 5)
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_js = {
                "lines": [
                    "function broken() {",
                    "  return 'Missing closing bracket;",
                    "}",
                    "",
                    "const result = broken();",
                ]
            }
            result = await overwrite_fn(new_lines=invalid_js)
            assert "error" in result
            assert "JavaScript syntax error:" in result["error"]
            with open(js_file_path, "r") as f:
                file_content = f.read()
            assert file_content == valid_js_content
        finally:
            if os.path.exists(js_file_path):
                os.unlink(js_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_jsx_syntax_check_success(self, server, monkeypatch):
        """Test JSX syntax checking in overwrite succeeds with valid React/JSX code."""
        valid_jsx_content = "import React from 'react';\n\nfunction HelloWorld() {\n  return <div>Hello, world!</div>;\n}\n\nexport default HelloWorld;\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsx", delete=False) as f:
            f.write(valid_jsx_content)
            jsx_file_path = f.name

        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 0
                    self.stderr = ""
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(jsx_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 7)
            assert select_result["status"] == "success"
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            new_jsx_content = {
                "lines": [
                    "import React from 'react';",
                    "",
                    "function Greeting({ name }) {",
                    "  return <div>Hello, {name}!</div>;",
                    "}",
                    "",
                    "export default Greeting;",
                ]
            }
            result = await overwrite_fn(new_lines=new_jsx_content)
            assert result["status"] == "preview"
            decide_fn = self.get_tool_fn(server, "decide")
            decide_result = await decide_fn(decision="accept")
            assert decide_result["status"] == "success"
            assert "Changes applied successfully" in decide_result["message"]
            with open(jsx_file_path, "r") as f:
                file_content = f.read()
            expected_content = "import React from 'react';\n\nfunction Greeting({ name }) {\n  return <div>Hello, {name}!</div>;\n}\n\nexport default Greeting;\n"
            assert file_content == expected_content
        finally:
            if os.path.exists(jsx_file_path):
                os.unlink(jsx_file_path)

    @pytest.mark.asyncio
    async def test_overwrite_jsx_syntax_check_failure(self, server, monkeypatch):
        """Test JSX syntax checking in overwrite fails with invalid React/JSX code."""
        valid_jsx_content = "import React from 'react';\n\nfunction HelloWorld() {\n  return <div>Hello, world!</div>;\n}\n\nexport default HelloWorld;\n"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsx", delete=False) as f:
            f.write(valid_jsx_content)
            jsx_file_path = f.name

        def mock_subprocess_run(*args, **kwargs):
            class MockCompletedProcess:
                def __init__(self):
                    self.returncode = 1
                    self.stderr = "SyntaxError: Unexpected token (4:10)"
                    self.stdout = ""

            return MockCompletedProcess()

        monkeypatch.setattr("subprocess.run", mock_subprocess_run)
        try:
            set_file_fn = self.get_tool_fn(server, "set_file")
            await set_file_fn(jsx_file_path)
            select_fn = self.get_tool_fn(server, "select")
            select_result = await select_fn(1, 7)
            overwrite_fn = self.get_tool_fn(server, "overwrite")
            invalid_jsx = {
                "lines": [
                    "import React from 'react';",
                    "",
                    "function BrokenComponent() {",
                    "  return <div>Missing closing tag<div>;",
                    "}",
                    "",
                    "export default BrokenComponent;",
                ]
            }
            result = await overwrite_fn(new_lines=invalid_jsx)
            assert "error" in result
            assert "JavaScript syntax error:" in result["error"]
            with open(jsx_file_path, "r") as f:
                file_content = f.read()
            assert file_content == valid_jsx_content
        finally:
            if os.path.exists(jsx_file_path):
                os.unlink(jsx_file_path)

    @pytest.mark.asyncio
    async def test_generate_diff_preview(self):
        """Test the generate_diff_preview function directly."""
        original_lines = ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5"]
        modified_lines = [
            "Line 1",
            "Modified Line 2",
            "New Line",
            "Line 3",
            "Line 4",
            "Line 5",
        ]

        # Testing replacement in the middle of the file
        result = generate_diff_preview(original_lines, modified_lines, 2, 3)

        # Verify the result contains the expected diff_lines key
        assert "diff_lines" in result

        # Get and examine the content of diff_lines
        diff_lines_list = result["diff_lines"]

        # The diff_lines should be a list of tuples, let's check its structure
        # First verify we have the expected number of elements
        assert len(diff_lines_list) > 0

        # Check that we have context lines before the change
        # The first element should be the context line with line number 1
        assert any(item for item in diff_lines_list if item[0] == 1)

        # Check for removed lines with minus prefix
        assert any(item for item in diff_lines_list if item[0] == "-2")
        assert any(item for item in diff_lines_list if item[0] == "-3")

        # Check for added lines with plus prefix
        # There should be one entry containing the modified content
        added_lines = [
            item
            for item in diff_lines_list
            if isinstance(item[0], str) and item[0].startswith("+")
        ]
        assert len(added_lines) > 0

        # Verify context after the change (line 4 and 5)
        assert any(item for item in diff_lines_list if item[0] == 4)
        assert any(item for item in diff_lines_list if item[0] == 5)
