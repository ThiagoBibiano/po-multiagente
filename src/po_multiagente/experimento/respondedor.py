"""Respondedor simulado: faz o papel do usuário numa instância com gabarito.

Responde a uma solicitação de tratamento com o arquivo de ``dados_tratados/``
só quando ela bate com ``solicitacoes_esperadas.yaml`` (mesmo arquivo e mesma
coluna; ou só o arquivo, quando ele tem uma única resposta). Uma solicitação
que não bate fica sem resposta, e o caso conta como falha de "Solicitação de
tratamento" (plano, seção 6). Às perguntas sobre o resultado (ADR-011),
responde com ``resultado_trivial_aceitavel`` do ``meta.yaml``, sem acrescentar
nenhuma exigência.
"""

import shutil
from pathlib import Path
from typing import Any

import yaml

from po_multiagente.avaliacao.instancia import Instancia


class RespondedorSimulado:
    """Respostas do usuário simulado para uma instância.

    Args:
        instancia: Instância com gabarito.
        pasta_tratados: Pasta vazia da execução, onde os arquivos entregues são copiados.
    """

    def __init__(self, instancia: Instancia, pasta_tratados: Path) -> None:
        self._instancia = instancia
        self._pasta = pasta_tratados
        arquivo = instancia.pasta / "solicitacoes_esperadas.yaml"
        self._esperadas: list[dict[str, Any]] = (
            yaml.safe_load(arquivo.read_text(encoding="utf-8")) or [] if arquivo.exists() else []
        )
        self.nao_atendidas: list[dict[str, Any]] = []

    def responder_solicitacoes(self, solicitacoes: list[dict[str, Any]]) -> dict[str, Any]:
        """Arquivos tratados para as solicitações que batem com as esperadas."""
        self._pasta.mkdir(parents=True, exist_ok=True)
        respondidas: dict[str, str] = {}
        for solicitacao in solicitacoes:
            resposta = self._resposta_para(solicitacao)
            if resposta is None:
                self.nao_atendidas.append(solicitacao)
                continue
            origem = self._instancia.pasta / "dados_tratados" / resposta
            if not (self._pasta / resposta).exists():
                shutil.copyfile(origem, self._pasta / resposta)
            respondidas[solicitacao["id"]] = resposta
        return {"pasta": str(self._pasta), "respondidas": respondidas}

    def responder_confirmacao(self) -> dict[str, Any]:
        """Aceita o resultado trivial só se o gabarito o considera aceitável."""
        return {"aceita": bool(self._instancia.meta.get("resultado_trivial_aceitavel", False))}

    def _resposta_para(self, solicitacao: dict[str, Any]) -> str | None:
        mesmas = [e for e in self._esperadas if e.get("arquivo") == solicitacao.get("arquivo")]
        exatas = [e for e in mesmas if e.get("coluna") == solicitacao.get("coluna")]
        if exatas:
            return str(exatas[0]["resposta"])
        respostas = {e["resposta"] for e in mesmas}
        return str(respostas.pop()) if len(respostas) == 1 else None
