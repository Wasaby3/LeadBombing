from .server import create_app, run_server

__all__ = ['create_app', 'run_server', 'main']


def main() -> None:
    """`leadbombing`: start the local leads app and open it in the browser."""
    run_server()
