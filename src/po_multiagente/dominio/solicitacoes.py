"""Solicitações de tratamento de dados dirigidas ao usuário."""

from enum import StrEnum

from pydantic import AwareDatetime

from po_multiagente.dominio._base import Identificador, ObjetoDominio, Sha256, TextoNaoVazio


class MotivoTratamento(StrEnum):
    """Por que um parâmetro não pode ser lido diretamente da fonte."""

    GRANULARIDADE = "granularidade"
    UNIDADE = "unidade"
    IDENTIFICADOR = "identificador"
    JUNCAO = "juncao"
    FALTANTE = "faltante"


class Solicitacao(ObjetoDominio):
    """Pedido ao usuário para tratar um dado.

    Trata sempre do dado — arquivo, coluna e forma esperada — e nunca pede ao
    usuário que julgue a formulação matemática (cap. 3, Interpretador).

    Attributes:
        coluna: Coluna envolvida; ``None`` quando ela não existe na fonte.
    """

    id: Identificador
    parametro_id: Identificador
    arquivo: TextoNaoVazio
    coluna: TextoNaoVazio | None
    motivo: MotivoTratamento
    forma_esperada: TextoNaoVazio


class RespostaSolicitacao(ObjetoDominio):
    """Arquivo tratado pelo usuário em resposta a uma solicitação."""

    solicitacao_id: Identificador
    arquivo_tratado: TextoNaoVazio
    sha256: Sha256
    respondida_em: AwareDatetime
