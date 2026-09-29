"""Gramática da mini-linguagem algébrica (ADR-002).

Expressões lineares indexadas, na sintaxe de Python que os modelos de
linguagem já conhecem::

    sum(custo[i, j] * x[i, j] for i in ORIGENS for j in DESTINOS)
    sum(x[i, j] for i in ORIGENS) >= demanda[j]
    x["Loja A"] <= 0.5 * capacidade

A gramática aceita qualquer expressão aritmética; a checagem de nomes,
índices e linearidade fica na compilação (``compilacao``), que localiza o
erro com mais precisão do que o analisador sintático.
"""

from functools import cache
from typing import cast

from lark import Lark, Token, Transformer, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

from po_multiagente.modelo.arvore import (
    Binaria,
    Comparacao,
    Expressao,
    Gerador,
    Indice,
    IndiceLivre,
    Membro,
    Negacao,
    Numero,
    Operador,
    Referencia,
    Relacao,
    Somatorio,
)

PALAVRAS_RESERVADAS = frozenset({"sum", "for", "in"})
"""Palavras da gramática que não podem ser nome de conjunto, parâmetro ou variável."""

_GRAMATICA = r"""
    ?expressao: soma
    comparacao: soma RELACAO soma

    ?soma: produto
         | soma "+" produto   -> adicao
         | soma "-" produto   -> subtracao
    ?produto: unario
            | produto "*" unario  -> multiplicacao
            | produto "/" unario  -> divisao
    ?unario: "-" unario  -> negacao
           | "+" unario
           | atomo
    ?atomo: NUMERO  -> numero
          | referencia
          | somatorio
          | "(" soma ")"

    somatorio: "sum" "(" soma gerador+ ")"
    gerador: "for" NOME "in" NOME
    referencia: NOME ("[" indice ("," indice)* "]")?
    ?indice: NOME   -> indice_livre
           | TEXTO  -> membro

    RELACAO: "<=" | ">=" | "=="
    NUMERO: /(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?/
    TEXTO: /"[^"\n]*"/ | /'[^'\n]*'/
    NOME: /[A-Za-z_][A-Za-z0-9_]*/

    %import common.WS
    %ignore WS
"""

_NOMES_TERMINAIS = {
    "RELACAO": "<=, >= ou ==",
    "NUMERO": "número",
    "TEXTO": "membro entre aspas",
    "NOME": "nome",
    "LPAR": "(",
    "RPAR": ")",
    "LSQB": "[",
    "RSQB": "]",
    "COMMA": ",",
    "PLUS": "+",
    "MINUS": "-",
    "STAR": "*",
    "SLASH": "/",
    "SUM": "sum",
    "FOR": "for",
    "IN": "in",
    "$END": "fim da expressão",
}


class ErroSintaxe(ValueError):
    """Texto fora da gramática, com a posição (coluna, a partir de 1) do erro."""

    def __init__(self, mensagem: str, coluna: int | None) -> None:
        super().__init__(mensagem)
        self.coluna = coluna


def analisar_expressao(texto: str) -> Expressao:
    """Converte uma expressão (a função objetivo, por exemplo) em árvore.

    Raises:
        ErroSintaxe: Se o texto não seguir a gramática.
    """
    arvore = _analisar(texto, "expressao")
    assert not isinstance(arvore, Comparacao)
    return arvore


def analisar_comparacao(texto: str) -> Comparacao:
    """Converte uma restrição (``expressão relação expressão``) em árvore.

    Raises:
        ErroSintaxe: Se o texto não seguir a gramática.
    """
    arvore = _analisar(texto, "comparacao")
    assert isinstance(arvore, Comparacao)
    return arvore


@cache
def _analisador() -> Lark:
    return Lark(
        _GRAMATICA,
        start=["expressao", "comparacao"],
        parser="lalr",
        transformer=_ParaArvore(),
        maybe_placeholders=False,
    )


def _analisar(texto: str, inicio: str) -> Expressao | Comparacao:
    try:
        # Com o transformador embutido, o Lark devolve os nós de `arvore`.
        return cast("Expressao | Comparacao", _analisador().parse(texto, start=inicio))
    except UnexpectedInput as erro:
        raise _traduzir(erro, texto) from None


def _traduzir(erro: UnexpectedInput, texto: str) -> ErroSintaxe:
    """Converte o erro do Lark numa mensagem em português, com dica quando possível."""
    coluna = erro.column if isinstance(erro.column, int) and erro.column > 0 else None
    if isinstance(erro, UnexpectedCharacters):
        inicio = erro.pos_in_stream or 0
        trecho = texto[inicio : inicio + 2]
        if trecho[:1] in "<>" and trecho[1:2] != "=":
            dica = "desigualdade estrita não existe em PL; use <= ou >="
        elif trecho[:1] == "=":
            dica = "para igualdade, use =="
        else:
            dica = f"caractere {erro.char!r} não pertence à linguagem"
        return ErroSintaxe(f"Erro de sintaxe na coluna {coluna}: {dica}", coluna)
    if isinstance(erro, UnexpectedEOF | UnexpectedToken):
        esperado = sorted({_NOMES_TERMINAIS.get(t, t) for t in erro.expected})
        token = getattr(erro, "token", None)
        if isinstance(erro, UnexpectedEOF) or (isinstance(token, Token) and token.type == "$END"):
            achado = "a expressão terminou antes do esperado"
            coluna = len(texto) + 1
        else:
            achado = f"encontrado {str(token)!r}"
        return ErroSintaxe(
            f"Erro de sintaxe na coluna {coluna}: {achado}; esperado {', '.join(esperado)}",
            coluna,
        )
    return ErroSintaxe(f"Erro de sintaxe: {erro}", coluna)  # pragma: no cover


@v_args(inline=True)
class _ParaArvore(Transformer[Token, Expressao | Comparacao]):
    """Converte a árvore do Lark nos nós de ``arvore``."""

    def numero(self, token: Token) -> Numero:
        return Numero(float(token))

    def indice_livre(self, token: Token) -> IndiceLivre:
        return IndiceLivre(str(token))

    def membro(self, token: Token) -> Membro:
        return Membro(str(token)[1:-1])

    def referencia(self, nome: Token, *indices: Indice) -> Referencia:
        return Referencia(str(nome), tuple(indices))

    def gerador(self, indice: Token, conjunto: Token) -> Gerador:
        return Gerador(str(indice), str(conjunto))

    def somatorio(self, corpo: Expressao, *geradores: Gerador) -> Somatorio:
        return Somatorio(corpo, tuple(geradores))

    def negacao(self, operando: Expressao) -> Negacao:
        return Negacao(operando)

    def adicao(self, esquerda: Expressao, direita: Expressao) -> Binaria:
        return Binaria(Operador.SOMA, esquerda, direita)

    def subtracao(self, esquerda: Expressao, direita: Expressao) -> Binaria:
        return Binaria(Operador.SUBTRACAO, esquerda, direita)

    def multiplicacao(self, esquerda: Expressao, direita: Expressao) -> Binaria:
        return Binaria(Operador.PRODUTO, esquerda, direita)

    def divisao(self, esquerda: Expressao, direita: Expressao) -> Binaria:
        return Binaria(Operador.DIVISAO, esquerda, direita)

    def comparacao(self, esquerda: Expressao, relacao: Token, direita: Expressao) -> Comparacao:
        return Comparacao(esquerda, Relacao(str(relacao)), direita)
