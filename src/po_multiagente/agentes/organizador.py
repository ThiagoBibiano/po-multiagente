"""Organizador de dados: monta tabelas com os números que o usuário escreveu (ADR-015).

Só na conversa (interface de chat), antes do fluxo, e só quando o usuário não
tem planilhas. Os números do texto viram tabelas, que o usuário confere antes
de o fluxo começar; daí em diante, tudo segue como se ele tivesse enviado as
planilhas. O Organizador não faz parte do grafo nem do experimento.

Nenhum número é criado: cada número das tabelas precisa aparecer escrito nas
mensagens do usuário, o que o código confere; senão, a saída é recusada e
volta ao modelo com a lista dos números sem origem. O que o problema pede e o
texto não traz vai para ``faltantes``, que viram perguntas ao usuário.
"""

import re

from pydantic import Field, model_validator

from po_multiagente.agentes._comum import (
    ErroAgente,
    ErroFormato,
    Registro,
    gerar_estruturado,
)
from po_multiagente.dominio import ObjetoDominio
from po_multiagente.dominio._base import TextoNaoVazio
from po_multiagente.llm import ErroLLM, LLMPort
from po_multiagente.prompts import carregar_instrucao

NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
ARQUIVO = re.compile(r"^[a-z0-9_]+\.csv$")


class TabelaProposta(ObjetoDominio):
    """Uma tabela montada a partir do texto, com os valores como foram escritos."""

    arquivo: TextoNaoVazio
    descricao: TextoNaoVazio
    colunas: tuple[TextoNaoVazio, ...] = Field(min_length=1)
    linhas: tuple[tuple[str, ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _forma(self) -> "TabelaProposta":
        if not ARQUIVO.fullmatch(self.arquivo):
            raise ValueError(
                f"arquivo {self.arquivo!r}: use letras minúsculas, algarismos e _, "
                "terminando em .csv"
            )
        tamanhos = {len(linha) for linha in self.linhas}
        if tamanhos != {len(self.colunas)}:
            raise ValueError(
                f"{self.arquivo}: cada linha precisa ter {len(self.colunas)} valores, um por coluna"
            )
        return self


class DadosOrganizados(ObjetoDominio):
    """Saída do Organizador."""

    tabelas: tuple[TabelaProposta, ...] = ()
    faltantes: tuple[TextoNaoVazio, ...] = ()


def numeros_sem_origem(dados: DadosOrganizados, texto: str) -> list[str]:
    """Números das tabelas que não aparecem escritos no texto do usuário.

    Aceita o número com ou sem ponto de milhar (``1.500`` e ``1500``).
    """
    escritos = set(NUMERO.findall(texto))
    escritos |= {n.replace(".", "") for n in escritos}
    ausentes = [
        numero
        for tabela in dados.tabelas
        for linha in tabela.linhas
        for celula in linha
        for numero in NUMERO.findall(celula)
        if numero not in escritos
    ]
    return list(dict.fromkeys(ausentes))


class Organizador:
    """Monta tabelas com os dados escritos na conversa, sem criar número.

    Args:
        llm: Modelo de linguagem.
        max_tentativas: Tentativas antes de desistir (saída fora do esquema
            ou com número sem origem).
    """

    agente = "organizador"

    def __init__(self, llm: LLMPort, max_tentativas: int = 3) -> None:
        self._llm = llm
        self._max_tentativas = max_tentativas
        self._instrucao = carregar_instrucao(self.agente)

    def organizar(self, texto: str, registro: Registro) -> DadosOrganizados:
        """Tabelas e dados faltantes a partir das mensagens do usuário.

        Raises:
            ErroAgente: Se todas as tentativas forem recusadas.
        """
        base = f"# Mensagens do usuário\n\n{texto.strip()}"
        erros: list[str] = []
        while len(erros) < self._max_tentativas:
            entrada = base if not erros else f"{base}\n\n# Saída recusada\n\n{erros[-1]}"
            try:
                dados = gerar_estruturado(
                    self._llm, self._instrucao, entrada, DadosOrganizados, registro
                )
                self._conferir(dados, texto)
            except (ErroFormato, ErroLLM) as erro:
                erros.append(str(erro))
                continue
            return dados
        raise ErroAgente(self.agente, erros)

    @staticmethod
    def _conferir(dados: DadosOrganizados, texto: str) -> None:
        ausentes = numeros_sem_origem(dados, texto)
        if ausentes:
            raise ErroFormato(
                "Estes números não aparecem nas mensagens do usuário: "
                + ", ".join(ausentes)
                + ". Use só números escritos por ele; o que faltar vai em faltantes."
            )
        nomes = [t.arquivo for t in dados.tabelas]
        repetidos = sorted({n for n in nomes if nomes.count(n) > 1})
        if repetidos:
            raise ErroFormato(f"Arquivos repetidos: {', '.join(repetidos)}")
