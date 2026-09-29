"""Assistente em etapas: conduz uma sessão para a interface, sem depender do Gradio.

A interface só mostra o que o assistente devolve e repassa as respostas do
usuário. Toda a condução (pasta de trabalho, arquivos enviados, respostas às
interrupções e visão do resultado) fica aqui, testável sem navegador.
"""

import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from po_multiagente.config import ConfiguracaoExecucao, carregar_perfil
from po_multiagente.dominio import Solicitacao
from po_multiagente.llm import LLMPort
from po_multiagente.modelo import ErroCompilacao, compilar, para_latex
from po_multiagente.orquestracao import Estado, Interrupcao, Sessao

TipoEtapa = Literal["solicitacoes", "confirmacao", "resultado"]

PASSOS = {
    "interpretar": "Interpretador: lendo a descrição e as planilhas",
    "tratar": "Recebendo os arquivos enviados",
    "modelar": "Modelador: montando o modelo matemático",
    "executar": "Resolvendo o modelo com o solver",
    "validar": "Validador: conferindo o modelo e a solução",
    "confirmar": "Preparando uma pergunta para você",
    "explicar": "Explicador: escrevendo a resposta",
}
"""O que cada nó do grafo faz, em palavras do usuário, para o progresso na tela."""


@dataclass(frozen=True)
class Etapa:
    """O que a interface mostra a seguir.

    Attributes:
        tipo: ``solicitacoes`` (o usuário envia arquivos tratados),
            ``confirmacao`` (o usuário diz se o resultado faz sentido, ADR-011)
            ou ``resultado`` (fim do fluxo, com ou sem solução).
    """

    tipo: TipoEtapa
    solicitacoes: tuple[Solicitacao, ...] = ()
    perguntas: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resultado:
    """Visão do fim do fluxo: a explicação primeiro, os artefatos técnicos depois (R5)."""

    explicacao: str | None
    status: str | None
    valor_objetivo: float | None
    falha: str | None
    solucao: dict[str, float] = field(default_factory=dict)
    especificacao: dict[str, Any] | None = None
    modelo: dict[str, Any] | None = None
    formulacao_latex: str | None = None
    pareceres: list[dict[str, Any]] = field(default_factory=list)
    chamadas_llm: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo: float = 0.0
    moeda: str = ""
    eventos: list[dict[str, Any]] = field(default_factory=list)


class ErroAssistente(Exception):
    """Pedido fora de ordem ou incompleto (por exemplo, responder sem ter começado)."""


