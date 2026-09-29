"""Representação intermediária e sua compilação (ADR-002).

Compilador determinístico que substitui a geração de código por modelo de
linguagem, em três estágios:

1. ``compilar``: análise sintática (gramática Lark) e checagem de nomes,
   índices e linearidade — erros de formato, que voltam ao Modelador
   (ADR-008);
2. ``instanciar``: ligação com os dados e expansão no modelo neutro;
3. o adaptador do solver, em ``po_multiagente.solver``.

Inclui a checagem de unidades, base do sinal S2, e a formulação em LaTeX.
"""

from po_multiagente.modelo.arvore import Comparacao, Expressao, Relacao, texto
from po_multiagente.modelo.compilacao import ModeloCompilado, RestricaoCompilada, compilar
from po_multiagente.modelo.erros import OBJETIVO, ErroCompilacao, ErroInstanciacao, ErroModelo
from po_multiagente.modelo.gramatica import (
    PALAVRAS_RESERVADAS,
    ErroSintaxe,
    analisar_comparacao,
    analisar_expressao,
)
from po_multiagente.modelo.instanciacao import (
    ModeloInstanciado,
    ObjetivoInstanciado,
    RestricaoInstanciada,
    Termo,
    VariavelInstanciada,
    instanciar,
    nome_instancia,
)
from po_multiagente.modelo.latex import expressao_latex, para_latex
from po_multiagente.modelo.unidades import (
    ADIMENSIONAL,
    Unidade,
    ler_unidade,
    unidade_do_objetivo,
    verificar_unidades,
)

__all__ = [
    "ADIMENSIONAL",
    "OBJETIVO",
    "PALAVRAS_RESERVADAS",
    "Comparacao",
    "ErroCompilacao",
    "ErroInstanciacao",
    "ErroModelo",
    "ErroSintaxe",
    "Expressao",
    "ModeloCompilado",
    "ModeloInstanciado",
    "ObjetivoInstanciado",
    "Relacao",
    "RestricaoCompilada",
    "RestricaoInstanciada",
    "Termo",
    "Unidade",
    "VariavelInstanciada",
    "analisar_comparacao",
    "analisar_expressao",
    "compilar",
    "expressao_latex",
    "instanciar",
    "ler_unidade",
    "nome_instancia",
    "para_latex",
    "texto",
    "unidade_do_objetivo",
    "verificar_unidades",
]
