"""Validador: sinais externos S1 a S5 sobre o modelo e o resultado, sem modelo de linguagem."""

from po_multiagente.agentes.gerador_executor import Execucao
from po_multiagente.dominio import Especificacao, ParecerValidador, Sinal, Verificacao
from po_multiagente.validacao import (
    Resolvedor,
    sinal_s1_status,
    sinal_s2_unidades,
    sinal_s3_parametros,
    sinal_s4_requisitos,
    sinal_s5_limites,
)


class Validador:
    """Agente Validador (cap. 3, Quadro de sinais).

    Localiza; não corrige. O parecer reprovado volta ao Modelador; uma
    confirmação do S5 vai ao usuário (ADR-011).
    """

    agente = "validador"

    def validar(
        self,
        iteracao: int,
        execucao: Execucao,
        especificacao: Especificacao,
        resolver: Resolvedor,
    ) -> ParecerValidador:
        """Calcula os cinco sinais."""
        compilado, instancia, resultado = execucao.compilado, execucao.instancia, execucao.resultado
        s1 = sinal_s1_status(resultado, instancia, resolver)
        if execucao.erros:
            s1 = Verificacao(
                sinal=Sinal.S1,
                aprovada=False,
                mensagem="Os dados não puderam ser ligados ao modelo: " + "; ".join(execucao.erros),
            )
        s5 = (
            sinal_s5_limites(instancia, resultado, criterio=especificacao.criterio)
            if instancia is not None
            else Verificacao(sinal=Sinal.S5, aprovada=True, mensagem="Não se aplica: sem solução.")
        )
        return ParecerValidador(
            iteracao=iteracao,
            verificacoes=(
                s1,
                sinal_s2_unidades(compilado, especificacao),
                sinal_s3_parametros(compilado.ir, especificacao),
                sinal_s4_requisitos(compilado.ir, especificacao),
                s5,
            ),
        )

    @staticmethod
    def retorno(parecer: ParecerValidador) -> str:
        """Texto das verificações reprovadas, para o Modelador corrigir."""
        return "\n".join(
            f"- {v.sinal.value} ({', '.join(v.elementos) or 'geral'}): {v.mensagem}"
            for v in parecer.verificacoes
            if not v.aprovada
        )
