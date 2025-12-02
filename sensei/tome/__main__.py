"""Entry point for `uvx --from sensei tome` or `python -m sensei.tome`."""

from .server import tome

if __name__ == "__main__":
    tome.run()
