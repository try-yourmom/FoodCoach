from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_frontend_renders_login_form_without_exceptions():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "frontend/streamlit_app.py", default_timeout=30).run()
    assert app.exception == []
    assert len(app.text_input) >= 2
    assert len(app.tabs) >= 2