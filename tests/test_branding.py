import pytest

from lunacaption import config
from lunacaption.branding import NIGHT, VIOLET, app_icon, logo_mark


@pytest.mark.parametrize("size", [16, 42, 256])
def test_logo_renders_crescent_and_caption_lines(size):
    mark = logo_mark(size)
    assert mark.size == (size, size) and mark.mode == "RGBA"
    assert mark.getpixel((0, 0))[3] == 0  # transparent outside the crescent
    if size >= 256:
        colours = {colour[:3] for _, colour in mark.getcolors(1 << 20) if colour[3] == 255}
        for expected in (VIOLET, NIGHT):
            assert tuple(int(expected[i : i + 2], 16) for i in (1, 3, 5)) in colours


def test_app_icon_sits_on_an_opaque_tile():
    icon = app_icon(64)
    assert icon.size == (64, 64)
    assert icon.getpixel((32, 2))[3] == 255
    assert icon.getpixel((0, 0))[3] < 255  # rounded corner


def test_cache_prefers_new_variable_then_previous_name(monkeypatch, tmp_path):
    monkeypatch.setenv("LUMACAPTION_CACHE", str(tmp_path / "old"))
    monkeypatch.delenv("LUNACAPTION_CACHE", raising=False)
    assert config.default_cache() == (tmp_path / "old").resolve()
    monkeypatch.setenv("LUNACAPTION_CACHE", str(tmp_path / "new"))
    assert config.default_cache() == (tmp_path / "new").resolve()


def test_cache_reuses_model_downloaded_under_previous_name(monkeypatch, tmp_path):
    monkeypatch.delenv("LUNACAPTION_CACHE", raising=False)
    monkeypatch.delenv("LUMACAPTION_CACHE", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.default_cache() == tmp_path / "LunaCaption" / "models"
    (tmp_path / "LumaCaption" / "models").mkdir(parents=True)
    assert config.default_cache() == tmp_path / "LumaCaption" / "models"
    (tmp_path / "LunaCaption" / "models").mkdir(parents=True)
    assert config.default_cache() == tmp_path / "LunaCaption" / "models"
