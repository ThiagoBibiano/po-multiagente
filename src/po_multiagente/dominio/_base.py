"""Base comum dos objetos de domínio e tipos restritos compartilhados."""

from collections import Counter
from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class ObjetoDominio(BaseModel):
    """Base de todos os objetos de domínio: imutáveis e estritos.

    Imutáveis porque cada objeto é um artefato registrado no dossiê (R5): uma
    correção gera um objeto novo e nunca altera um já registrado. Estritos
    (``extra="forbid"``) porque o Interpretador e o Modelador produzem esses
    objetos por saída estruturada; um campo inesperado é erro do modelo de
    linguagem e deve aparecer, e não ser descartado em silêncio.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
        validate_default=True,
    )


Identificador = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=64)
]
"""Nome simbólico do modelo: conjunto, parâmetro, variável, restrição ou índice."""

IdRequisito = Annotated[str, StringConstraints(pattern=r"^REQ[1-9][0-9]*$")]
"""Identificador de requisito de negócio (``REQ1``, ``REQ2``, ...)."""

TextoNaoVazio = Annotated[str, StringConstraints(min_length=1)]
"""Texto livre com ao menos um caractere além de espaços."""

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
"""Resumo SHA-256 em hexadecimal minúsculo."""


def exigir_unicos(valores: Iterable[str], contexto: str) -> None:
    """Falha se algum valor aparecer mais de uma vez.

    Args:
        valores: Valores que devem ser únicos.
        contexto: Descrição usada na mensagem de erro.

    Raises:
        ValueError: Se houver repetidos; a mensagem lista todos.
    """
    repetidos = sorted(v for v, n in Counter(valores).items() if n > 1)
    if repetidos:
        raise ValueError(f"{contexto} com repetição: {', '.join(repetidos)}")


def exigir_declarados(usados: Iterable[str], declarados: Iterable[str], contexto: str) -> None:
    """Falha se algum valor usado não estiver entre os declarados.

    Args:
        usados: Referências encontradas.
        declarados: Referências válidas.
        contexto: Descrição usada na mensagem de erro.

    Raises:
        ValueError: Se houver referência não declarada; a mensagem lista todas.
    """
    faltantes = sorted(set(usados) - set(declarados))
    if faltantes:
        raise ValueError(f"{contexto} sem declaração: {', '.join(faltantes)}")
