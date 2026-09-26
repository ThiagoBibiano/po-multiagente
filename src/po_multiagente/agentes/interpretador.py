"""Interpretador: pedido e fontes → quadro de especificação e solicitações de tratamento."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import Field, ValidationError

from po_multiagente.agentes._comum import (
    ErroAgente,
    ErroFormato,
    Registro,
    bloco_json,
    descrever_fontes,
    formatar_erros_validacao,
    gerar_estruturado,
)
from po_multiagente.dados import ErroDados, Fontes, valores
from po_multiagente.dominio import (
    AlertaAmbiguidade,
    Especificacao,
    ObjetoDominio,
    Parametro,
    Requisito,
    Sentido,
    Solicitacao,
)
from po_multiagente.dominio._base import TextoNaoVazio
from po_multiagente.llm import LLMPort
from po_multiagente.prompts import carregar_instrucao


class SaidaInterpretador(ObjetoDominio):
    """O que o modelo produz; as fontes são preenchidas pelo inventário."""

    decisao: TextoNaoVazio
    criterio: TextoNaoVazio
    sentido: Sentido
    requisitos: tuple[Requisito, ...] = Field(min_length=1)
    parametros: tuple[Parametro, ...]
    solicitacoes: tuple[Solicitacao, ...]
    premissas: tuple[TextoNaoVazio, ...]
    nao_considerado: tuple[TextoNaoVazio, ...]
    alertas: tuple[AlertaAmbiguidade, ...]


@dataclass(frozen=True)
class Rodada:
    """Contexto de uma rodada de especificação depois da primeira.

    Attributes:
        anterior: Quadro da rodada anterior, a atualizar.
        respondidas: Solicitação → arquivo tratado recebido.
        observacao_usuario: Resposta do gestor a uma pergunta sobre o
            resultado (ADR-011).
    """

    anterior: Especificacao | None = None
    respondidas: Mapping[str, str] = field(default_factory=dict)
    observacao_usuario: str | None = None


@dataclass(frozen=True)
class ResultadoInterpretador:
    """Quadro de especificação e as solicitações ainda sem resposta."""

    especificacao: Especificacao
    pendentes: tuple[Solicitacao, ...]
    tentativas: int


class Interpretador:
    """Agente Interpretador (cap. 3, Passo 3).

    O modelo propõe o quadro; o código confere cada origem lendo os dados.
    Um parâmetro ilegível por motivo de dado (granularidade, unidade...) sem
    solicitação ganha uma solicitação automática; uma origem inexistente
    volta ao modelo como erro.

    Args:
        llm: Modelo de linguagem.
        max_tentativas: Tentativas por chamada até o quadro ser aceito.
    """

    agente = "interpretador"

    def __init__(self, llm: LLMPort, max_tentativas: int = 3) -> None:
        self._llm = llm
        self._max_tentativas = max_tentativas
        self._instrucao = carregar_instrucao(self.agente)

    def especificar(
        self,
        descricao: str,
        fontes: Fontes,
        registro: Registro,
        rodada: Rodada | None = None,
    ) -> ResultadoInterpretador:
        """Produz o quadro de especificação.

        Args:
            descricao: Pedido do gestor.
            fontes: Fontes atuais, incluindo arquivos tratados já recebidos.
            registro: Onde registrar as chamadas.
            rodada: Contexto das rodadas seguintes; ``None`` na primeira.

        Raises:
            ErroAgente: Se as tentativas se esgotarem.
        """
        rodada = rodada or Rodada()
        respondidas = dict(rodada.respondidas)
        base = self._entrada(descricao, fontes, rodada)
        mensagens: list[str] = []
        for tentativa in range(1, self._max_tentativas + 1):
            entrada = (
                base if not mensagens else f"{base}\n\n# Correções necessárias\n\n{mensagens[-1]}"
            )
            try:
                saida = gerar_estruturado(
                    self._llm, self._instrucao, entrada, SaidaInterpretador, registro
                )
                especificacao = self._montar(saida, fontes)
                especificacao = self._conferir_dados(especificacao, fontes, respondidas)
            except ErroFormato as erro:
                mensagens.append(str(erro))
                continue
            pendentes = tuple(s for s in especificacao.solicitacoes if s.id not in respondidas)
            return ResultadoInterpretador(especificacao, pendentes, tentativa)
        raise ErroAgente(self.agente, mensagens)

    @staticmethod
    def _entrada(descricao: str, fontes: Fontes, rodada: Rodada) -> str:
        partes = [
            f"# Pedido do gestor\n\n{descricao}",
            f"# Inventário das fontes\n\n{descrever_fontes(fontes)}",
        ]
        if rodada.anterior is not None:
            quadro = rodada.anterior.model_dump(mode="json", exclude={"fontes"})
            partes.append(bloco_json("Quadro anterior", quadro))
        if rodada.respondidas:
            linhas = "\n".join(f"- `{s}` → `{a}`" for s, a in rodada.respondidas.items())
            partes.append(f"# Arquivos tratados recebidos do gestor\n\n{linhas}")
        if rodada.observacao_usuario:
            partes.append(
                f"# Observação do gestor sobre o resultado anterior\n\n{rodada.observacao_usuario}"
            )
        return "\n\n".join(partes)

    @staticmethod
    def _montar(saida: SaidaInterpretador, fontes: Fontes) -> Especificacao:
        try:
            return Especificacao(**dict(saida), fontes=fontes.inventario())
        except ValidationError as erro:
            raise ErroFormato(formatar_erros_validacao(erro)) from erro

    @staticmethod
    def _conferir_dados(
        especificacao: Especificacao, fontes: Fontes, respondidas: Mapping[str, str]
    ) -> Especificacao:
        """Lê cada parâmetro; cria solicitações para falhas de dado sem pedido."""
        com_pedido = {s.parametro_id for s in especificacao.solicitacoes if s.id not in respondidas}
        novas: list[Solicitacao] = []
        erros: list[str] = []
        for parametro in especificacao.parametros:
            if parametro.id in com_pedido:
                continue
            origem = parametro.origem
            try:
                tabela = fontes.tabela(origem.arquivo)
            except ErroDados as erro:
                erros.append(f"- parâmetro {parametro.id}: {erro}")
                continue
            referidas = (origem.coluna, *origem.chaves, *(f.coluna for f in origem.filtros))
            ausentes = [c for c in referidas if c not in tabela.colunas]
            if ausentes:
                # Coluna inexistente é referência errada do modelo, e não dado a tratar.
                erros.append(
                    f"- parâmetro {parametro.id}: {origem.arquivo!r} não tem a(s) coluna(s) "
                    f"{', '.join(repr(c) for c in ausentes)}; colunas: "
                    f"{', '.join(repr(c) for c in tabela.colunas)}"
                )
                continue
            try:
                valores(tabela, origem.coluna, origem.chaves, origem.filtros)
            except ErroDados as erro:
                if erro.motivo is None or erro.arquivo is None:
                    erros.append(f"- parâmetro {parametro.id}: {erro}")
                    continue
                novas.append(
                    Solicitacao(
                        id=f"auto_{parametro.id}",
                        parametro_id=parametro.id,
                        arquivo=erro.arquivo,
                        coluna=erro.coluna,
                        motivo=erro.motivo,
                        forma_esperada=f"{erro}. Envie o dado corrigido, uma linha por chave.",
                    )
                )
        if erros:
            raise ErroFormato("Origens inválidas:\n" + "\n".join(erros))
        if not novas:
            return especificacao
        return especificacao.model_copy(
            update={"solicitacoes": (*especificacao.solicitacoes, *novas)}
        )
