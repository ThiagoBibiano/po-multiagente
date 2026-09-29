"""Localização das causas de inviabilidade e de ilimitação (apoio ao sinal S1).

O solver só informa que o modelo é inviável ou ilimitado. Para devolver ao
Modelador o elemento com erro, estas funções resolvem variantes do modelo:
o CBC não fornece um subsistema irredutível inviável (IIS), e o filtro de
deleção sobre as famílias de restrições o aproxima com poucas resoluções.
"""

import math
from collections.abc import Callable
from dataclasses import replace

from po_multiagente.dominio import ResultadoSolver, StatusSolucao, TipoVariavel
from po_multiagente.modelo import ModeloInstanciado, VariavelInstanciada

Resolvedor = Callable[[ModeloInstanciado], ResultadoSolver]
"""Resolve um modelo neutro com o solver da execução, sempre o mesmo."""

LIMITE_ARTIFICIAL = 1e7
"""Cota imposta às variáveis sem limite para achar a direção de ilimitação."""


def localizar_inviabilidade(modelo: ModeloInstanciado, resolver: Resolvedor) -> tuple[str, ...]:
    """Famílias de restrições que, juntas, tornam o modelo inviável.

    Filtro de deleção: cada família é retirada; se o restante continua
    inviável, ela não é necessária e sai de vez. As que sobram formam um
    conjunto irredutível no nível de família — retirar qualquer uma torna o
    modelo viável. Custa uma resolução por família.

    Returns:
        Identificadores das famílias, na ordem do modelo; ou, quando nenhuma
        restrição é necessária, as variáveis cujo domínio é vazio. Vazio se
        o modelo não for inviável.
    """
    if resolver(modelo).status is not StatusSolucao.INVIAVEL:
        return ()
    familias = list(dict.fromkeys(r.restricao_id for r in modelo.restricoes))
    necessarias = set(familias)
    for familia in familias:
        candidatas = necessarias - {familia}
        retiradas = set(familias) - candidatas
        if resolver(modelo.sem_restricoes(retiradas)).status is StatusSolucao.INVIAVEL:
            necessarias = candidatas
    if necessarias:
        return tuple(f for f in familias if f in necessarias)
    return tuple(dict.fromkeys(v.variavel_id for v in modelo.variaveis if _dominio_vazio(v)))


def localizar_ilimitacao(modelo: ModeloInstanciado, resolver: Resolvedor) -> tuple[str, ...]:
    """Variáveis ao longo das quais o objetivo melhora sem limite.

    Impõe ``LIMITE_ARTIFICIAL`` aos lados sem limite, resolve e aponta as
    variáveis que encostam nessa cota: são elas que nenhuma restrição segura.

    Returns:
        Identificadores das variáveis (no modelo, e não instanciadas).
    """
    limitado = replace(
        modelo,
        variaveis=tuple(
            replace(
                v,
                limite_inferior=(
                    -LIMITE_ARTIFICIAL if v.limite_inferior is None else v.limite_inferior
                ),
                limite_superior=(
                    LIMITE_ARTIFICIAL if v.limite_superior is None else v.limite_superior
                ),
            )
            for v in modelo.variaveis
        ),
    )
    resultado = resolver(limitado)
    if resultado.status is not StatusSolucao.OTIMO:
        return ()
    encostadas = [
        v.variavel_id
        for v in modelo.variaveis
        if (
            v.limite_superior is None
            and resultado.valores[v.nome] >= LIMITE_ARTIFICIAL * (1 - 1e-6)
        )
        or (
            v.limite_inferior is None
            and resultado.valores[v.nome] <= -LIMITE_ARTIFICIAL * (1 - 1e-6)
        )
    ]
    return tuple(dict.fromkeys(encostadas))


def _dominio_vazio(variavel: VariavelInstanciada) -> bool:
    """Limites sem nenhum valor admissível, como um inteiro entre 2,5 e 2,7."""
    inferior, superior = variavel.limite_inferior, variavel.limite_superior
    if inferior is None or superior is None:
        return False
    if variavel.tipo is TipoVariavel.CONTINUA:
        return inferior > superior
    return math.ceil(inferior - 1e-9) > math.floor(superior + 1e-9)
