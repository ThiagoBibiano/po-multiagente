"""Acurácia da associação entre parâmetros e colunas (cap. 3, critério 1).

Sendo G os pares do gabarito e P os produzidos, precisão = |P ∩ G| / |P| e
revocação = |P ∩ G| / |G|. O par é identificado pela origem (arquivo, coluna e
filtros), e não pelo nome do parâmetro, que o modelo escolhe livremente.
"""

from dataclasses import dataclass

from po_multiagente.dominio import Especificacao, Parametro

Par = tuple[str, str, tuple[tuple[str, str], ...]]


@dataclass(frozen=True)
class Associacao:
    """Precisão e revocação da associação."""

    precisao: float
    revocacao: float
    faltantes: tuple[Par, ...]
    excedentes: tuple[Par, ...]


def par(parametro: Parametro) -> Par:
    """Origem do parâmetro, sem o nome dele."""
    origem = parametro.origem
    return (
        origem.arquivo,
        origem.coluna,
        tuple(sorted((f.coluna, f.valor) for f in origem.filtros)),
    )


def acuracia_associacao(produzida: Especificacao, gabarito: Especificacao) -> Associacao:
    """Compara as origens dos parâmetros produzidos com as do gabarito."""
    p = {par(x) for x in produzida.parametros}
    g = {par(x) for x in gabarito.parametros}
    comuns = p & g
    return Associacao(
        precisao=len(comuns) / len(p) if p else 0.0,
        revocacao=len(comuns) / len(g) if g else 1.0,
        faltantes=tuple(sorted(g - p)),
        excedentes=tuple(sorted(p - g)),
    )
