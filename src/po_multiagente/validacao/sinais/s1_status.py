"""S1 — estado de retorno do solver.

Localiza restrições incompatíveis (inviabilidade) ou insuficientes
(ilimitação). Com o modelo e o resolvedor, aponta as famílias ou as
variáveis envolvidas; sem eles, só informa o estado.
"""

from po_multiagente.dominio import ResultadoSolver, Sinal, StatusSolucao, Verificacao
from po_multiagente.modelo import ModeloInstanciado
from po_multiagente.validacao.diagnostico import (
    Resolvedor,
    localizar_ilimitacao,
    localizar_inviabilidade,
)


def sinal_s1_status(
    resultado: ResultadoSolver,
    modelo: ModeloInstanciado | None = None,
    resolver: Resolvedor | None = None,
) -> Verificacao:
    """Verifica o estado de retorno e, se houver falha, localiza a causa.

    Args:
        resultado: Resultado da execução.
        modelo: Modelo resolvido; com ``resolver``, permite localizar a causa.
        resolver: O mesmo solver da execução, para resolver variantes.
    """
    match resultado.status:
        case StatusSolucao.OTIMO:
            return _verificacao(True, "O solver encontrou solução ótima.")
        case StatusSolucao.LIMITE_TEMPO if resultado.valores:
            return _verificacao(
                True,
                "O solver parou no limite de tempo com solução viável, sem prova de otimalidade.",
            )
        case StatusSolucao.LIMITE_TEMPO:
            return _verificacao(False, "O solver não encontrou solução no limite de tempo.")
        case StatusSolucao.INVIAVEL:
            elementos = (
                localizar_inviabilidade(modelo, resolver)
                if modelo is not None and resolver is not None
                else ()
            )
            return _verificacao(False, _mensagem_inviavel(modelo, elementos), elementos)
        case StatusSolucao.ILIMITADO:
            elementos = (
                localizar_ilimitacao(modelo, resolver)
                if modelo is not None and resolver is not None
                else ()
            )
            mensagem = "O objetivo pode melhorar sem limite"
            if elementos:
                mensagem += f": nenhuma restrição segura {', '.join(elementos)}"
            return _verificacao(False, mensagem + ".", elementos)
        case StatusSolucao.ERRO:
            return _verificacao(False, "O solver falhou ao executar o modelo.")


def _mensagem_inviavel(modelo: ModeloInstanciado | None, elementos: tuple[str, ...]) -> str:
    if not elementos:
        return "O modelo é inviável."
    familias = {r.restricao_id for r in modelo.restricoes} if modelo else set()
    if set(elementos) <= familias:
        return (
            f"O modelo é inviável: as restrições {', '.join(elementos)} não podem ser "
            "atendidas ao mesmo tempo."
        )
    return f"O modelo é inviável: o domínio das variáveis {', '.join(elementos)} é vazio."


def _verificacao(aprovada: bool, mensagem: str, elementos: tuple[str, ...] = ()) -> Verificacao:
    return Verificacao(sinal=Sinal.S1, aprovada=aprovada, mensagem=mensagem, elementos=elementos)