class Assistente:
    """Uma conversa do usuário com a plataforma, do pedido ao resultado.

    Args:
        llm: Modelo de linguagem.
        configuracao: Configuração da execução; o padrão é o do experimento.
        pasta_trabalho: Onde guardar os arquivos enviados; o padrão é uma
            pasta temporária.

    Attributes:
        ao_avancar: Chamada com a descrição de cada passo que começa (ver
            ``PASSOS``); a interface a troca a cada execução.
    """

    def __init__(
        self,
        llm: LLMPort,
        configuracao: ConfiguracaoExecucao | None = None,
        pasta_trabalho: Path | None = None,
    ) -> None:
        self._llm = llm
        self._configuracao = configuracao or ConfiguracaoExecucao()
        self._raiz = pasta_trabalho or Path(tempfile.mkdtemp(prefix="po-multiagente-"))
        self._sessao: Sessao | None = None
        self._etapa: Etapa | None = None
        self._rodadas = 0
        self.ao_avancar: Callable[[str], None] | None = None

    @property
    def etapa(self) -> Etapa | None:
        """Etapa atual; ``None`` antes de começar."""
        return self._etapa

    def comecar(self, descricao: str, arquivos: Sequence[Path]) -> Etapa:
        """Começa uma sessão nova com o pedido e as fontes de dados.

        Raises:
            ErroAssistente: Sem descrição ou sem arquivo.
        """
        if not descricao.strip():
            raise ErroAssistente("Descreva o problema antes de executar.")
        if not arquivos:
            raise ErroAssistente(
                "Envie ao menos uma planilha (CSV ou Excel): os números do problema vêm "
                "das suas planilhas, e não do texto."
            )
        pasta = self._raiz / "dados"
        shutil.rmtree(pasta, ignore_errors=True)
        _copiar(arquivos, pasta)
        self._rodadas = 0
        self._sessao = Sessao(self._llm, self._configuracao, ao_iniciar_no=self._avisar)
        return self._avancar(self._sessao.iniciar(descricao.strip(), pasta))

    def tratar(self, respostas: Mapping[str, Path]) -> Etapa:
        """Responde às solicitações de tratamento com os arquivos tratados.

        Args:
            respostas: Arquivo tratado de cada solicitação, pelo id. Uma
                solicitação sem arquivo fica sem resposta.

        Raises:
            ErroAssistente: Se a etapa atual não for de solicitações, ou se o
                id não for de uma solicitação pendente.
        """
        sessao = self._exigir("solicitacoes")
        pendentes = {s.id for s in self._etapa.solicitacoes} if self._etapa else set()
        desconhecidas = sorted(set(respostas) - pendentes)
        if desconhecidas:
            raise ErroAssistente(f"Solicitações desconhecidas: {', '.join(desconhecidas)}")
        self._rodadas += 1
        pasta = self._raiz / f"tratados_{self._rodadas}"
        _copiar(list(respostas.values()), pasta)
        respondidas = {id_: arquivo.name for id_, arquivo in respostas.items()}
        return self._avancar(sessao.responder({"pasta": str(pasta), "respondidas": respondidas}))

    def responder_em_ordem(self, arquivos: Sequence[Path]) -> Etapa:
        """Responde às solicitações pendentes com os arquivos na ordem em que foram listadas.

        Raises:
            ErroAssistente: Se houver mais arquivos do que solicitações.
        """
        pendentes = self._etapa.solicitacoes if self._etapa else ()
        if len(arquivos) > len(pendentes):
            raise ErroAssistente(
                f"Foram enviados {len(arquivos)} arquivo(s) para {len(pendentes)} solicitação(ões)."
            )
        return self.tratar({s.id: a for s, a in zip(pendentes, arquivos, strict=False)})

    def confirmar(self, aceita: bool, observacao: str | None = None) -> Etapa:
        """Responde se o resultado faz sentido (ADR-011).

        Args:
            aceita: ``True`` se o resultado faz sentido para o usuário.
            observacao: O que falta ou está errado, em palavras do usuário;
                volta ao Interpretador.
        """
        sessao = self._exigir("confirmacao")
        resposta: dict[str, Any] = {"aceita": aceita}
        if not aceita and observacao and observacao.strip():
            resposta["observacao"] = observacao.strip()
        return self._avancar(sessao.responder(resposta))

    def resultado(self) -> Resultado:
        """Visão do estado atual da sessão.

        Raises:
            ErroAssistente: Se a sessão não começou.
        """
        if self._sessao is None:
            raise ErroAssistente("A sessão ainda não começou.")
        return _resultado(self._sessao.estado, self._configuracao)

    def _avisar(self, no: str) -> None:
        if self.ao_avancar is not None:
            self.ao_avancar(PASSOS.get(no, no))

    def _exigir(self, tipo: TipoEtapa) -> Sessao:
        if self._sessao is None or self._etapa is None or self._etapa.tipo != tipo:
            atual = self._etapa.tipo if self._etapa else "nenhuma"
            raise ErroAssistente(f"A etapa atual é {atual}, e não {tipo}.")
        return self._sessao

    def _avancar(self, passo: Interrupcao | Estado) -> Etapa:
        if not isinstance(passo, Interrupcao):
            self._etapa = Etapa("resultado")
        elif passo.tipo == "solicitacoes":
            solicitacoes = passo.conteudo.get("solicitacoes", [])
            self._etapa = Etapa(
                "solicitacoes", solicitacoes=tuple(map(Solicitacao.model_validate, solicitacoes))
            )
        else:
            self._etapa = Etapa("confirmacao", perguntas=tuple(passo.conteudo.get("perguntas", [])))
        return self._etapa


def _copiar(arquivos: Sequence[Path], pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for arquivo in arquivos:
        shutil.copyfile(arquivo, pasta / Path(arquivo).name)


def _resultado(estado: Estado, configuracao: ConfiguracaoExecucao) -> Resultado:
    resultado = estado.get("resultado")
    especificacao = estado.get("especificacao")
    modelo = estado.get("modelo")
    explicacao = estado.get("explicacao")
    formulacao = None
    if modelo is not None:
        try:
            formulacao = para_latex(compilar(modelo))
        except ErroCompilacao:
            formulacao = None
    chamadas = estado.get("chamadas", [])
    entrada = sum(c["uso"]["entrada"] for c in chamadas)
    cache = sum(c["uso"]["entrada_em_cache"] for c in chamadas)
    saida = sum(c["uso"]["saida"] for c in chamadas)
    perfil = carregar_perfil(configuracao.perfil_modelo)
    return Resultado(
        explicacao=explicacao.texto if explicacao else None,
        status=resultado.status.value if resultado else None,
        valor_objetivo=resultado.valor_objetivo if resultado else None,
        falha=estado.get("falha"),
        solucao=dict(resultado.valores) if resultado else {},
        especificacao=especificacao.model_dump(mode="json") if especificacao else None,
        modelo=modelo.model_dump(mode="json") if modelo else None,
        formulacao_latex=formulacao,
        pareceres=[p.model_dump(mode="json") for p in estado.get("pareceres", [])],
        chamadas_llm=len(chamadas),
        tokens_entrada=entrada,
        tokens_saida=saida,
        custo=perfil.custo(entrada, cache, saida),
        moeda=perfil.moeda,
        eventos=list(estado.get("eventos", [])),
    )
