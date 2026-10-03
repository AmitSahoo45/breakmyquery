def test_relative_data_dir_is_anchored_to_repo(monkeypatch):
    from bmq.config import ROOT, get_settings
    monkeypatch.setenv('BMQ_DATA_DIR', '.bmq/test-data')
    assert get_settings().data_dir == ROOT / '.bmq' / 'test-data'


def test_cloud_host_and_outside_data_path_are_rejected(monkeypatch):
    import pytest
    from bmq.config import get_settings
    monkeypatch.setenv('BMQ_OLLAMA_HOST', 'https://ollama.com')
    with pytest.raises(ValueError):
        get_settings()
    monkeypatch.setenv('BMQ_OLLAMA_HOST', 'http://localhost:11434')
    monkeypatch.setenv('BMQ_DATA_DIR', '../outside')
    with pytest.raises(ValueError):
        get_settings()
