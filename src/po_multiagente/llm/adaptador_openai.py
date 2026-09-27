"""Adaptador para a API de Respostas (OpenAI e compatíveis), com saída estruturada estrita."""

import os
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError, omit
from openai.types.responses import ResponseTextConfigParam
from openai.types.shared_params import Reasoning

from po_multiagente.config import PerfilModelo
from po_multiagente.llm.porta import ErroLLM, Pedido, RespostaLLM, Uso

TENTATIVAS_REDE = 4
"""Novas tentativas para falhas transitórias (rede, limite de taxa, erro 5xx)."""

_ERRO_DO_SERVIDOR = 500


class AdaptadorOpenAI:
    """``LLMPort`` sobre a API de Respostas (``client.responses.create``).

    Serve a qualquer provedor que implemente essa API (a Maritaca, por
    exemplo): o perfil define o endpoint e a variável de ambiente da chave.

    Args:
        perfil: Perfil do modelo; define endpoint, esforço de raciocínio, temperatura e preços.
        cliente: Cliente já configurado; o padrão lê a chave de ``perfil.variavel_chave``.
    """

    def __init__(self, perfil: PerfilModelo, cliente: OpenAI | None = None) -> None:
        self._perfil = perfil
        if cliente is None:
            chave = os.environ.get(perfil.variavel_chave)
            if not chave:
                raise ErroLLM(
                    f"Defina {perfil.variavel_chave} (no Colab, em Secrets) para chamar o modelo"
                )
            cliente = OpenAI(api_key=chave, base_url=perfil.url_base)
        self._cliente = cliente

    @property
    def modelo(self) -> str:
        """Identificador do modelo na API."""
        return self._perfil.modelo

    def parametros(self) -> dict[str, Any]:
        """Parâmetros de inferência que serão enviados, para o manifesto."""
        parametros: dict[str, Any] = {"max_output_tokens": self._perfil.max_saida_tokens}
        if self._perfil.esforco_raciocinio is not None:
            parametros["reasoning"] = {"effort": self._perfil.esforco_raciocinio}
        if self._perfil.temperatura is not None:
            parametros["temperature"] = self._perfil.temperatura
        return parametros

    def gerar(self, pedido: Pedido) -> RespostaLLM:
        """Chama o modelo, com novas tentativas para falhas transitórias."""
        parametros = self.parametros()
        texto: ResponseTextConfigParam = {
            "format": {
                "type": "json_schema",
                "name": pedido.nome_esquema,
                "schema": pedido.esquema,
                "strict": self._perfil.saida_estruturada_estrita,
            }
        }
        esforco = self._perfil.esforco_raciocinio
        raciocinio: Reasoning | None = {"effort": esforco} if esforco is not None else None
        inicio = time.perf_counter()
        for tentativa in range(TENTATIVAS_REDE):
            try:
                resposta = self._cliente.responses.create(
                    model=self._perfil.modelo,
                    instructions=pedido.instrucoes,
                    input=pedido.entrada,
                    text=texto,
                    store=False,
                    max_output_tokens=self._perfil.max_saida_tokens,
                    reasoning=raciocinio if raciocinio is not None else omit,
                    temperature=(
                        self._perfil.temperatura if self._perfil.temperatura is not None else omit
                    ),
                )
                break
            except (APIConnectionError, RateLimitError) as erro:
                if tentativa == TENTATIVAS_REDE - 1:
                    raise ErroLLM(f"Falha de comunicação com o modelo: {erro}") from erro
            except APIStatusError as erro:
                if erro.status_code < _ERRO_DO_SERVIDOR or tentativa == TENTATIVAS_REDE - 1:
                    raise ErroLLM(f"A API recusou o pedido ({erro.status_code}): {erro}") from erro
            time.sleep(2**tentativa)
        if resposta.status != "completed" or not resposta.output_text:
            detalhe = getattr(resposta, "incomplete_details", None)
            raise ErroLLM(f"Resposta {resposta.status} do modelo: {detalhe}")
        uso = resposta.usage
        return RespostaLLM(
            texto=resposta.output_text,
            modelo=resposta.model,
            uso=Uso(
                entrada=uso.input_tokens if uso else 0,
                entrada_em_cache=uso.input_tokens_details.cached_tokens if uso else 0,
                saida=uso.output_tokens if uso else 0,
                raciocinio=uso.output_tokens_details.reasoning_tokens if uso else 0,
            ),
            parametros=parametros,
            duracao_s=time.perf_counter() - inicio,
        )
