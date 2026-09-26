"""Gravação e reprodução de chamadas ao modelo de linguagem.

A API não garante repetição (não há ``seed`` na API de Respostas, e o
raciocínio é estocástico). Gravar as respostas torna reproduzível uma
execução já feita, e permite ao CI rodar o fluxo sem rede e sem custo.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from po_multiagente.llm.porta import ErroLLM, LLMPort, Pedido, RespostaLLM, Uso

ModoCassete = Literal["gravar", "reproduzir"]


def chave_pedido(modelo: str, pedido: Pedido) -> str:
    """Identidade de uma chamada: modelo, agente, instruções, entrada e esquema."""
    conteudo = json.dumps(
        [modelo, pedido.agente, pedido.instrucoes, pedido.entrada, pedido.esquema],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(conteudo.encode()).hexdigest()


class Cassete:
    """Envolve um ``LLMPort``: grava cada resposta ou reproduz as gravadas.

    Args:
        caminho: Arquivo JSONL, uma chamada por linha.
        modo: ``gravar`` chama o modelo e acrescenta ao arquivo; ``reproduzir``
            nunca chama o modelo e falha se a chamada não estiver gravada.
        interno: Modelo real; obrigatório para gravar.
        modelo: Identificador do modelo, para compor a chave ao reproduzir.
    """

    def __init__(
        self, caminho: Path, modo: ModoCassete, interno: LLMPort | None = None, modelo: str = ""
    ) -> None:
        if modo == "gravar" and interno is None:
            raise ValueError("Gravar exige o modelo real")
        self._caminho = caminho
        self._modo = modo
        self._interno = interno
        self._modelo = interno.modelo if interno is not None else modelo
        self._gravadas: dict[str, RespostaLLM] = {}
        if caminho.exists():
            for linha in caminho.read_text(encoding="utf-8").splitlines():
                registro = json.loads(linha)
                resposta = registro["resposta"]
                self._gravadas[registro["chave"]] = RespostaLLM(
                    texto=resposta["texto"],
                    modelo=resposta["modelo"],
                    uso=Uso(**resposta["uso"]),
                    parametros=resposta["parametros"],
                    duracao_s=resposta["duracao_s"],
                    gravada=True,
                )

    @property
    def modelo(self) -> str:
        """Identificador do modelo gravado ou chamado."""
        return self._modelo

    def gerar(self, pedido: Pedido) -> RespostaLLM:
        """Reproduz a resposta gravada ou, no modo gravar, chama e grava."""
        chave = chave_pedido(self._modelo, pedido)
        if chave in self._gravadas:
            return self._gravadas[chave]
        if self._modo == "reproduzir" or self._interno is None:
            raise ErroLLM(f"Chamada do agente {pedido.agente} não gravada em {self._caminho.name}")
        resposta = self._interno.gerar(pedido)
        self._gravadas[chave] = resposta
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._caminho.open("a", encoding="utf-8") as arquivo:
            registro = {"chave": chave, "agente": pedido.agente, "resposta": asdict(resposta)}
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return resposta
