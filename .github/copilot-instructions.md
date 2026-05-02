# Copilot Instructions

## Project Guidelines
- When verifying backend changes, run pytest in the backend project only and exclude backup directories; backup test copies can cause duplicate collection and import errors.
- Use the backend project root directly for validation commands; do not prepend an extra backend directory when running Ruff, MyPy, or pytest.