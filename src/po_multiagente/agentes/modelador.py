"""Modelador: quadro de especificação → modelo na representação intermediária."""

from dataclasses import dataclass

from po_multiagente.agentes._comum import (
    ErroAgente,
    ErroFormato,
    Registro,
    bloco_json,
    descrever_fontes,
    gerar_estruturado,
)
from po_multiagente.dados import Fontes
from po_multiagente.dominio import Especificacao, ModeloIR
from po_multiagente.llm import LLMPort
from po_multiagente.modelo import ErroCompilacao, ModeloCompilado, compilar
from po_multiagente.prompts import carregar_instrucao


@dataclass(frozen=True)
class ResultadoModelador:
    """Modelo compilado e quantas tentativas de formato ele exigiu (ADR-008)."""

    compilado: ModeloCompilado
    tentativas_formato: int


class Modelador:
    """Agente Modelador (cap. 3, Passo 3).

    Erros de esquema e de compilação geram nova tentativa dentro do próprio
    agente, com limite fixo, igual com e sem Validador (ADR-008).

    Args:
        llm: Modelo de linguagem.
        max_tentativas: Tentativas de formato por chamada.
    """

    agente = "modelador"

    def __init__(self, llm: LLMPort, max_tentativas: int = 3) -> None:
        self._llm = llm
        self._max_tentativas = max_tentativas
        self._instrucao = carregar_instrucao(self.agente)

    def formular(
        self,
        especificacao: Especificacao,
        fontes: Fontes,
        registro: Registro,
        *,
        anterior: ModeloIR | None = None,
        retorno_validador: str | None = None,
    ) -> ResultadoModelador:
        """Formula (ou corrige) o modelo.

        Raises:
            ErroAgente: Se as tentativas de formato se esgotarem.
        """
        quadro = especificacao.model_dump(
            mode="json", exclude={"fontes", "solicitacoes", "alertas"}
        )
        partes = [
            bloco_json("Quadro de especificação", quadro),
            f"# Inventário das fontes\n\n{descrever_fontes(fontes)}",
        ]
        if anterior is not None:
            partes.append(bloco_json("Modelo anterior", anterior.model_dump(mode="json")))
        if retorno_validador:
            partes.append(f"# Parecer do Validador\n\n{retorno_validador}")
        base = "\n\n".join(partes)
        mensagens: list[str] = []
        for tentativa in range(1, self._max_tentativas + 1):
            entrada = (
                base
                if not mensagens
                else f"{base}\n\n# Erros de formato a corrigir\n\n{mensagens[-1]}"
            )
            try:
                ir = gerar_estruturado(self._llm, self._instrucao, entrada, ModeloIR, registro)
                compilado = compilar(ir)
            except ErroFormato as erro:
                mensagens.append(str(erro))
                continue
            except ErroCompilacao as erro:
                mensagens.append("\n".join(f"- {e}" for e in erro.erros))
                continue
            return ResultadoModelador(compilado=compilado, tentativas_formato=tentativa)
        raise ErroAgente(self.agente, mensagens)
