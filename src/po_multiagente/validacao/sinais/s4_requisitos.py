"""S4 — cobertura de requisitos, por identificador.

Conta identificadores, e não compara significados: um requisito do quadro
que nenhuma restrição, domínio de variável ou objetivo cita, ou um elemento
que cita requisito inexistente, é localizado sem juízo do modelo de
linguagem (cap. 3).
"""

from po_multiagente.dominio import Especificacao, ModeloIR, Sinal, Verificacao


def sinal_s4_requisitos(ir: ModeloIR, especificacao: Especificacao) -> Verificacao:
    """Verifica que cada requisito é atendido e que cada restrição tem requisito válido."""
    declarados = [r.id for r in especificacao.requisitos]
    citados = {
        *ir.objetivo.requisitos,
        *(req for r in ir.restricoes for req in r.requisitos),
        *(req for v in ir.variaveis for req in v.requisitos),
    }
    problemas = [
        (requisito, "requisito sem restrição, domínio de variável nem objetivo que o atenda")
        for requisito in declarados
        if requisito not in citados
    ]
    if desconhecidos := sorted(set(ir.objetivo.requisitos) - set(declarados)):
        problemas.append(("objetivo", f"cita {', '.join(desconhecidos)}, ausente(s) do quadro"))
    citacoes = [(r.id, r.requisitos) for r in ir.restricoes] + [
        (v.id, v.requisitos) for v in ir.variaveis
    ]
    for elemento, requisitos in citacoes:
        if desconhecidos := sorted(set(requisitos) - set(declarados)):
            problemas.append((elemento, f"cita {', '.join(desconhecidos)}, ausente(s) do quadro"))
    if not problemas:
        return Verificacao(
            sinal=Sinal.S4,
            aprovada=True,
            mensagem="Todo requisito é atendido, e toda restrição cita requisito do quadro.",
        )
    return Verificacao(
        sinal=Sinal.S4,
        aprovada=False,
        mensagem="; ".join(f"{elemento}: {problema}" for elemento, problema in problemas),
        elementos=tuple(elemento for elemento, _ in problemas),
    )
