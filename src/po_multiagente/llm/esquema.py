"""Esquema JSON estrito derivado dos objetos de domínio.

A saída estruturada estrita da OpenAI exige, em todo objeto, todas as
propriedades em ``required`` e ``additionalProperties: false``, e aceita só
parte das palavras-chave do JSON Schema. O esquema enviado é derivado do
Pydantic, e não escrito à mão, para que o domínio seja a única fonte.
"""

from typing import Any

from pydantic import BaseModel

_PERMITIDAS = frozenset(
    {
        "type", "properties", "required", "additionalProperties", "items", "anyOf",
        "enum", "const", "$ref", "$defs", "description", "pattern", "format",
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems",
    }
)  # fmt: skip


def esquema_estrito(modelo: type[BaseModel]) -> dict[str, Any]:
    """Esquema do modelo Pydantic no formato aceito pela saída estruturada estrita.

    Campos com valor padrão passam a ser obrigatórios; o modelo de linguagem
    precisa escrever o valor (por exemplo, uma lista vazia ou ``null``).
    """
    esquema = _limpar(modelo.model_json_schema(mode="validation"))
    assert isinstance(esquema, dict)
    return esquema


def _limpar(no: object) -> object:
    if isinstance(no, list):
        return [_limpar(item) for item in no]
    if not isinstance(no, dict):
        return no
    limpo: dict[str, Any] = {
        chave: (
            {nome: _limpar(sub) for nome, sub in valor.items()}
            if chave in ("properties", "$defs")
            else _limpar(valor)
        )
        for chave, valor in no.items()
        if chave in _PERMITIDAS
    }
    if limpo.get("type") == "object" or "properties" in limpo:
        limpo["type"] = "object"
        limpo["additionalProperties"] = False
        propriedades: dict[str, Any] = limpo.setdefault("properties", {})
        limpo["required"] = list(propriedades)
    return limpo
