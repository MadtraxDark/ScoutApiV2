from scout_api.modules.crawler.utils.product_attributes import (
    SOURCE_NOT_FOUND,
    SOURCE_SPECIFICATIONS,
    SOURCE_TITLE,
    detect_product_category,
    format_identity_variant,
    resolve_attribute,
    resolve_attributes,
    resolve_product_identity,
)


def test_structured_specification_wins_over_title() -> None:
    resolved = resolve_attribute(
        "storage",
        specifications={"Storage": "256 GB"},
        title="Phone XYZ 128GB",
    )
    assert resolved.value == "256 GB"
    assert resolved.source == SOURCE_SPECIFICATIONS


def test_title_fallback_fills_missing_phone_attributes() -> None:
    bundle = resolve_product_identity(
        specifications={},
        title="CELULAR APPLE IPHONE 15 128GB BLUE SIM",
    )
    assert bundle.value("brand") == "Apple"
    assert bundle.get("brand").source == SOURCE_TITLE
    assert bundle.value("model") == "iPhone 15"
    assert bundle.value("storage") == "128 GB"
    assert bundle.value("color") == "Blue"
    assert bundle.category == "smartphone"


def test_smartphone_storage_color_and_connectivity() -> None:
    bundle = resolve_attributes(
        ("model", "storage", "color", "connectivity", "ram"),
        title="Samsung Galaxy S24 5G 256GB 8GB RAM",
    )
    assert bundle.value("storage") == "256 GB"
    assert bundle.value("ram") == "8 GB"
    assert bundle.value("connectivity") == "5G"
    assert bundle.value("model") is not None


def test_ram_kit_attributes() -> None:
    bundle = resolve_product_identity(
        title="Kingston Fury Beast 32GB (2x16GB) DDR5 6000MHz CL36",
        category="ram",
    )
    assert bundle.value("ram") == "32 GB"
    assert bundle.value("capacity") == "32 GB"
    assert bundle.value("module_count") == "2"
    assert bundle.value("module_capacity") == "16 GB"
    assert bundle.value("memory_type") == "DDR5"
    assert bundle.value("frequency") == "6000 MHz"
    assert bundle.value("cas_latency") == "CL36"
    assert bundle.value("storage") is None


def test_motherboard_chipset_socket_memory_wifi() -> None:
    bundle = resolve_product_identity(
        title="ASUS TUF Gaming B650M-Plus WiFi AM5 DDR5",
        category="motherboard",
    )
    assert bundle.value("chipset") == "B650M-PLUS"
    assert bundle.value("socket") == "AM5"
    assert bundle.value("memory_type") == "DDR5"
    assert bundle.value("wifi") == "true"


def test_cpu_cores_threads_from_title_only() -> None:
    bundle = resolve_product_identity(
        title="AMD Ryzen 7 7800X3D 8-Core 16-Thread",
        category="cpu",
    )
    assert bundle.value("brand") == "AMD"
    assert "7800X3D" in (bundle.value("model") or "")
    assert bundle.value("cores") == "8"
    assert bundle.value("threads") == "16"
    # Must not invent socket from external knowledge.
    assert bundle.value("socket") is None


def test_gpu_vram_not_storage() -> None:
    bundle = resolve_product_identity(
        title="MSI GeForce RTX 5060 Ti Gaming Trio OC 8GB GDDR7",
        category="gpu",
    )
    assert bundle.value("vram") == "8 GB"
    assert bundle.value("memory_type") == "GDDR7"
    assert bundle.value("gpu_model") is not None
    assert "5060" in (bundle.value("gpu_model") or "")
    assert bundle.value("overclocked") == "true"
    assert bundle.value("storage") is None


def test_psu_wattage_efficiency_modularity() -> None:
    bundle = resolve_product_identity(
        title="Corsair RM850x 850W 80 Plus Gold Full Modular",
        category="psu",
    )
    assert bundle.value("wattage") == "850 W"
    assert bundle.value("efficiency") == "80 Plus Gold"
    assert bundle.value("modularity") == "Full Modular"


def test_ssd_capacity_interface_form_factor() -> None:
    bundle = resolve_product_identity(
        title="Samsung 990 Pro 2TB NVMe PCIe 4.0 M.2",
        category="ssd",
    )
    assert bundle.value("storage") == "2 TB"
    assert bundle.value("interface") == "NVMe"
    assert bundle.value("pcie_generation") == "PCIe 4.0"
    assert bundle.value("form_factor") == "M.2"


