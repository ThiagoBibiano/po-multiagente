"""Instruções versionadas dos agentes, com hash registrado em cada execução."""

import hashlib
from dataclasses import dataclass
from importlib.resources import files

AGENTES_COM_INSTRUCAO = ("interpretador", "modelador", "explicador")


@dataclass(frozen=True)
class Instrucao:
    """Texto da instrução de um agente e o SHA-256 dele."""

    agente: str
    texto: str
    sha256: str


def carregar_instrucao(agente: str) -> Instrucao:
    """Lê ``prompts/<agente>.md`` distribuído com o pacote."""
    texto = files("po_multiagente.prompts").joinpath(f"{agente}.md").read_text(encoding="utf-8")
    return Instrucao(agente=agente, texto=texto, sha256=hashlib.sha256(texto.encode()).hexdigest())
