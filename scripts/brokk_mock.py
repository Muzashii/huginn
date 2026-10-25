"""API falsa do Brokk para desenvolver a ferramenta `orcamento` do W2.

Só biblioteca padrão (roda na imagem python:3.12-slim do docker-compose, profile "mock").
  POST /orcamento  {"material": "resina", "altura_cm": 10, "quantidade": 1, "acabamento": "cru"}
  GET  /saude
Os valores são fictícios; o Brokk real calcula a partir do STL.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PRECO_CM = {"resina": 6.0, "fdm": 2.5}
ACABAMENTO = {"cru": 1.0, "lixado": 1.2, "primer": 1.1}
PRAZO = {"resina": "3 a 5 dias úteis", "fdm": "2 a 4 dias úteis"}


def calcular(pedido: dict) -> tuple[int, dict]:
    material = str(pedido.get("material", "")).lower()
    acabamento = str(pedido.get("acabamento", "cru")).lower()
    try:
        altura = float(pedido.get("altura_cm", 0))
        quantidade = int(pedido.get("quantidade", 1))
    except (TypeError, ValueError):
        return 400, {"erro": "altura_cm e quantidade precisam ser números"}
    if material not in PRECO_CM or acabamento not in ACABAMENTO or not 1 <= altura <= 30 or quantidade < 1:
        return 400, {"erro": "pedido inválido", "materiais": list(PRECO_CM), "acabamentos": list(ACABAMENTO)}
    unitario = max(25.0, altura * PRECO_CM[material]) * ACABAMENTO[acabamento]
    desconto = 0.1 if quantidade >= 10 else 0.0
    total = round(unitario * quantidade * (1 - desconto), 2)
    return 200, {
        "valor_unitario": round(unitario, 2),
        "quantidade": quantidade,
        "desconto": desconto,
        "valor_total": total,
        "prazo_producao": PRAZO[material],
        "observacao": "Valor estimado (mock). O orçamento final é confirmado pela equipe.",
    }


class Handler(BaseHTTPRequestHandler):
    def _responder(self, status: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/saude":
            return self._responder(200, {"ok": True})
        self._responder(404, {"erro": "rota"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/orcamento":
            return self._responder(404, {"erro": "rota"})
        try:
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self._responder(400, {"erro": "JSON inválido"})
        self._responder(*calcular(pedido))


if __name__ == "__main__":
    print("brokk-mock ouvindo em :8090", flush=True)
    HTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