def test_notebook_ram_storage_gpu_refresh() -> None:
    bundle = resolve_product_identity(
        title="Notebook Acer Nitro V Ryzen 7 16GB RAM 512GB SSD RTX 4060 15.6 144Hz",
        category="notebook",
    )
    assert bundle.value("ram") == "16 GB"
    assert bundle.value("storage") == "512 GB"
    assert bundle.value("gpu_model") is not None
    assert "4060" in (bundle.value("gpu_model") or "")
    assert bundle.value("refresh_rate") == "144 Hz"


def test_monitor_screen_resolution_panel_refresh() -> None:
    bundle = resolve_product_identity(
        title='Monitor LG UltraGear 27" QHD IPS 180Hz',
        category="monitor",
    )
    assert bundle.value("screen_size") == '27"'
    assert bundle.value("resolution") == "QHD"
    assert bundle.value("panel") == "IPS"
    assert bundle.value("refresh_rate") == "180 Hz"


def test_cooler_liquid_radiator_and_sockets() -> None:
    bundle = resolve_product_identity(
        title="Water Cooler 360mm ARGB AM5 LGA1700",
        category="cooler",
    )
    assert bundle.value("cooler_type") == "liquid"
    assert bundle.value("radiator_size") == "360 mm"
    assert bundle.value("socket") in {"AM5", "LGA1700"}


def test_console_storage_and_model() -> None:
    bundle = resolve_product_identity(
        title="PlayStation 5 Slim Digital Edition 1TB",
        category="console",
    )
    assert bundle.value("storage") == "1 TB"
    assert bundle.value("brand") == "Sony"
    assert "PlayStation 5" in (bundle.value("model") or "")
    assert format_identity_variant(bundle) == "Digital"


def test_ambiguous_capacities_stay_null() -> None:
    bundle = resolve_attributes(
        ("ram", "storage", "vram"),
        title="Produto XYZ 16GB 512GB",
    )
    assert bundle.value("ram") is None
    assert bundle.value("storage") is None
    assert bundle.value("vram") is None


def test_nothing_found_returns_null() -> None:
    resolved = resolve_attribute(
        "storage",
        specifications={},
        title="Produto XYZ",
    )
    assert resolved.value is None
    assert resolved.source == SOURCE_NOT_FOUND


def test_ram_and_storage_are_distinguished() -> None:
    bundle = resolve_attributes(
        ("ram", "storage", "vram"),
        title="Notebook Acer 16GB RAM 512GB SSD",
    )
    assert bundle.value("ram") == "16 GB"
    assert bundle.value("storage") == "512 GB"
    assert bundle.value("vram") is None


def test_vram_is_not_treated_as_storage() -> None:
    bundle = resolve_attributes(
        ("ram", "storage", "vram"),
        title="Placa de Vídeo RTX 5060 8GB GDDR7",
    )
    assert bundle.value("vram") == "8 GB"
    assert bundle.value("storage") is None
    assert bundle.value("ram") is None


def test_structured_color_overrides_title_color() -> None:
    resolved = resolve_attribute(
        "color",
        specifications={"Color": "Black"},
        title="Phone XYZ 128GB Blue",
    )
    assert resolved.value == "Black"
    assert resolved.source == SOURCE_SPECIFICATIONS


def test_voltage_from_title() -> None:
    resolved = resolve_attribute(
        "voltage",
        title="Liquidificador XYZ 220V",
    )
    assert resolved.value == "220 V"
    assert resolved.source == SOURCE_TITLE


def test_short_alias_does_not_match_inside_longer_words() -> None:
    resolved = resolve_attribute(
        "color",
        specifications={"Notas de coração": "Rosa, iris"},
        title="Perfume Boulevard A La Folie Edp 100 Ml",
    )
    assert resolved.value is None
    assert resolved.source == SOURCE_NOT_FOUND


def test_identifiers_are_not_inferred_from_title() -> None:
    for attribute in ("gtin", "ean", "upc", "sku", "product_id"):
        resolved = resolve_attribute(
            attribute,
            title="CELULAR APPLE IPHONE 15 128GB BLUE SIM 195949036453",
        )
        assert resolved.value is None
        assert resolved.source == SOURCE_NOT_FOUND


def test_screen_size_from_title_without_confusing_storage() -> None:
    bundle = resolve_attributes(
        ("screen_size", "storage", "ram"),
        title='Notebook 15.6" 16GB RAM 512GB SSD',
    )
    assert bundle.value("screen_size") == '15.6"'
    assert bundle.value("ram") == "16 GB"
    assert bundle.value("storage") == "512 GB"


