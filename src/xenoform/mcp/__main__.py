"""python -m xenoform.mcp [--http] [--port 47319] [--desk URL]"""

import argparse

from xenoform.mcp_server import serve


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m xenoform.mcp", description="Xenoform MCP server (stdio by default).")
    parser.add_argument("--http", action="store_true", help="Streamable HTTP on 127.0.0.1 instead of stdio.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47319)
    parser.add_argument("--desk", default="", help="Desk URL. Defaults to XENO_DESK, else the desk answering on 47330 then 47317.")
    args = parser.parse_args(argv)
    try:
        serve("streamable-http" if args.http else "stdio", host=args.host, port=args.port, desk=args.desk or None)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
