"""``python -m jarvis_agent``: configure logging, then serve the app with uvicorn.

Logging starts before uvicorn, and uvicorn gets ``log_config=None``, so its own lines
(server started, access log) use the same format and files from the first line on.
"""

import argparse

import uvicorn

from jarvis_agent import logs
from jarvis_agent.runtime import start_logging


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m jarvis_agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    start_logging()
    try:
        uvicorn.run("jarvis_agent.main:app", host=args.host, port=args.port, log_config=None)
    finally:
        logs.shutdown()


if __name__ == "__main__":
    main()