def test_detect_product_category_examples() -> None:
    assert detect_product_category("GeForce RTX 4060 8GB") == "gpu"
    assert detect_product_category("Kingston DDR5 32GB") == "ram"
    assert detect_product_category("Fonte 850W 80 Plus Gold") == "psu"
    assert (
        detect_product_category("Placa-Mae ASUS TUF Gaming B650M-Plus WIFI AM5 DDR5")
        == "motherboard"
    )
    assert (
        detect_product_category("Notebook Acer Nitro V Ryzen 7 16GB 512GB SSD RTX 4060")
        == "notebook"
    )


def test_spaced_dash_separators_and_lavender_color() -> None:
    bundle = resolve_product_identity(
        title="Apple - iPhone 17 512GB - Lavender (Unlocked)",
    )
    assert bundle.category == "smartphone"
    assert bundle.value("brand") == "Apple"
    assert bundle.value("model") == "iPhone 17"
    assert bundle.value("storage") == "512 GB"
    assert bundle.value("color") == "Lavender"


def test_contextual_screen_size_without_inch_mark() -> None:
    monitor = resolve_product_identity(
        title="Monitor LG UltraGear 27 QHD IPS 180Hz",
        category="monitor",
    )
    assert monitor.value("screen_size") == '27"'
    assert monitor.value("resolution") == "QHD"
    assert monitor.value("refresh_rate") == "180 Hz"

    notebook = resolve_product_identity(
        title="Notebook Acer Nitro V Ryzen 7 16GB 512GB SSD RTX 4060 15.6 144Hz",
        category="notebook",
    )
    assert notebook.value("screen_size") == '15.6"'
    assert notebook.value("refresh_rate") == "144 Hz"


def test_bare_number_without_display_context_is_not_screen_size() -> None:
    bundle = resolve_product_identity(
        title="Produto XYZ modelo 27 especial",
        category="monitor",
    )
    assert bundle.value("screen_size") is None


def test_hyphenated_cpu_codes_are_preserved() -> None:
    bundle = resolve_product_identity(
        title="Processador Intel Core i7-14700K 20 Cores LGA1700",
        category="cpu",
    )
    assert "14700K" in (bundle.value("model") or "")
    assert bundle.value("processor") is not None
    assert "i7-14700K" in (bundle.value("processor") or "")


def test_brand_skips_product_type_prefixes() -> None:
    gpu = resolve_product_identity(title="Placa de Video MSI GeForce RTX 4060 Ti 8GB")
    assert gpu.value("brand") in {"Msi", "MSI"}
    assert gpu.value("vram") == "8 GB"

    ssd = resolve_product_identity(title="SSD Samsung 990 PRO 2TB NVMe PCIe 4.0 M.2")
    assert ssd.value("brand") == "Samsung"
    assert ssd.value("storage") == "2 TB"

    mobo = resolve_product_identity(
        title="Placa-Mae ASUS TUF Gaming B650M-Plus WIFI AM5 DDR5"
    )
    assert mobo.category == "motherboard"
    assert mobo.value("brand") == "Asus"
    assert mobo.value("chipset") == "B650M-PLUS"
    assert mobo.value("socket") == "AM5"


def test_psu_gold_is_efficiency_not_color() -> None:
    bundle = resolve_product_identity(
        title="Corsair RM850x 850W 80 Plus Gold Full Modular",
        category="psu",
    )
    assert bundle.value("efficiency") == "80 Plus Gold"
    assert bundle.value("color") is None


def test_iphone_does_not_become_processor() -> None:
    bundle = resolve_product_identity(title="CELULAR APPLE IPHONE 15 128GB BLUE")
    assert bundle.value("processor") is None
    assert bundle.value("storage") == "128 GB"


def test_notebook_unmarked_ram_with_ssd_marker() -> None:
    bundle = resolve_product_identity(
        title="Notebook Acer Nitro V Ryzen 7 16GB 512GB SSD RTX 4060 15.6 144Hz",
    )
    assert bundle.category == "notebook"
    assert bundle.value("ram") == "16 GB"
    assert bundle.value("storage") == "512 GB"
    assert bundle.value("gpu_model") is not None
    assert bundle.value("refresh_rate") == "144 Hz"
    assert "Ryzen" in (bundle.value("processor") or "")
