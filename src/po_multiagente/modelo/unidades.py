"""Unidades de medida e checagem dimensional das expressões (base do sinal S2).

Uma unidade é um produto de símbolos com expoentes inteiros: ``R$/un`` é
``R$¹·un⁻¹``. Não há conversão entre símbolos — ``km`` e ``m`` são
diferentes —, porque converter unidade é tratamento de dado, e o artefato
não transforma dados. A checagem só verifica se as unidades fecham.

Constantes escritas na expressão (``<= 200``) não têm unidade declarada:
somadas ou comparadas, assumem a unidade do outro lado; multiplicando,
contam como adimensionais.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from po_multiagente.modelo.arvore import (
    Binaria,
    Comparacao,
    Expressao,
    Negacao,
    Numero,
    Operador,
    Referencia,
    Somatorio,
    texto,
)
from po_multiagente.modelo.compilacao import ModeloCompilado
from po_multiagente.modelo.erros import OBJETIVO, ErroModelo

_ADIMENSIONAIS = frozenset({"", "1", "-", "adimensional", "sem unidade"})

_SINONIMOS = {
    sinonimo: canonico
    for canonico, sinonimos in {
        "un": ("un", "unid", "und", "unidade", "unidades"),
        "h": ("h", "hr", "hrs", "hora", "horas"),
        "min": ("min", "minuto", "minutos"),
        "dia": ("dia", "dias"),
        "mês": ("mês", "mes", "meses"),
        "R$": ("r$", "real", "reais", "brl"),
        "kg": ("kg", "quilo", "quilos", "quilograma", "quilogramas"),
        "t": ("t", "ton", "tonelada", "toneladas"),
        "L": ("l", "litro", "litros"),
        "km": ("km", "quilômetro", "quilômetros", "quilometro", "quilometros"),
    }.items()
    for sinonimo in sinonimos
}
"""Grafias comuns de um mesmo símbolo, sem distinguir maiúsculas."""

_SOBRESCRITOS = {"²": 2, "³": 3}
_TOKEN = re.compile(r"\(|\)|[*·]|/|\^-?\d+|[²³]|[^\s*·/()^²³]+")


@dataclass(frozen=True)
class Unidade:
    """Produto de símbolos com expoentes inteiros não nulos, em ordem canônica."""

    expoentes: tuple[tuple[str, int], ...] = ()

    @classmethod
    def de(cls, expoentes: Mapping[str, int]) -> "Unidade":
        """Cria a unidade descartando expoentes nulos."""
        return cls(tuple(sorted((s, e) for s, e in expoentes.items() if e != 0)))

    def __mul__(self, outra: "Unidade") -> "Unidade":
        """Produto: soma os expoentes."""
        total = Counter(dict(self.expoentes))
        total.update(dict(outra.expoentes))
        return Unidade.de(total)

    def __truediv__(self, outra: "Unidade") -> "Unidade":
        """Quociente: subtrai os expoentes."""
        total = Counter(dict(self.expoentes))
        total.subtract(dict(outra.expoentes))
        return Unidade.de(total)

    def __pow__(self, expoente: int) -> "Unidade":
        """Potência inteira."""
        return Unidade.de({s: e * expoente for s, e in self.expoentes})

    def __str__(self) -> str:
        """Notação legível: ``R$/un``, ``R$/(t·km)``, ``m^2``, ``adimensional``."""
        if not self.expoentes:
            return "adimensional"
        numerador = "·".join(_potencia(s, e) for s, e in self.expoentes if e > 0) or "1"
        denominador = [_potencia(s, -e) for s, e in self.expoentes if e < 0]
        if not denominador:
            return numerador
        if len(denominador) == 1:
            return f"{numerador}/{denominador[0]}"
        return f"{numerador}/({'·'.join(denominador)})"


ADIMENSIONAL = Unidade()


def ler_unidade(texto_unidade: str) -> Unidade:
    """Lê a notação de uma unidade.

    Aceita ``*``, ``·`` ou espaço para produto; ``/`` para quociente (tudo o
    que vem depois de ``/``, até o próximo ``/``, é denominador: ``R$/t·km``
    é real por tonelada-quilômetro); parênteses; e expoentes ``^2``, ``²`` e
    ``³``.

    Raises:
        ValueError: Se a notação for inválida.
    """
    normalizado = texto_unidade.strip()
    if normalizado.lower() in _ADIMENSIONAIS:
        return ADIMENSIONAL
    tokens = _TOKEN.findall(normalizado)
    if "".join(tokens) != re.sub(r"\s+", "", normalizado):
        raise ValueError(f"unidade {texto_unidade!r} com caractere inválido")
    leitor = _LeitorUnidade(tokens, texto_unidade)
    unidade = leitor.quociente()
    if leitor.restante:
        raise ValueError(f"unidade {texto_unidade!r} inválida perto de {leitor.restante[0]!r}")
    return unidade


def verificar_unidades(
    compilado: ModeloCompilado, unidades_parametros: Mapping[str, str]
) -> tuple[ErroModelo, ...]:
    """Localiza os termos cujas unidades não fecham.

    Args:
        compilado: Modelo checado.
        unidades_parametros: Unidade declarada de cada parâmetro, no quadro de
            especificação. Um parâmetro sem unidade declarada não é checado
            (a falta de origem é o sinal S3).

    Returns:
        Os erros, localizados na restrição, na função objetivo ou na
        declaração com unidade ilegível; vazio quando tudo fecha.
    """
    unidades, erros = _unidades_declaradas(compilado, unidades_parametros)
    verificador = _Verificador(unidades, erros)
    verificador.expressao(OBJETIVO, compilado.objetivo)
    for restricao in compilado.restricoes:
        verificador.comparacao(restricao.restricao.id, restricao.comparacao)
    return tuple(dict.fromkeys(erros))


def unidade_do_objetivo(
    compilado: ModeloCompilado, unidades_parametros: Mapping[str, str]
) -> Unidade | None:
    """Unidade da função objetivo (``R$``, por exemplo); ``None`` se indeterminada."""
    unidades, _ = _unidades_declaradas(compilado, unidades_parametros)
    return _Verificador(unidades, []).expressao(OBJETIVO, compilado.objetivo)


def _unidades_declaradas(
    compilado: ModeloCompilado, unidades_parametros: Mapping[str, str]
) -> tuple[dict[str, Unidade], list[ErroModelo]]:
    declaradas = [(v.id, v.unidade) for v in compilado.ir.variaveis] + [
        (p.id, unidades_parametros[p.id])
        for p in compilado.ir.parametros
        if p.id in unidades_parametros
    ]
    unidades: dict[str, Unidade] = {}
    erros: list[ErroModelo] = []
    for nome, notacao in declaradas:
        try:
            unidades[nome] = ler_unidade(notacao)
        except ValueError as erro:
            erros.append(ErroModelo(nome, str(erro)))
    return unidades, erros


class _Verificador:
    def __init__(self, unidades: Mapping[str, Unidade], erros: list[ErroModelo]) -> None:
        self._unidades = unidades
        self._erros = erros
        self._elemento = OBJETIVO

    def comparacao(self, elemento: str, comparacao: Comparacao) -> None:
        self._elemento = elemento
        self._combinar(
            comparacao.esquerda, comparacao.direita, f"os dois lados de {texto(comparacao)!r}"
        )

    def expressao(self, elemento: str, expressao: Expressao) -> Unidade | None:
        self._elemento = elemento
        return self._inferir(expressao)

    def _inferir(self, expressao: Expressao) -> Unidade | None:
        """Unidade da expressão; ``None`` para constante sem unidade (ou desconhecida)."""
        match expressao:
            case Numero():
                return None
            case Referencia(nome):
                return self._unidades.get(nome)
            case Somatorio(corpo) | Negacao(corpo):
                return self._inferir(corpo)
            case Binaria(Operador.PRODUTO | Operador.DIVISAO as operador, esquerda, direita):
                a, b = self._inferir(esquerda), self._inferir(direita)
                if a is None and b is None:
                    return None
                a = ADIMENSIONAL if a is None else a
                b = ADIMENSIONAL if b is None else b
                return a * b if operador is Operador.PRODUTO else a / b
            case Binaria(_, esquerda, direita):
                return self._combinar(esquerda, direita, f"os termos de {texto(expressao)!r}")

    def _combinar(self, esquerda: Expressao, direita: Expressao, descricao: str) -> Unidade | None:
        a, b = self._inferir(esquerda), self._inferir(direita)
        if a is not None and b is not None and a != b:
            self._erros.append(
                ErroModelo(
                    self._elemento,
                    f"as unidades de {descricao} não fecham: {texto(esquerda)!r} está em {a} "
                    f"e {texto(direita)!r} está em {b}",
                )
            )
        return a if a is not None else b


class _LeitorUnidade:
    """Analisador descendente recursivo da notação de unidades."""

    def __init__(self, tokens: list[str], original: str) -> None:
        self.restante = tokens
        self._original = original

    def quociente(self) -> Unidade:
        unidade = self._produto()
        while self._consumir("/"):
            unidade = unidade / self._produto()
        return unidade

    def _produto(self) -> Unidade:
        unidade = self._fator()
        while self.restante and self.restante[0] not in ("/", ")"):
            if not self._consumir("*"):
                self._consumir("·")
            unidade = unidade * self._fator()
        return unidade

    def _fator(self) -> Unidade:
        if not self.restante:
            raise ValueError(f"unidade {self._original!r} incompleta")
        token = self.restante.pop(0)
        if token == "(":
            base = self.quociente()
            if not self._consumir(")"):
                raise ValueError(f"unidade {self._original!r} com parêntese sem fechamento")
        elif token in {"*", "·", "/", ")"} or token.startswith("^") or token in _SOBRESCRITOS:
            raise ValueError(f"unidade {self._original!r} inválida perto de {token!r}")
        elif token == "1":
            base = ADIMENSIONAL
        else:
            base = Unidade.de({_SINONIMOS.get(token.lower(), token): 1})
        return base ** self._expoente()

    def _expoente(self) -> int:
        if self.restante and self.restante[0].startswith("^"):
            return int(self.restante.pop(0)[1:])
        if self.restante and self.restante[0] in _SOBRESCRITOS:
            return _SOBRESCRITOS[self.restante.pop(0)]
        return 1

    def _consumir(self, token: str) -> bool:
        if self.restante and self.restante[0] == token:
            self.restante.pop(0)
            return True
        return False


def _potencia(simbolo: str, expoente: int) -> str:
    return simbolo if expoente == 1 else f"{simbolo}^{expoente}"
