"""Plataforma multiagente low-code para Pesquisa Operacional.

Formula, resolve e explica problemas de programação linear (PL) e linear
inteira mista (PLIM) descritos em português, com os parâmetros obtidos de
fontes de dados do usuário. A API pública (``iniciar`` e ``Plataforma``)
entra nas fases F2 e F4 do plano (``docs/plano.md``).
"""

from importlib.metadata import version

__version__ = version("po-multiagente")

__all__ = ["__version__"]
