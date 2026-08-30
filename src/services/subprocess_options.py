import subprocess


def hidden_window_options() -> dict[str, int]:
    """Return subprocess options that suppress child console windows on Windows."""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": creation_flags} if creation_flags else {}
