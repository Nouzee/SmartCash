def test_public_package_uses_smartcash_name() -> None:
    import smartcash

    assert smartcash.PROJECT_NAME == "SmartCash"
    assert smartcash.SNAPSHOT_SCHEMA_VERSION == "1.0"
