@echo off
rem Xenoform MCP server for Claude, Cursor, Grok Bot and other AI clients. See docs\mcp.md.
rem   Xenoform-MCP.bat          stdio (what Claude Desktop / Cursor launch)
rem   Xenoform-MCP.bat --http   streamable HTTP on http://127.0.0.1:47319/mcp
setlocal
cd /d "%~dp0"
rem XENO_DESK picks the desk; unset, the server finds the one on 47330, then 47317.
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo Xenoform's .venv was not found at "%~dp0.venv".
  echo Run install.bat first, then start Xenoform-MCP.bat again.
  exit /b 1
)
"%PY%" -c "import mcp" 2>nul || "%PY%" -m pip install -q "mcp>=2.3,<3"
"%PY%" -m xenoform.mcp %*
