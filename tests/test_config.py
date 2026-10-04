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


def test_model_hints_can_be_disabled_explicitly(monkeypatch):
    import pytest
    from bmq.config import get_settings

    monkeypatch.delenv('BMQ_MODEL_HINTS', raising=False)
    assert get_settings().model_hints is True
    monkeypatch.setenv('BMQ_MODEL_HINTS', 'false')
    assert get_settings().model_hints is False
    monkeypatch.setenv('BMQ_MODEL_HINTS', 'true')
    assert get_settings().model_hints is True
    monkeypatch.setenv('BMQ_MODEL_HINTS', 'typo')
    with pytest.raises(ValueError, match='BMQ_MODEL_HINTS'):
        get_settings()
