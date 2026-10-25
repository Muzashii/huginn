import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from brokk_mock import calcular  # noqa: E402


def test_orcamento_valido():
    status, corpo = calcular({"material": "resina", "altura_cm": 10, "quantidade": 2, "acabamento": "primer"})
    assert status == 200
    assert corpo["valor_total"] == round(60 * 1.1 * 2, 2)


def test_desconto_a_partir_de_10_unidades():
    _, corpo = calcular({"material": "fdm", "altura_cm": 20, "quantidade": 10})
    assert corpo["desconto"] == 0.1


def test_pedido_invalido():
    assert calcular({"material": "ouro", "altura_cm": 10})[0] == 400
    assert calcular({"material": "fdm", "altura_cm": "dez"})[0] == 400
