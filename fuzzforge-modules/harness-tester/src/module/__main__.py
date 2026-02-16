"""Harness tester module entrypoint."""

from fuzzforge_modules_sdk.api import logs

from module import HarnessTesterModule


def main() -> None:
    """Run the harness tester module."""
    logs.configure()
    module = HarnessTesterModule()
    module.main()


if __name__ == "__main__":
    main()
