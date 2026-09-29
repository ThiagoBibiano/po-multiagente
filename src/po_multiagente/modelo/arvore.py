"""Árvore sintática das expressões algébricas da representação intermediária.

Nós imutáveis, produzidos pela gramática (``gramatica``) e consumidos pela
checagem, pela instanciação, pelas unidades e pela renderização em LaTeX.
"""

from dataclasses import dataclass
from enum import StrEnum


class Operador(StrEnum):
    """Operador aritmético binário."""

    SOMA = "+"
    SUBTRACAO = "-"
    PRODUTO = "*"
    DIVISAO = "/"


class Relacao(StrEnum):
    """Relação de uma restrição. Desigualdades estritas não existem em PL."""

    MENOR_OU_IGUAL = "<="
    MAIOR_OU_IGUAL = ">="
    IGUAL = "=="


@dataclass(frozen=True)
class Numero:
    """Constante numérica escrita na expressão."""

    valor: float


@dataclass(frozen=True)
class IndiceLivre:
    """Índice ligado por ``para_todo`` ou por um somatório, como ``p`` em ``x[p]``."""

    nome: str


@dataclass(frozen=True)
class Membro:
    """Membro fixo de um conjunto, como ``"Loja A"`` em ``x["Loja A"]``."""

    texto: str


Indice = IndiceLivre | Membro


@dataclass(frozen=True)
class Referencia:
    """Uso de um parâmetro ou de uma variável, com seus índices."""

    nome: str
    indices: tuple[Indice, ...] = ()


@dataclass(frozen=True)
class Gerador:
    """Cláusula ``for indice in conjunto`` de um somatório."""

    indice: str
    conjunto: str


@dataclass(frozen=True)
class Somatorio:
    """``sum(corpo for i in I for j in J)``."""

    corpo: "Expressao"
    geradores: tuple[Gerador, ...]


@dataclass(frozen=True)
class Binaria:
    """Operação aritmética entre duas expressões."""

    operador: Operador
    esquerda: "Expressao"
    direita: "Expressao"


@dataclass(frozen=True)
class Negacao:
    """Troca de sinal: ``-expressao``."""

    operando: "Expressao"


Expressao = Numero | Referencia | Somatorio | Binaria | Negacao


@dataclass(frozen=True)
class Comparacao:
    """Restrição: duas expressões ligadas por uma relação."""

    esquerda: Expressao
    relacao: Relacao
    direita: Expressao


_PRECEDENCIA = {
    Operador.SOMA: 1,
    Operador.SUBTRACAO: 1,
    Operador.PRODUTO: 2,
    Operador.DIVISAO: 2,
}
_PRECEDENCIA_NEGACAO = 3
_PRECEDENCIA_ATOMO = 4


def texto(no: Expressao | Comparacao) -> str:
    """Escreve o nó na mini-linguagem, com o mínimo de parênteses.

    Usado para localizar erros: a mensagem cita o trecho exato em que o
    problema está.
    """
    if isinstance(no, Comparacao):
        return f"{texto(no.esquerda)} {no.relacao.value} {texto(no.direita)}"
    return _texto(no)


def formatar_numero(valor: float) -> str:
    """Escreve um número sem casas decimais supérfluas (``200``, e não ``200.0``)."""
    return str(int(valor)) if valor.is_integer() else repr(valor)


def _texto(no: Expressao) -> str:
    match no:
        case Numero(valor):
            return formatar_numero(valor)
        case Referencia(nome, ()):
            return nome
        case Referencia(nome, indices):
            return f"{nome}[{', '.join(_texto_indice(i) for i in indices)}]"
        case Somatorio(corpo, geradores):
            clausulas = " ".join(f"for {g.indice} in {g.conjunto}" for g in geradores)
            return f"sum({_texto(corpo)} {clausulas})"
        case Negacao(operando):
            return f"-{_entre_parenteses(operando, _PRECEDENCIA_NEGACAO)}"
        case Binaria(operador, esquerda, direita):
            precedencia = _PRECEDENCIA[operador]
            # Os operadores associam à esquerda; à direita, a mesma precedência exige
            # parênteses para preservar a árvore: a - (b - c), e também a + (b + c).
            return (
                f"{_entre_parenteses(esquerda, precedencia)} {operador.value} "
                f"{_entre_parenteses(direita, precedencia + 1)}"
            )


def _entre_parenteses(no: Expressao, minima: int) -> str:
    return f"({_texto(no)})" if _precedencia(no) < minima else _texto(no)


def _precedencia(no: Expressao) -> int:
    if isinstance(no, Binaria):
        return _PRECEDENCIA[no.operador]
    if isinstance(no, Negacao):
        return _PRECEDENCIA_NEGACAO
    return _PRECEDENCIA_ATOMO


def _texto_indice(indice: Indice) -> str:
    return indice.nome if isinstance(indice, IndiceLivre) else f'"{indice.texto}"'
