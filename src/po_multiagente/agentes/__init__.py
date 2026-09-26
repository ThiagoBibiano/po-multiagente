"""Os cinco agentes da plataforma (cap. 3, Passo 3).

Interpretador, Modelador e Explicador usam o modelo de linguagem, sempre com
saída estruturada conferida pelo código; Gerador-Executor e Validador são
determinísticos.
"""

from po_multiagente.agentes._comum import (
    ErroAgente,
    ErroFormato,
    Registro,
    RegistroChamada,
    descrever_fontes,
)
from po_multiagente.agentes.explicador import Explicador, formatar_numero
from po_multiagente.agentes.gerador_executor import Execucao, GeradorExecutor
from po_multiagente.agentes.interpretador import Interpretador, ResultadoInterpretador, Rodada
from po_multiagente.agentes.modelador import Modelador, ResultadoModelador
from po_multiagente.agentes.validador import Validador

__all__ = [
    "ErroAgente",
    "ErroFormato",
    "Execucao",
    "Explicador",
    "GeradorExecutor",
    "Interpretador",
    "Modelador",
    "Registro",
    "RegistroChamada",
    "ResultadoInterpretador",
    "ResultadoModelador",
    "Rodada",
    "Validador",
    "descrever_fontes",
    "formatar_numero",
]
