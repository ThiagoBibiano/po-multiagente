"""Roteiro tirado do gabarito: exercita o arnês inteiro sem rede e sem custo.

O Interpretador devolve o quadro de referência (na primeira rodada, com as
origens tratadas ainda nos arquivos originais), o Modelador devolve a
formulação de referência e o Explicador, um texto com marcadores. Mede o
arnês (grafo, compilador, validação, respondedor), e não o modelo de linguagem.
"""

import json
from typing import Any

from po_multiagente.avaliacao.instancia import Instancia
from po_multiagente.llm import LLMRoteirizado, Pedido

_CAMPOS_OPCIONAIS = ("solicitacoes", "premissas", "nao_considerado", "alertas")


def roteiro_do_gabarito(instancia: Instancia, rodadas: int = 3) -> LLMRoteirizado:
    """Modelo roteirizado que responde com o gabarito da instância."""
    quadro: dict[str, Any] = json.loads(
        (instancia.pasta / "referencia" / "quadro.json").read_text(encoding="utf-8")
    )
    for campo in _CAMPOS_OPCIONAIS:
        quadro.setdefault(campo, [])
    modelo = json.loads(
        (instancia.pasta / "referencia" / "modelo.json").read_text(encoding="utf-8")
    )

    def interpretador(pedido: Pedido) -> dict[str, Any]:
        if "Arquivos tratados recebidos" in pedido.entrada:
            return quadro
        return _quadro_antes_do_tratamento(quadro)

    return LLMRoteirizado(
        {
            "interpretador": [interpretador] * rodadas,
            "modelador": [modelo] * rodadas,
            "explicador": [{"texto": "O melhor resultado para o critério é {{OBJ}}."}] * rodadas,
        }
    )


def _quadro_antes_do_tratamento(quadro: dict[str, Any]) -> dict[str, Any]:
    """Aponta os parâmetros tratados para o arquivo original da solicitação."""
    solicitacoes = {s["id"]: s for s in quadro["solicitacoes"]}
    parametros = []
    for parametro in quadro["parametros"]:
        origem = parametro["origem"]
        solicitacao = solicitacoes.get(origem.get("solicitacao_id") or "")
        if solicitacao is not None:
            origem = {
                "arquivo": solicitacao["arquivo"],
                "coluna": solicitacao["coluna"],
                "chaves": [],
                "filtros": [],
                "solicitacao_id": solicitacao["id"],
            }
        parametros.append({**parametro, "origem": origem})
    return {**quadro, "parametros": parametros}
