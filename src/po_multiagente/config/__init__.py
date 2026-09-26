"""Configuração do pacote.

Perfis de modelo de linguagem (capacidades, preços, parâmetros de inferência,
em ``config/modelos/*.yaml``) e a configuração de uma execução.
"""

from po_multiagente.config.perfis import (
    ConfiguracaoExecucao,
    EsforcoRaciocinio,
    PerfilModelo,
    Precos,
    carregar_perfil,
)

__all__ = ["ConfiguracaoExecucao", "EsforcoRaciocinio", "PerfilModelo", "Precos", "carregar_perfil"]
