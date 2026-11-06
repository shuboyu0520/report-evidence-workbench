from pathlib import Path

from app.reader_view import reader_html


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "docs" / "reader.html"
    output.write_text(reader_html(), encoding="utf8")
