import main


def test_app_module_is_importable():
    assert callable(main.main)
