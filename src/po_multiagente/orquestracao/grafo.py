"""Grafo de estados que encadeia os agentes (ADR-007).

O estado guarda só objetos de domínio e tipos simples, que o checkpointer
serializa com segurança; o modelo compilado e o instanciado são recalculados
quando preciso (é barato e determinístico). O resultado do solver, a parte
cara, fica no estado.
"""

import operator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from po_multiagente import dominio
from po_multiagente.agentes import (
    ErroAgente,
    Execucao,
    Explicador,
    GeradorExecutor,
    Interpretador,
    Modelador,
    Registro,
    Rodada,
    Validador,
)
from po_multiagente.config import ConfiguracaoExecucao
from po_multiagente.dados import ErroLigacao, Fontes, ligar
from po_multiagente.dominio import (
    Especificacao,
    Explicacao,
    ModeloIR,
    ParecerValidador,
    ResultadoSolver,
    Solicitacao,
)
from po_multiagente.llm import LLMPort
from po_multiagente.modelo import ErroInstanciacao, compilar, instanciar
from po_multiagente.solver import OpcoesSolver, obter_backend


class Estado(TypedDict, total=False):
    """Estado compartilhado pelos agentes (cap. 3, Passo 3)."""

    descricao: str
    pasta_dados: str
    pastas_tratadas: list[str]
    respondidas: dict[str, str]
    observacao_usuario: str | None
    especificacao: Especificacao
    pendentes: list[Solicitacao]
    rodadas_tratamento: int
    rodadas_confirmacao: int
    modelo: ModeloIR
    retorno_modelador: str | None
    resultado: ResultadoSolver
    erros_execucao: list[str]
    log_solver: str
    pareceres: Annotated[list[ParecerValidador], operator.add]
    explicacao: Explicacao
    falha: str | None
    tentativas_formato: Annotated[list[int], operator.add]
    chamadas: Annotated[list[dict[str, Any]], operator.add]
    eventos: Annotated[list[dict[str, Any]], operator.add]


@dataclass(frozen=True)
class Agentes:
    """Os agentes de uma execução, construídos a partir da configuração."""

    interpretador: Interpretador
    modelador: Modelador
    gerador_executor: GeradorExecutor
    validador: Validador
    explicador: Explicador

    @classmethod
    def criar(cls, llm: LLMPort, configuracao: ConfiguracaoExecucao) -> "Agentes":
        """Monta os agentes com o modelo e o solver da configuração."""
        return cls(
            interpretador=Interpretador(llm, configuracao.max_tentativas_formato),
            modelador=Modelador(llm, configuracao.max_tentativas_formato),
            gerador_executor=GeradorExecutor(
                obter_backend(configuracao.backend_solver),
                configuracao.motor_solver,
                OpcoesSolver(limite_tempo_s=configuracao.limite_tempo_solver_s),
            ),
            validador=Validador(),
            explicador=Explicador(llm),
        )


def serializador() -> JsonPlusSerializer:
    """Serializador do checkpointer com os tipos do domínio liberados."""
    tipos = [
        (objeto.__module__, objeto.__name__)
        for objeto in (getattr(dominio, nome) for nome in dominio.__all__)
        if isinstance(objeto, type)
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=tipos)


def montar_grafo(
    agentes: Agentes,
    configuracao: ConfiguracaoExecucao,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any]:
    """Monta o grafo, com ou sem o nó Validador (``configuracao.validador``).

    Sem Validador, o nó não existe: a saída do Gerador-Executor vai direto
    ao Explicador (Passo 7).
    """
    nos = _Nos(agentes, configuracao)
    grafo: StateGraph[Any] = StateGraph(Estado)
    grafo.add_node("interpretar", nos.interpretar)
    grafo.add_node("tratar", nos.tratar)
    grafo.add_node("modelar", nos.modelar)
    grafo.add_node("executar", nos.executar)
    grafo.add_node("explicar", nos.explicar)
    grafo.add_edge(START, "interpretar")
    grafo.add_conditional_edges(
        "interpretar", nos.depois_de_interpretar, ["tratar", "modelar", END]
    )
    grafo.add_edge("tratar", "interpretar")
    grafo.add_conditional_edges("modelar", nos.depois_de_modelar, ["executar", END])
    if configuracao.validador:
        grafo.add_node("validar", nos.validar)
        grafo.add_node("confirmar", nos.confirmar)
        grafo.add_edge("executar", "validar")
        grafo.add_conditional_edges(
            "validar", nos.depois_de_validar, ["modelar", "confirmar", "explicar"]
        )
        grafo.add_conditional_edges(
            "confirmar", nos.depois_de_confirmar, ["interpretar", "modelar", "explicar"]
        )
    else:
        grafo.add_edge("executar", "explicar")
    grafo.add_edge("explicar", END)
    return grafo.compile(checkpointer=checkpointer or InMemorySaver(serde=serializador()))


