"""Erros da leitura das fontes e da ligação dos valores ao modelo."""

from po_multiagente.dominio import MotivoTratamento


class ErroDados(Exception):
    """Falha ao ler uma fonte ou ao ligar seus valores ao modelo.

    Attributes:
        arquivo: Fonte envolvida; ``None`` quando falta a própria origem.
        coluna: Coluna envolvida, quando houver.
        motivo: Tratamento que resolveria a falha, quando ela está no dado e
            não numa referência errada. Orienta a solicitação de tratamento
            que o Interpretador dirige ao usuário.
    """

    def __init__(
        self,
        mensagem: str,
        *,
        arquivo: str | None,
        coluna: str | None = None,
        motivo: MotivoTratamento | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.arquivo = arquivo
        self.coluna = coluna
        self.motivo = motivo


class ErroLigacao(Exception):
    """Uma ou mais falhas ao ligar os dados a um modelo.

    Reúne todas as falhas em vez de parar na primeira, para que o
    Interpretador trate todas de uma vez.
    """

    def __init__(self, erros: tuple[ErroDados, ...]) -> None:
        super().__init__("; ".join(str(e) for e in erros))
        self.erros = erros
