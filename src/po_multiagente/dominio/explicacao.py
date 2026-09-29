"""Explicação final ao gestor, com a procedência de cada número exibido."""

from pydantic import NonNegativeInt

from po_multiagente.dominio._base import ObjetoDominio, TextoNaoVazio


class ItemFicha(ObjetoDominio):
    """Número exibido na explicação e de onde ele veio."""

    marcador: TextoNaoVazio
    valor: float
    origem: TextoNaoVazio


class Explicacao(ObjetoDominio):
    """Texto em linguagem de negócio, sem número que não venha de marcador.

    Attributes:
        ficha: Procedência de cada número substituído no texto.
        recusas: Textos recusados por trazer algarismo fora de marcador.
        deterministica: Indica que o texto é o de reserva, montado pelo código
            depois de recusas repetidas.
    """

    texto: TextoNaoVazio
    ficha: tuple[ItemFicha, ...] = ()
    recusas: NonNegativeInt = 0
    deterministica: bool = False
