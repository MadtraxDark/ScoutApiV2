"""Contract: entrypoint must not recursively chown Camoufox profiles."""

from pathlib import Path


def test_docker_entrypoint_no_recursive_chown() -> None:
    text = Path("docker-entrypoint.sh").read_text(encoding="utf-8")
    code_lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "chown -R" not in code
    assert "CAMOUFOX_CHOWN_PROFILES" in text
    assert "CAMOUFOX_PURGE_DISPOSABLE_CACHE" in text
    assert "cache2" in text
