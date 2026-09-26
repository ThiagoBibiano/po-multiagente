"""S5 — limites triviais do valor objetivo.

Duas verificações, calculadas a partir dos dados, sem o solver:

1. a solução respeita os domínios e cada restrição instanciada, e o valor
   objetivo recalculado confere com o informado. Uma solução que passa
   nesta verificação está, necessariamente, dentro da faixa elementar
   obtida por propagação de limites; a faixa entra só na mensagem, para
   leitura;
2. o valor objetivo não coincide com uma cota trivial — a obtida só com os
   domínios das variáveis, sem nenhuma restrição. Coincidir costuma indicar
   restrição faltante (custo mínimo zero porque falta a demanda) ou sentido
   invertido (lucro máximo zero), mas pode ser a resposta certa. Por isso não
   reprova: gera uma pergunta ao usuário sobre o resultado, em linguagem de
   negócio (ADR-011), e a especificação é refinada se ele disser que o
   resultado não faz sentido.
"""

import math

from po_multiagente.dominio import ResultadoSolver, Sentido, Sinal, TipoVariavel, Verificacao
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
    criterio: str | None = None,
    perguntar_cota_trivial: bool = True,
    tolerancia: float = TOLERANCIA,
) -> Verificacao:
    """Confronta a solução com os limites que os dados admitem.

    Args:
        modelo: Modelo instanciado que foi resolvido.
        resultado: Resultado do solver.
        criterio: Critério do quadro de especificação (``"Margem total"``),
            usado para redigir a pergunta ao usuário.
        perguntar_cota_trivial: Liga a segunda verificação (ver módulo).
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
    faixa = intervalo_do_objetivo(modelo, limites_propagados(modelo))
    descricao_faixa = f"[{_numero(faixa.inferior)}; {_numero(faixa.superior)}]"
    pergunta = (
        _pergunta_cota_trivial(modelo, valor, criterio, tolerancia)
        if perguntar_cota_trivial
        else None
    )
    if pergunta:
        return _verificacao(
            True,
            f"O valor objetivo ({valor:g}) coincide com uma cota trivial, obtida só com os "
            "domínios das variáveis: as restrições não afetam o resultado. Faixa admitida "
            f"pelos dados: {descricao_faixa}.",
            (OBJETIVO,),
            confirmacao=pergunta,
        )
    return _verificacao(
        True,
        f"O valor objetivo ({valor:g}) está na faixa admitida pelos dados {descricao_faixa}.",
    )


def _pergunta_cota_trivial(
    modelo: ModeloInstanciado, valor: float, criterio: str | None, tolerancia: float
) -> str | None:
    """Pergunta ao usuário se o valor coincide com uma cota trivial; senão, ``None``.

    A cota "favorável" (custo mínimo sem restrição nenhuma) sugere exigência
    faltante; a "desfavorável" (lucro máximo com tudo no mínimo), exigência
    entendida ao contrário. A pergunta fala do resultado, e nunca da
    formulação (cap. 3, Interpretador).
    """
    trivial = intervalo_do_objetivo(modelo, limites_dos_dominios(modelo))
    minimizar = modelo.objetivo.sentido is Sentido.MINIMIZAR
    favoravel, desfavoravel = (
        (trivial.inferior, trivial.superior) if minimizar else (trivial.superior, trivial.inferior)
    )
    alvo = f"«{criterio}»" if criterio else "o objetivo"
    abertura = f"Com as exigências informadas, o melhor resultado para {alvo} é {valor:g}"
    if math.isfinite(favoravel) and _proximos(valor, favoravel, tolerancia):
        return (
            f"{abertura}, o mesmo que se obteria sem exigência nenhuma. Isso costuma indicar "
            "que falta alguma exigência, como uma quantidade mínima a atender. Esse resultado "
            "faz sentido para a sua operação?"
        )
    if math.isfinite(desfavoravel) and _proximos(valor, desfavoravel, tolerancia):
        return (
            f"{abertura}, o mesmo que se obteria deixando todas as decisões no mínimo (por "
            "exemplo, sem produzir nada). Isso costuma indicar que alguma exigência foi "
            "entendida ao contrário. Esse resultado faz sentido para a sua operação?"
        )
    return None


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


def _verificacao(
    aprovada: bool,
    mensagem: str,
    elementos: tuple[str, ...] = (),
    confirmacao: str | None = None,
) -> Verificacao:
    return Verificacao(
        sinal=Sinal.S5,
        aprovada=aprovada,
        mensagem=mensagem,
        elementos=elementos,
        confirmacao=confirmacao,
    )
