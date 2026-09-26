"""Fontes de dados do usuário e origem de cada valor usado no modelo."""

from enum import StrEnum

from pydantic import Field, model_validator

from po_multiagente.dominio._base import (
    Identificador,
    ObjetoDominio,
    Sha256,
    TextoNaoVazio,
    exigir_unicos,
)


class TipoColuna(StrEnum):
    """Tipo inferido de uma coluna na leitura da fonte."""

    INTEIRO = "inteiro"
    DECIMAL = "decimal"
    TEXTO = "texto"
    DATA = "data"
    BOOLEANO = "booleano"


class Coluna(ObjetoDominio):
    """Coluna de uma fonte, com o nome em vocabulário operacional do usuário."""

    nome: TextoNaoVazio
    tipo: TipoColuna


class FonteDados(ObjetoDominio):
    """Arquivo de dados fornecido pelo usuário, como foi lido.

    O hash registra o conteúdo exato; conferido no início e no fim da
    execução, prova que o artefato não alterou o arquivo.
    """

    arquivo: TextoNaoVazio
    sha256: Sha256
    colunas: tuple[Coluna, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _colunas_unicas(self) -> "FonteDados":
        exigir_unicos((c.nome for c in self.colunas), f"Colunas de {self.arquivo!r}")
        return self


class Filtro(ObjetoDominio):
    """Seleção de linhas: só as linhas em que ``coluna`` vale ``valor``.

    Endereça o dado sem transformá-lo, como numa tabela "longa" em que a
    disponibilidade de cada recurso está na linha daquele recurso.
    """

    coluna: TextoNaoVazio
    valor: TextoNaoVazio


class Origem(ObjetoDominio):
    """De onde vêm os valores de um parâmetro ou os membros de um conjunto.

    Attributes:
        arquivo: Fonte que contém os valores.
        coluna: Coluna com os valores.
        chaves: Colunas que indexam os valores, na ordem dos índices; vazio
            para um valor escalar ou para os membros de um conjunto.
        filtros: Linhas consideradas; vazio para todas. Um parâmetro escalar
            numa tabela com várias linhas é a célula que os filtros isolam.
        solicitacao_id: Solicitação de tratamento que originou o arquivo,
            quando o dado não estava disponível diretamente.
    """

    arquivo: TextoNaoVazio
    coluna: TextoNaoVazio
    chaves: tuple[TextoNaoVazio, ...] = ()
    filtros: tuple[Filtro, ...] = ()
    solicitacao_id: Identificador | None = None
