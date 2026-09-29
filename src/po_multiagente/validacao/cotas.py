"""Cotas elementares das variáveis e do valor objetivo (apoio ao sinal S5).

Propagação de limites: cada restrição, isolada, limita cada uma de suas
variáveis dados os limites das demais. Poucas passadas bastam para cotas
elementares; não se busca a envoltória exata, que exigiria resolver o modelo.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from po_multiagente.dominio import TipoVariavel
from po_multiagente.modelo import ModeloInstanciado, Relacao, Termo

PASSADAS = 10
_INF = math.inf


@dataclass(frozen=True)
class Intervalo:
    """Faixa fechada de valores; os extremos podem ser infinitos."""

    inferior: float
    superior: float


def intervalo_do_objetivo(modelo: ModeloInstanciado, limites: dict[str, Intervalo]) -> Intervalo:
    """Faixa do valor objetivo dados os limites de cada variável."""
    inferior = superior = modelo.objetivo.constante
    for nome, coeficiente in modelo.objetivo.termos:
        extremos = _produto(coeficiente, limites[nome])
        inferior += extremos.inferior
        superior += extremos.superior
    return Intervalo(inferior, superior)


def limites_dos_dominios(modelo: ModeloInstanciado) -> dict[str, Intervalo]:
    """Limites de cada variável só pelo domínio declarado, sem restrições."""
    return {
        v.nome: Intervalo(
            -_INF if v.limite_inferior is None else v.limite_inferior,
            _INF if v.limite_superior is None else v.limite_superior,
        )
        for v in modelo.variaveis
    }


def limites_propagados(modelo: ModeloInstanciado) -> dict[str, Intervalo]:
    """Limites de cada variável pelo domínio e pelas restrições, uma a uma."""
    limites = limites_dos_dominios(modelo)
    inteiras = {v.nome for v in modelo.variaveis if v.tipo is not TipoVariavel.CONTINUA}
    for _ in range(PASSADAS):
        mudou = False
        for restricao in modelo.restricoes:
            # "<=" limita por cima; ">=" é "<=" com os sinais trocados; "==" é os dois.
            if restricao.relacao is not Relacao.MAIOR_OU_IGUAL:
                tetos = _tetos(restricao.termos, restricao.lado_direito, limites)
                mudou |= _apertar(limites, tetos, inteiras)
            if restricao.relacao is not Relacao.MENOR_OU_IGUAL:
                negados = [(nome, -coeficiente) for nome, coeficiente in restricao.termos]
                tetos = _tetos(negados, -restricao.lado_direito, limites)
                mudou |= _apertar(limites, tetos, inteiras)
        if not mudou:
            break
    return limites


def _tetos(
    termos: Iterable[Termo], lado_direito: float, limites: dict[str, Intervalo]
) -> dict[str, Intervalo]:
    """Limites implicados por ``soma(a·x) <= b`` para cada variável."""
    termos = tuple(termos)
    # Menor valor de cada termo; o de cada variável sai de b menos o dos demais.
    minimos = [_produto(a, limites[n]).inferior for n, a in termos]
    infinitos = sum(1 for m in minimos if m == -_INF)
    soma_finita = sum(m for m in minimos if m != -_INF)
    implicados = {}
    for (nome, coeficiente), minimo in zip(termos, minimos, strict=True):
        if coeficiente == 0.0:
            continue
        if minimo == -_INF:
            if infinitos > 1:
                continue
            resto = soma_finita
        else:
            if infinitos > 0:
                continue
            resto = soma_finita - minimo
        cota = (lado_direito - resto) / coeficiente
        implicados[nome] = Intervalo(-_INF, cota) if coeficiente > 0 else Intervalo(cota, _INF)
    return implicados


def _apertar(
    limites: dict[str, Intervalo], implicados: dict[str, Intervalo], inteiras: set[str]
) -> bool:
    mudou = False
    for nome, implicado in implicados.items():
        atual = limites[nome]
        inferior = max(atual.inferior, implicado.inferior)
        superior = min(atual.superior, implicado.superior)
        if nome in inteiras:
            inferior = math.ceil(inferior - 1e-9) if math.isfinite(inferior) else inferior
            superior = math.floor(superior + 1e-9) if math.isfinite(superior) else superior
        # Folga mínima para não iterar sobre ganhos numéricos desprezíveis.
        if inferior > atual.inferior + 1e-9 or superior < atual.superior - 1e-9:
            limites[nome] = Intervalo(inferior, superior)
            mudou = True
    return mudou


def _produto(coeficiente: float, intervalo: Intervalo) -> Intervalo:
    if coeficiente == 0.0:
        return Intervalo(0.0, 0.0)
    extremos = (coeficiente * intervalo.inferior, coeficiente * intervalo.superior)
    return Intervalo(min(extremos), max(extremos))
