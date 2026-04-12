from app.services.generation_config import normalize_seed, resolve_dimensions
from app.services.generation_storage import get_unique_filename
from app.services.generation_stream import create_channel, finalize_channel, publish_event


def test_resolve_dimensions_falls_back_to_square():
    assert resolve_dimensions("unknown", "unknown") == (2048, 2048)


def test_normalize_seed_wraps_large_seed():
    seed = normalize_seed(99999999, 5)
    assert 1 <= seed <= 99999999


def test_get_unique_filename_appends_suffix(tmp_path):
    folder = str(tmp_path)
    first = tmp_path / "image.jpg"
    first.write_bytes(b"data")

    assert get_unique_filename(folder, "image", ".jpg") == "image_1.jpg"


def test_stream_channel_records_and_replays_history():
    channel = create_channel(user_id=1)
    publish_event(channel, {"type": "generating"}, 0)
    publish_event(channel, {"type": "complete"}, 1)
    finalize_channel(channel)

    history = channel["history"]
    assert len(history) == 2
    assert '"event_index": 0' in history[0]
    assert '"event_index": 1' in history[1]
