import sys


def apply_entangler_patch() -> None:
    """
    Patch ARTIQ at runtime so kasli_generic understands "type": "entangler"
    and has any schema/peripheral processor registrations needed.

    IMPORTANT: This runs *before* kasli_generic starts parsing the JSON,
    so schema and peripheral_processors must be registered here.
    """
    # 1) Ensure entangler is importable (so missing dependency errors are clear)
    import entangler  # noqa: F401

    # 2) Import ARTIQ pieces we need to patch
    #    (These import paths match the general structure you were working with.)
    from artiq.coredevice import jsondesc
    from artiq.gateware.eem_7series import peripheral_processors

    # 3) Register the entangler peripheral processor
    #    ---- YOU MUST POINT THIS TO YOUR ACTUAL peripheral_entangler FUNCTION ----
    #
    # If your entangler repo provides a function/class to build the gateware peripheral,
    # import it here and register it:
    #
    #   from entangler.artiq_integration import peripheral_entangler
    #   peripheral_processors["entangler"] = peripheral_entangler
    #
    # Below is a placeholder that will fail loudly until you wire it up.
    def _missing_peripheral_entangler(*args, **kwargs):
        raise RuntimeError(
            "Entangler peripheral processor not wired up. "
            "Edit apply_entangler_patch() to import your peripheral_entangler "
            "and set peripheral_processors['entangler'] = peripheral_entangler."
        )

    peripheral_processors["entangler"] = _missing_peripheral_entangler

    # 4) (Optional but common) Extend JSON schema so ARTIQ validates entangler config fields
    # If you have a schema JSON file in the entangler repo, load and merge it here.
    #
    # Example (adjust path/import to your entangler package):
    #
    #   import importlib.resources as r
    #   schema_text = r.files("entangler").joinpath("entangler_eem.schema.json").read_text()
    #   jsondesc.schema = jsondesc.merge_schemas(jsondesc.schema, schema_text)
    #
    # Leaving schema unchanged is OK *only if* your JSON doesn’t require extra validation
    # or your config already fits the existing schema.


def main() -> None:
    # Patch FIRST (before importing/running kasli_generic main)
    apply_entangler_patch()

    # Delegate to ARTIQ kasli_generic
    from artiq.gateware.targets.kasli_generic import main as kasli_generic_main

    # kasli_generic.main() reads argv itself, but we keep argv unchanged anyway.
    sys.exit(kasli_generic_main())


if __name__ == "__main__":
    main()
