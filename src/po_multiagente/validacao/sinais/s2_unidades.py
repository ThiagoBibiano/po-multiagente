"""S2 — consistência de unidades.

As unidades dos parâmetros vêm do quadro de especificação; as das
variáveis, do modelo. Localiza a restrição ou o termo cujas unidades não
fecham.
"""

from po_multiagente.dominio import Especificacao, Sinal, Verificacao
from po_multiagente.modelo import ModeloCompilado, verificar_unidades


def sinal_s2_unidades(compilado: ModeloCompilado, especificacao: Especificacao) -> Verificacao:
    """Verifica se as unidades fecham no objetivo e em cada restrição."""
    erros = verificar_unidades(compilado, {p.id: p.unidade for p in especificacao.parametros})
    if not erros:
        return Verificacao(
            sinal=Sinal.S2,
            aprovada=True,
            mensagem="As unidades fecham na função objetivo e em todas as restrições.",
        )
    return Verificacao(
        sinal=Sinal.S2,
        aprovada=False,
        mensagem="; ".join(str(e) for e in erros),
        elementos=tuple(dict.fromkeys(e.elemento for e in erros)),
    )
