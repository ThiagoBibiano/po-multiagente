"""Plataforma multiagente low-code para Pesquisa Operacional.

Formula, resolve e explica problemas de programação linear (PL) e linear
inteira mista (PLIM) descritos em português, com os parâmetros obtidos de
fontes de dados do usuário.

No Colab::

    from po_multiagente import iniciar
    iniciar()   # chave lida dos Secrets do Colab (por exemplo, GEMINI_API_KEY)
"""

from importlib.metadata import version

__version__ = version("po-multiagente")

__all__ = ["__version__", "iniciar"]


def iniciar(perfil: str | None = None, *, compartilhar: bool = False) -> None:
    """Abre a interface Gradio (extra ``po-multiagente[interface]``).

    Args:
        perfil: Perfil do modelo; o padrão é o do experimento.
        compartilhar: Gera um link público temporário do Gradio.
    """
    from po_multiagente.interface import iniciar as abrir  # noqa: PLC0415 — Gradio é opcional

    abrir(perfil, compartilhar=compartilhar)
