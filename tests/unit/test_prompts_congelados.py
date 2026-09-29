"""Prompts congelados antes do conjunto-teste (plano, seção 11).

Os prompts atingiram a meta na partição de conferência em 28/09/2026. Mudar
um deles invalida essa conferência; se a mudança for intencional, atualize o
hash aqui e rode a conferência de novo.
"""

import pytest

from po_multiagente.prompts import AGENTES_COM_INSTRUCAO, carregar_instrucao

CONGELADOS = {
    "interpretador": "ba11cf04f65cc55a3a39bf1cf536761109918e9c2b9fc24b482f3052c678ad32",
    "modelador": "50cf77b9997fc1383db5cb5306f067299f4f6ba243ba1eb5e4ad322f487c2307",
    "explicador": "3730dea67b51076bd849e54808d79ffb8cae9db8e183d28b5be7e008b3edb7c3",
}


def test_todo_agente_com_instrucao_esta_congelado() -> None:
    assert set(AGENTES_COM_INSTRUCAO) == set(CONGELADOS)


@pytest.mark.parametrize("agente", sorted(CONGELADOS))
def test_prompt_nao_mudou_desde_a_conferencia(agente: str) -> None:
    assert carregar_instrucao(agente).sha256 == CONGELADOS[agente]
