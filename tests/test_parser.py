import pathlib

from src.parser import yaml_loader


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_minimal8_loads_and_validates():
    isa_path = BASE_DIR / "examples" / "minimal8.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    assert data["metadata"]["name"] == "Minimal8"
    assert data["memory"]["address_bits"] == 16
    assert len(data["instructions"]) > 0


def test_simple8_loads_and_validates():
    isa_path = BASE_DIR / "examples" / "simple8.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    assert data["metadata"]["name"] == "Simple8"
    assert len(data["registers"]) >= 8
    assert any(inst["name"] == "HALT" for inst in data["instructions"])

