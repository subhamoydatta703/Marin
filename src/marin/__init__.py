def main() -> None:
    import runpy
    from pathlib import Path

    cli = Path(__file__).resolve().parent.parent / "app.py"
    runpy.run_path(str(cli), run_name="__main__")
