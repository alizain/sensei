"""Entry point for `uvx --from sensei kura` or `python -m sensei.kura`."""

from .server import kura

if __name__ == "__main__":
	kura.run()