def fontes_do_estado(estado: Estado) -> Fontes:
    """Fontes da sessão: dados originais e pastas de arquivos tratados."""
    return Fontes(
        Path(estado["pasta_dados"]), *(Path(p) for p in estado.get("pastas_tratadas", []))
    )


def execucao_do_estado(estado: Estado) -> Execucao:
    """Refaz, sem resolver de novo, a execução guardada no estado."""
    compilado = compilar(estado["modelo"])
    instancia = None
    if not estado.get("erros_execucao"):
        try:
            dados = ligar(compilado.ir, estado["especificacao"], fontes_do_estado(estado))
            instancia = instanciar(compilado, dados.conjuntos, dados.parametros)
        except (ErroLigacao, ErroInstanciacao):
            instancia = None
    return Execucao(
        compilado=compilado,
        instancia=instancia,
        resultado=estado["resultado"],
        log=estado.get("log_solver", ""),
        erros=tuple(estado.get("erros_execucao", [])),
    )


class _Nos:
    """Nós do grafo; cada um devolve só as chaves do estado que altera.

    O parâmetro dos nós se chama ``state`` porque é o nome exigido pelo
    protocolo de nó do LangGraph (ADR-005: nomes de biblioteca ficam em inglês).
    """

    def __init__(self, agentes: Agentes, configuracao: ConfiguracaoExecucao) -> None:
        self._agentes = agentes
        self._configuracao = configuracao

    # ------------------------------------------------------------------ nós

    def interpretar(self, state: Estado) -> dict[str, Any]:
        registro = Registro()
        rodada = Rodada(
            anterior=state.get("especificacao"),
            respondidas=state.get("respondidas", {}),
            observacao_usuario=state.get("observacao_usuario"),
        )
        try:
            resultado = self._agentes.interpretador.especificar(
                state["descricao"], fontes_do_estado(state), registro, rodada
            )
        except ErroAgente as erro:
            return _com_registro(
                registro, {"falha": str(erro)}, "interpretador", "falha", str(erro)
            )
        return _com_registro(
            registro,
            {
                "especificacao": resultado.especificacao,
                "pendentes": list(resultado.pendentes),
                "observacao_usuario": None,
            },
            "interpretador",
            "quadro",
            f"{len(resultado.especificacao.requisitos)} requisitos, "
            f"{len(resultado.pendentes)} solicitações pendentes",
        )

    def tratar(self, state: Estado) -> dict[str, Any]:
        resposta = interrupt(
            {
                "tipo": "solicitacoes",
                "solicitacoes": [s.model_dump(mode="json") for s in state.get("pendentes", [])],
            }
        )
        pastas = list(state.get("pastas_tratadas", []))
        if resposta.get("pasta") and resposta["pasta"] not in pastas:
            pastas.append(resposta["pasta"])
        return {
            "pastas_tratadas": pastas,
            "respondidas": {**state.get("respondidas", {}), **resposta.get("respondidas", {})},
            "rodadas_tratamento": state.get("rodadas_tratamento", 0) + 1,
            "eventos": [_evento("usuario", "tratamento", resposta.get("respondidas", {}))],
        }

    def modelar(self, state: Estado) -> dict[str, Any]:
        registro = Registro()
        try:
            resultado = self._agentes.modelador.formular(
                state["especificacao"],
                fontes_do_estado(state),
                registro,
                anterior=state.get("modelo"),
                retorno_validador=state.get("retorno_modelador"),
            )
        except ErroAgente as erro:
            return _com_registro(registro, {"falha": str(erro)}, "modelador", "falha", str(erro))
        return _com_registro(
            registro,
            {
                "modelo": resultado.compilado.ir,
                "retorno_modelador": None,
                "tentativas_formato": [resultado.tentativas_formato],
            },
            "modelador",
            "modelo",
            f"{len(resultado.compilado.ir.restricoes)} famílias de restrições, "
            f"{resultado.tentativas_formato} tentativa(s) de formato",
        )

    def executar(self, state: Estado) -> dict[str, Any]:
        execucao = self._agentes.gerador_executor.executar(
            compilar(state["modelo"]), state["especificacao"], fontes_do_estado(state)
        )
        return {
            "resultado": execucao.resultado,
            "erros_execucao": list(execucao.erros),
            "log_solver": execucao.log,
            "eventos": [_evento("gerador_executor", "resultado", execucao.resultado.status.value)],
        }

    def validar(self, state: Estado) -> dict[str, Any]:
        iteracao = len(state.get("pareceres", [])) + 1
        parecer = self._agentes.validador.validar(
            iteracao,
            execucao_do_estado(state),
            state["especificacao"],
            self._agentes.gerador_executor.resolver,
        )
        atualizacao: dict[str, Any] = {
            "pareceres": [parecer],
            "eventos": [
                _evento("validador", "parecer", "aprovado" if parecer.aprovado else "reprovado")
            ],
        }
        if not parecer.aprovado:
            atualizacao["retorno_modelador"] = Validador.retorno(parecer)
        return atualizacao

    def confirmar(self, state: Estado) -> dict[str, Any]:
        parecer = state["pareceres"][-1]
        resposta = interrupt({"tipo": "confirmacao", "perguntas": list(parecer.confirmacoes)})
        if resposta.get("aceita", True):
            return {"eventos": [_evento("usuario", "confirmacao", "aceita")]}
        observacao = resposta.get("observacao")
        atualizacao: dict[str, Any] = {
            "rodadas_confirmacao": state.get("rodadas_confirmacao", 0) + 1,
            "eventos": [_evento("usuario", "confirmacao", observacao or "não faz sentido")],
        }
        if observacao:
            atualizacao["observacao_usuario"] = observacao
        else:
            atualizacao["retorno_modelador"] = (
                "- S5 (objetivo): o gestor disse que o resultado não faz sentido: "
                + " ".join(parecer.confirmacoes)
            )
        return atualizacao

    def explicar(self, state: Estado) -> dict[str, Any]:
        registro = Registro()
        pareceres = state.get("pareceres", [])
        explicacao = self._agentes.explicador.explicar(
            state["especificacao"],
            execucao_do_estado(state),
            pareceres[-1] if pareceres else None,
            registro,
        )
        return _com_registro(registro, {"explicacao": explicacao}, "explicador", "explicacao", "")

    # ------------------------------------------------------------------ rotas

    def depois_de_interpretar(self, estado: Estado) -> str:
        if estado.get("falha"):
            return END
        limite = self._configuracao.max_rodadas_tratamento
        if estado.get("pendentes") and estado.get("rodadas_tratamento", 0) < limite:
            return "tratar"
        return "modelar"

    @staticmethod
    def depois_de_modelar(estado: Estado) -> str:
        return END if estado.get("falha") else "executar"

    def depois_de_validar(self, estado: Estado) -> str:
        parecer = estado["pareceres"][-1]
        if not parecer.aprovado:
            limite = self._configuracao.max_iteracoes_validador
            return "modelar" if len(estado["pareceres"]) < limite else "explicar"
        if parecer.confirmacoes and estado.get("rodadas_confirmacao", 0) < 1:
            return "confirmar"
        return "explicar"

    def depois_de_confirmar(self, estado: Estado) -> str:
        if estado.get("observacao_usuario"):
            return "interpretar"
        if estado.get("retorno_modelador"):
            limite = self._configuracao.max_iteracoes_validador
            return "modelar" if len(estado["pareceres"]) < limite else "explicar"
        return "explicar"


def _evento(agente: str, artefato: str, detalhe: object) -> dict[str, Any]:
    return {"agente": agente, "artefato": artefato, "detalhe": detalhe}


def _com_registro(
    registro: Registro, atualizacao: dict[str, Any], agente: str, artefato: str, detalhe: str
) -> dict[str, Any]:
    chamadas = [{**asdict(c), "uso": asdict(c.uso)} for c in registro.chamadas]
    return {**atualizacao, "chamadas": chamadas, "eventos": [_evento(agente, artefato, detalhe)]}
