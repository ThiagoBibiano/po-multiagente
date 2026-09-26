"""Sinais externos do agente Validador.

Cada sinal é calculável sem que o modelo de linguagem julgue a própria saída
(cap. 3, Quadro de sinais): S1 estado do solver, S2 unidades, S3 cobertura
de parâmetros, S4 cobertura de requisitos e S5 limites triviais. Os sinais
localizam o erro; a correção fica com o Modelador.
"""

from po_multiagente.validacao.cotas import (
    Intervalo,
    intervalo_do_objetivo,
    limites_dos_dominios,
    limites_propagados,
)
from po_multiagente.validacao.diagnostico import (
    Resolvedor,
    localizar_ilimitacao,
    localizar_inviabilidade,
)
from po_multiagente.validacao.sinais import (
    sinal_s1_status,
    sinal_s2_unidades,
    sinal_s3_parametros,
    sinal_s4_requisitos,
    sinal_s5_limites,
)

__all__ = [
    "Intervalo",
    "Resolvedor",
    "intervalo_do_objetivo",
    "limites_dos_dominios",
    "limites_propagados",
    "localizar_ilimitacao",
    "localizar_inviabilidade",
    "sinal_s1_status",
    "sinal_s2_unidades",
    "sinal_s3_parametros",
    "sinal_s4_requisitos",
    "sinal_s5_limites",
]
