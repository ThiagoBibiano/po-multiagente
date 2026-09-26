"""Os cinco sinais externos do Validador (cap. 3, Quadro de sinais).

Cada sinal é uma função que devolve uma ``Verificacao`` localizada, sem que
o modelo de linguagem julgue a própria saída.
"""

from po_multiagente.validacao.sinais.s1_status import sinal_s1_status
from po_multiagente.validacao.sinais.s2_unidades import sinal_s2_unidades
from po_multiagente.validacao.sinais.s3_parametros import sinal_s3_parametros
from po_multiagente.validacao.sinais.s4_requisitos import sinal_s4_requisitos
from po_multiagente.validacao.sinais.s5_limites import sinal_s5_limites

__all__ = [
    "sinal_s1_status",
    "sinal_s2_unidades",
    "sinal_s3_parametros",
    "sinal_s4_requisitos",
    "sinal_s5_limites",
]
