"""S5 — limites triviais do valor objetivo.

Duas verificações, calculadas a partir dos dados, sem o solver:

1. a solução respeita os domínios e cada restrição instanciada, e o valor
   objetivo recalculado confere com o informado. Uma solução que passa
   nesta verificação está, necessariamente, dentro da faixa elementar
   obtida por propagação de limites; a faixa entra só na mensagem, para
   leitura;
2. o valor objetivo não coincide com uma cota trivial — a obtida só com os
   domínios das variáveis, sem nenhuma restrição. Coincidir indica que as
   restrições não afetam o resultado: custo mínimo zero porque falta a
   restrição de demanda, ou lucro máximo zero porque um sentido está
   invertido.
"""

import math

from po_multiagente.dominio import ResultadoSolver, Sinal, TipoVariavel, Verificacao
from po_multiagente.modelo import OBJETIVO, ModeloInstanciado, Relacao
from po_multiagente.validacao.cotas import (
    intervalo_do_objetivo,
    limites_dos_dominios,
    limites_propagados,
)

TOLERANCIA = 1e-6
"""Folga relativa das comparações numéricas."""


def sinal_s5_limites(
    modelo: ModeloInstanciado,
    resultado: ResultadoSolver,
    *,
    rejeitar_cota_trivial: bool = True,
    tolerancia: float = TOLERANCIA,
) -> Verificacao:
    """Confronta a solução com os limites que os dados admitem.

    Args:
        modelo: Modelo instanciado que foi resolvido.
        resultado: Resultado do solver.
        rejeitar_cota_trivial: Liga a terceira verificação (ver módulo).
        tolerancia: Folga relativa das comparações.
    """
    if not resultado.valores or resultado.valor_objetivo is None:
        return _verificacao(True, "Não se aplica: não há solução para confrontar com os limites.")
    violacoes = _violacoes(modelo, resultado.valores, tolerancia)
    recalculado = modelo.objetivo.constante + sum(
        c * resultado.valores[n] for n, c in modelo.objetivo.termos
    )
    if not _proximos(recalculado, resultado.valor_objetivo, tolerancia):
        violacoes.append(
            (
                OBJETIVO,
                f"o valor informado ({resultado.valor_objetivo:g}) difere do recalculado "
                f"com a solução ({recalculado:g})",
            )
        )
    if violacoes:
        return _verificacao(
            False,
            "A solução não respeita o modelo instanciado: "
            + "; ".join(f"{e}: {m}" for e, m in violacoes),
            tuple(dict.fromkeys(e for e, _ in violacoes)),
        )
    valor = resultado.valor_objetivo
    trivial = intervalo_do_objetivo(modelo, limites_dos_dominios(modelo))
    for cota in (trivial.inferior, trivial.superior):
        if rejeitar_cota_trivial and math.isfinite(cota) and _proximos(valor, cota, tolerancia):
            return _verificacao(
                False,
                f"O valor objetivo ({valor:g}) coincide com a cota trivial ({cota:g}) obtida só "
                "com os domínios das variáveis: as restrições não afetam o resultado, o que "
                "indica restrição faltante ou sentido invertido.",
                (OBJETIVO,),
            )
    faixa = intervalo_do_objetivo(modelo, limites_propagados(modelo))
    return _verificacao(
        True,
        f"O valor objetivo ({valor:g}) está na faixa admitida pelos dados "
        f"[{_numero(faixa.inferior)}; {_numero(faixa.superior)}].",
    )


def _violacoes(
    modelo: ModeloInstanciado, valores: dict[str, float], tolerancia: float
) -> list[tuple[str, str]]:
    violacoes = []
    for variavel in modelo.variaveis:
        valor = valores[variavel.nome]
        inferior, superior = variavel.limite_inferior, variavel.limite_superior
        fora = (inferior is not None and valor < inferior - _folga(inferior, tolerancia)) or (
            superior is not None and valor > superior + _folga(superior, tolerancia)
        )
        fracionaria = variavel.tipo is not TipoVariavel.CONTINUA and not _proximos(
            valor, round(valor), tolerancia
        )
        if fora or fracionaria:
            violacoes.append((variavel.variavel_id, f"{variavel.nome} = {valor:g} fora do domínio"))
    for restricao in modelo.restricoes:
        lado_esquerdo = sum(c * valores[n] for n, c in restricao.termos)
        folga = _folga(restricao.lado_direito, tolerancia)
        atendida = {
            Relacao.MENOR_OU_IGUAL: lado_esquerdo <= restricao.lado_direito + folga,
            Relacao.MAIOR_OU_IGUAL: lado_esquerdo >= restricao.lado_direito - folga,
            Relacao.IGUAL: abs(lado_esquerdo - restricao.lado_direito) <= folga,
        }[restricao.relacao]
        if not atendida:
            violacoes.append(
                (
                    restricao.restricao_id,
                    f"{restricao.nome} violada ({lado_esquerdo:g} {restricao.relacao.value} "
                    f"{restricao.lado_direito:g})",
                )
            )
    return violacoes


def _folga(referencia: float, tolerancia: float) -> float:
    return tolerancia * max(1.0, abs(referencia))


def _proximos(a: float, b: float, tolerancia: float) -> bool:
    return abs(a - b) <= _folga(max(abs(a), abs(b)), tolerancia)


def _numero(valor: float) -> str:
    return "-∞" if valor == -math.inf else "+∞" if valor == math.inf else f"{valor:g}"


def _verificacao(aprovada: bool, mensagem: str, elementos: tuple[str, ...] = ()) -> Verificacao:
    return Verificacao(sinal=Sinal.S5, aprovada=aprovada, mensagem=mensagem, elementos=elementos)
