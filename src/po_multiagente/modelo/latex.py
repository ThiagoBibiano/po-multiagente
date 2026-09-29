"""Formulação do modelo em LaTeX, para leitura humana (R5).

Gera um bloco ``aligned`` compatível com KaTeX e MathJax, que a interface
exibe e o dossiê guarda. A renderização parte da árvore sintática, e não do
texto, para que o que o usuário lê seja exatamente o que foi compilado.
"""

import re

from po_multiagente.dominio import Sentido, TipoVariavel, Variavel
from po_multiagente.modelo.arvore import (
    Binaria,
    Comparacao,
    Expressao,
    Indice,
    IndiceLivre,
    Negacao,
    Numero,
    Operador,
    Referencia,
    Relacao,
    Somatorio,
)
from po_multiagente.modelo.compilacao import ModeloCompilado

_RELACOES = {
    Relacao.MENOR_OU_IGUAL: r"\le",
    Relacao.MAIOR_OU_IGUAL: r"\ge",
    Relacao.IGUAL: "=",
}
_LETRAS_INDICE = ("i", "j", "k", "l", "m", "n")
_ESPECIAIS_TEXTO = re.compile(r"[\\{}$&#^_%~]")
_ESCAPES = {"\\": r"\textbackslash{}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def para_latex(compilado: ModeloCompilado) -> str:
    """Formulação completa: objetivo, restrições (com seus ids) e domínios."""
    ir = compilado.ir
    operador = r"\max" if ir.objetivo.sentido is Sentido.MAXIMIZAR else r"\min"
    linhas = [rf"{operador} \quad & {_expressao(compilado.objetivo)} && \\"]
    for posicao, restricao in enumerate(compilado.restricoes):
        rotulo = r"\text{sujeito a} \quad " if posicao == 0 else ""
        para_todo = ", ".join(
            rf"{_nome(q.indice)} \in {_conjunto(q.conjunto)}" for q in restricao.restricao.para_todo
        )
        quantificador = rf"\forall\, {para_todo} \quad " if para_todo else ""
        linhas.append(
            rf"{rotulo}& {_comparacao(restricao.comparacao)} && {quantificador}"
            rf"\text{{({_texto(restricao.restricao.id)})}} \\"
        )
    linhas.extend(
        rf"& {dominio} && {percorre} \\" for dominio, percorre in map(_dominio, ir.variaveis)
    )
    return "\\begin{aligned}\n" + "\n".join(linhas) + "\n\\end{aligned}"


def expressao_latex(expressao: Expressao | Comparacao) -> str:
    """Uma expressão ou restrição isolada em LaTeX."""
    if isinstance(expressao, Comparacao):
        return _comparacao(expressao)
    return _expressao(expressao)


def _comparacao(comparacao: Comparacao) -> str:
    return (
        f"{_expressao(comparacao.esquerda)} {_RELACOES[comparacao.relacao]} "
        f"{_expressao(comparacao.direita)}"
    )


def _expressao(expressao: Expressao, contexto: int = 0) -> str:
    """LaTeX da expressão; ``contexto`` é a precedência mínima sem parênteses."""
    match expressao:
        case Numero(valor):
            return _numero(valor)
        case Referencia(nome, indices):
            return _referencia(nome, indices)
        case Somatorio(corpo, geradores):
            somas = "".join(
                rf"\sum_{{{_nome(g.indice)} \in {_conjunto(g.conjunto)}}} " for g in geradores
            )
            # Como o sinal de menos, o somatório se estende ao termo à sua direita.
            return _parenteses(somas + _expressao(corpo, 2), 3, contexto)
        case Negacao(operando):
            return _parenteses("-" + _expressao(operando, 3), 3, contexto)
        case Binaria(Operador.DIVISAO, esquerda, direita):
            return rf"\frac{{{_expressao(esquerda)}}}{{{_expressao(direita)}}}"
        case Binaria(Operador.PRODUTO, esquerda, direita):
            separador = r" \cdot " if isinstance(direita, Numero) else r"\, "
            return _parenteses(
                _expressao(esquerda, 2) + separador + _expressao(direita, 3), 2, contexto
            )
        case Binaria(operador, esquerda, direita):
            return _parenteses(
                f"{_expressao(esquerda, 1)} {operador.value} {_expressao(direita, 2)}", 1, contexto
            )


def _parenteses(latex: str, precedencia: int, contexto: int) -> str:
    return rf"\left( {latex} \right)" if precedencia < contexto else latex


def _referencia(nome: str, indices: tuple[Indice, ...]) -> str:
    if not indices:
        return _nome(nome)
    subscritos = ",".join(
        _nome(i.nome) if isinstance(i, IndiceLivre) else rf"\text{{{_texto(i.texto)}}}"
        for i in indices
    )
    return f"{_nome(nome)}_{{{subscritos}}}"


def _dominio(variavel: Variavel) -> tuple[str, str]:
    """Domínio da variável e, se indexada, o quantificador sobre seus índices."""
    letras = [
        _LETRAS_INDICE[n] if n < len(_LETRAS_INDICE) else f"i_{{{n + 1}}}"
        for n in range(len(variavel.indices))
    ]
    simbolo = f"{_nome(variavel.id)}_{{{','.join(letras)}}}" if letras else _nome(variavel.id)
    inferior, superior = variavel.limite_inferior, variavel.limite_superior
    if variavel.tipo is TipoVariavel.BINARIA:
        dominio = rf"{simbolo} \in \{{0, 1\}}"
    elif inferior is not None and superior is not None:
        dominio = rf"{_numero(inferior)} \le {simbolo} \le {_numero(superior)}"
    elif inferior is not None:
        dominio = rf"{simbolo} \ge {_numero(inferior)}"
    elif superior is not None:
        dominio = rf"{simbolo} \le {_numero(superior)}"
    else:
        dominio = rf"{simbolo} \in \mathbb{{R}}"
    if variavel.tipo is TipoVariavel.INTEIRA:
        dominio += rf",\ {simbolo} \in \mathbb{{Z}}"
    percorre = ", ".join(
        rf"{letra} \in {_conjunto(c)}" for letra, c in zip(letras, variavel.indices, strict=True)
    )
    return dominio, rf"\forall\, {percorre}" if percorre else ""


def _nome(identificador: str) -> str:
    if len(identificador) == 1:
        return identificador
    return r"\mathit{" + _texto(identificador) + "}"


def _conjunto(identificador: str) -> str:
    return r"\mathrm{" + _texto(identificador) + "}"


def _numero(valor: float) -> str:
    texto = str(int(valor)) if valor.is_integer() else repr(valor)
    return texto.replace(".", "{,}")


def _texto(texto: str) -> str:
    return _ESPECIAIS_TEXTO.sub(lambda m: _ESCAPES.get(m[0], "\\" + m[0]), texto)
