"""Erros localizados da compilação e da instanciação do modelo."""

from collections.abc import Iterable
from dataclasses import dataclass

OBJETIVO = "objetivo"
"""Elemento usado para localizar erros na função objetivo."""


@dataclass(frozen=True)
class ErroModelo:
    """Erro localizado num elemento do modelo.

    Attributes:
        elemento: Identificador da restrição, da variável, do conjunto ou do
            parâmetro; ``"objetivo"`` para a função objetivo.
        mensagem: O que está errado, citando o trecho exato.
    """

    elemento: str
    mensagem: str

    def __str__(self) -> str:
        """Elemento e mensagem, como aparecem no retorno ao Modelador."""
        return f"{self.elemento}: {self.mensagem}"


class _ErroComElementos(Exception):
    def __init__(self, erros: Iterable[ErroModelo]) -> None:
        self.erros = tuple(dict.fromkeys(erros))
        super().__init__("; ".join(str(e) for e in self.erros))


class ErroCompilacao(_ErroComElementos):
    """O modelo não segue a gramática ou referencia nomes e índices inválidos.

    É erro de formato: pela ADR-008, gera nova tentativa dentro do próprio
    Modelador, igual nas duas configurações do experimento.
    """


class ErroInstanciacao(_ErroComElementos):
    """Os dados ligados não bastam para instanciar o modelo compilado."""
