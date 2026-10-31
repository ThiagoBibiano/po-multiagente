"""Dossiê de cada execução (requisito R5).

Reúne especificação, modelo, formulação, log do solver, validações,
prompts, respostas, configuração, versões e hashes, e exporta em HTML ou
ZIP.
"""

from po_multiagente.rastreabilidade.dossie import (
    Dossie,
    arquivos_do_dossie,
    exportar_zip,
    gravar_zip,
    montar_dossie,
    para_html,
)

__all__ = [
    "Dossie",
    "arquivos_do_dossie",
    "exportar_zip",
    "gravar_zip",
    "montar_dossie",
    "para_html",
]
