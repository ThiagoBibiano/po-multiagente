"""Porta de acesso a modelos de linguagem (ADR-003).

Contrato ``LLMPort``, adaptador para a API de Respostas da OpenAI, esquema
estrito derivado do domínio, gravação e reprodução de chamadas e um modelo
roteirizado para testes. Sem LangChain: o LangGraph só orquestra.
"""

from po_multiagente.llm.adaptador_openai import AdaptadorOpenAI
from po_multiagente.llm.cassete import Cassete, ModoCassete, chave_pedido
from po_multiagente.llm.esquema import esquema_estrito
from po_multiagente.llm.porta import ErroLLM, LLMPort, Pedido, RespostaLLM, Uso
from po_multiagente.llm.roteirizado import LLMRoteirizado

__all__ = [
    "AdaptadorOpenAI",
    "Cassete",
    "ErroLLM",
    "LLMPort",
    "LLMRoteirizado",
    "ModoCassete",
    "Pedido",
    "RespostaLLM",
    "Uso",
    "chave_pedido",
    "esquema_estrito",
]
