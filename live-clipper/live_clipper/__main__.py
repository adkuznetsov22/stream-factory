import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from .app import App
from .config import settings

# streamlink is installed next to the interpreter; make it reachable without activating the venv
os.environ["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"


def main():
    p = argparse.ArgumentParser(prog="live_clipper")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="discover streams, detect moments, render and publish clips")
    t = sub.add_parser("test", help="record one channel and render a clip from the last seconds")
    t.add_argument("login")
    t.add_argument("--record", type=int, default=60)
    t.add_argument("--clip", type=int, default=30)
    sub.add_parser("discover", help="print streams that would be recorded")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for name in ("httpx", "httpx2", "huggingface_hub"):
        logging.getLogger(name).setLevel(logging.WARNING)
    app = App(settings)
    if args.cmd == "run":
        asyncio.run(app.run())
    elif args.cmd == "test":
        asyncio.run(app.test(args.login, args.record, args.clip))
    else:
        from .discovery import discover

        async def show():
            for st in await discover(app.http, settings):
                print(f"{st.login:20} {st.viewers:>7}  {st.game}  {st.title[:60]}")

        asyncio.run(show())


if __name__ == "__main__":
    main()
