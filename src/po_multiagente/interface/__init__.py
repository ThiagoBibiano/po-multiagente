"""Interface Gradio para o usuário final (ADR-001).

Camada fina sobre a API pública do pacote. O ``Assistente`` conduz a sessão
sem depender do Gradio; ``iniciar`` abre a interface e exige o extra
``po-multiagente[interface]``.
"""

from po_multiagente.interface.assistente import (
    Assistente,
    ErroAssistente,
    Etapa,
    Resultado,
    TipoEtapa,
)

__all__ = ["Assistente", "ErroAssistente", "Etapa", "Resultado", "TipoEtapa", "iniciar"]


def iniciar(perfil: str | None = None, *, compartilhar: bool = False) -> None:
    """Abre a interface; ver ``po_multiagente.interface.app.iniciar``."""
    from po_multiagente.interface.app import iniciar as abrir  # noqa: PLC0415 — Gradio é opcional

    abrir(perfil, compartilhar=compartilhar)
