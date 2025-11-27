"""Entry point for `uvx --from sensei scout` or `python -m sensei.scout`."""

from .server import scout

if __name__ == "__main__":
	scout.run()
