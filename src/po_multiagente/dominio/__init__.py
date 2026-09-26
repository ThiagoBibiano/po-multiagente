"""Objetos de domínio: o vocabulário comum a todas as camadas.

Não depende de nenhuma outra camada do pacote. Todos os objetos são
imutáveis, estritos e serializáveis em JSON, pois compõem o dossiê de cada
execução (R5) e servem de esquema para a saída estruturada dos agentes.
"""

from po_multiagente.dominio._base import Identificador, IdRequisito, ObjetoDominio
from po_multiagente.dominio.especificacao import Especificacao, Parametro, Sentido
from po_multiagente.dominio.fontes import Coluna, Filtro, FonteDados, Origem, TipoColuna
from po_multiagente.dominio.modelo_ir import (
    Conjunto,
    ModeloIR,
    Objetivo,
    ParametroModelo,
    Quantificador,
    Restricao,
    TipoVariavel,
    Variavel,
)
from po_multiagente.dominio.requisitos import AlertaAmbiguidade, Requisito
from po_multiagente.dominio.resultados import IdentificacaoSolver, ResultadoSolver, StatusSolucao
from po_multiagente.dominio.solicitacoes import MotivoTratamento, RespostaSolicitacao, Solicitacao
from po_multiagente.dominio.validacao import ParecerValidador, Sinal, Verificacao

__all__ = [
    "AlertaAmbiguidade",
    "Coluna",
    "Conjunto",
    "Especificacao",
    "Filtro",
    "FonteDados",
    "IdRequisito",
    "IdentificacaoSolver",
    "Identificador",
    "ModeloIR",
    "MotivoTratamento",
    "Objetivo",
    "ObjetoDominio",
    "Origem",
    "Parametro",
    "ParametroModelo",
    "ParecerValidador",
    "Quantificador",
    "Requisito",
    "RespostaSolicitacao",
    "Restricao",
    "ResultadoSolver",
    "Sentido",
    "Sinal",
    "Solicitacao",
    "StatusSolucao",
    "TipoColuna",
    "TipoVariavel",
    "Variavel",
    "Verificacao",
]
