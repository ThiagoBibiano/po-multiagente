"""Adaptador para as APIs da OpenAI (e compatíveis), com saída estruturada estrita.

Duas APIs, escolhidas pelo perfil: a de Respostas (``responses``) e a de Chat
Completions (``chat``). A segunda existe porque alguns provedores só atendem
certos níveis de serviço por ela (a Maritaca ignora ``service_tier`` na de
Respostas, e o respeita na de Chat Completions).
"""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError, omit
from openai.types.chat import ChatCompletion
from openai.types.responses import Response, ResponseTextConfigParam
from openai.types.shared_params import Reasoning, ResponseFormatJSONSchema

from po_multiagente.config import PerfilModelo
from po_multiagente.llm.porta import ErroLLM, ErroSaidaForaDoEsquema, Pedido, RespostaLLM, Uso

TENTATIVAS_REDE = 4
"""Novas tentativas para falhas transitórias (rede, limite de taxa, erro 5xx)."""

_ERRO_DO_SERVIDOR = 500
_SAIDA_FORA_DO_ESQUEMA = "model_output_schema_mismatch"
_SAIDA_TRUNCADA = "max_tokens_reached"
TRUNCADA = (
    "A resposta passou do limite de tokens de saída e ficou incompleta. "
    "Devolva o objeto completo, sem repetir elementos."
)
"""Motivo devolvido ao agente quando a saída é cortada, em vez do texto parcial."""

_Bruta = TypeVar("_Bruta")


@dataclass(frozen=True)
class _Saida:
    """O que interessa de uma resposta, qualquer que seja a API."""

    texto: str
    modelo: str
    uso: Uso
    nivel_servico: str | None


class AdaptadorOpenAI:
    """``LLMPort`` sobre a API de Respostas ou a de Chat Completions do SDK ``openai``.

    Serve a qualquer provedor que implemente essas APIs (a Maritaca, por
    exemplo): o perfil define a API, o endpoint e a variável de ambiente da chave.

    Args:
        perfil: Perfil do modelo; define API, endpoint, nível de serviço,
            esforço de raciocínio, temperatura e preços.
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
        limite = "max_completion_tokens" if self._perfil.api == "chat" else "max_output_tokens"
        parametros: dict[str, Any] = {limite: self._perfil.max_saida_tokens}
        if self._perfil.esforco_raciocinio is not None:
            parametros["reasoning"] = {"effort": self._perfil.esforco_raciocinio}
        if self._perfil.temperatura is not None:
            parametros["temperature"] = self._perfil.temperatura
        if self._perfil.nivel_servico is not None:
            parametros["service_tier"] = self._perfil.nivel_servico
        return parametros

    def gerar(self, pedido: Pedido) -> RespostaLLM:
        """Chama o modelo, com novas tentativas para falhas transitórias.

        Com nível de serviço no perfil, ``parametros["service_tier"]`` é o nível
        que o provedor informa ter aplicado, e não o pedido: a flex, por
        exemplo, depende de capacidade.
        """
        inicio = time.perf_counter()
        if self._perfil.api == "chat":
            saida = _ler_chat(self._tentar(lambda: self._chamar_chat(pedido)))
        else:
            saida = _ler_respostas(self._tentar(lambda: self._chamar_respostas(pedido)))
        parametros = self.parametros()
        if self._perfil.nivel_servico is not None:
            parametros["service_tier"] = saida.nivel_servico
        return RespostaLLM(
            texto=saida.texto,
            modelo=saida.modelo,
            uso=saida.uso,
            parametros=parametros,
            duracao_s=time.perf_counter() - inicio,
        )

    def _tentar(self, chamada: Callable[[], _Bruta]) -> _Bruta:
        """Repete falhas transitórias e traduz as recusas do provedor."""
        for tentativa in range(TENTATIVAS_REDE):
            try:
                return chamada()
            except (APIConnectionError, RateLimitError) as erro:
                if tentativa == TENTATIVAS_REDE - 1:
                    raise ErroLLM(f"Falha de comunicação com o modelo: {erro}") from erro
            except APIStatusError as erro:
                if erro.code == _SAIDA_FORA_DO_ESQUEMA:
                    raise ErroSaidaForaDoEsquema(_mensagem(erro)) from erro
                if erro.code == _SAIDA_TRUNCADA:
                    raise ErroSaidaForaDoEsquema(TRUNCADA) from erro
                if erro.status_code < _ERRO_DO_SERVIDOR or tentativa == TENTATIVAS_REDE - 1:
                    raise ErroLLM(f"A API recusou o pedido ({erro.status_code}): {erro}") from erro
            time.sleep(2**tentativa)
        raise AssertionError("inalcançável")  # pragma: no cover

    def _chamar_respostas(self, pedido: Pedido) -> Response:
        perfil = self._perfil
        texto: ResponseTextConfigParam = {
            "format": {
                "type": "json_schema",
                "name": pedido.nome_esquema,
                "schema": pedido.esquema,
                "strict": perfil.saida_estruturada_estrita,
            }
        }
        esforco = perfil.esforco_raciocinio
        raciocinio: Reasoning | None = {"effort": esforco} if esforco is not None else None
        return self._cliente.responses.create(
            model=perfil.modelo,
            instructions=pedido.instrucoes,
            input=pedido.entrada,
            text=texto,
            store=False,
            max_output_tokens=perfil.max_saida_tokens,
            reasoning=raciocinio if raciocinio is not None else omit,
            temperature=perfil.temperatura if perfil.temperatura is not None else omit,
            service_tier=perfil.nivel_servico if perfil.nivel_servico is not None else omit,
        )

    def _chamar_chat(self, pedido: Pedido) -> ChatCompletion:
        perfil = self._perfil
        formato: ResponseFormatJSONSchema = {
            "type": "json_schema",
            "json_schema": {
                "name": pedido.nome_esquema,
                "schema": pedido.esquema,
                "strict": perfil.saida_estruturada_estrita,
            },
        }
        return self._cliente.chat.completions.create(
            model=perfil.modelo,
            messages=[
                {"role": "system", "content": pedido.instrucoes},
                {"role": "user", "content": pedido.entrada},
            ],
            response_format=formato,
            # Sem store: na OpenAI o padrão já é não guardar, e a Maritaca rejeita o campo.
            max_completion_tokens=perfil.max_saida_tokens,
            reasoning_effort=perfil.esforco_raciocinio or omit,
            temperature=perfil.temperatura if perfil.temperatura is not None else omit,
            service_tier=perfil.nivel_servico if perfil.nivel_servico is not None else omit,
        )


def _ler_respostas(resposta: Response) -> _Saida:
    detalhe = getattr(resposta, "incomplete_details", None)
    if getattr(detalhe, "reason", None) == "max_output_tokens":
        raise ErroSaidaForaDoEsquema(TRUNCADA)
    if resposta.status != "completed" or not resposta.output_text:
        raise ErroLLM(f"Resposta {resposta.status} do modelo: {detalhe}")
    uso = resposta.usage
    return _Saida(
        texto=resposta.output_text,
        modelo=resposta.model,
        uso=Uso(
            entrada=uso.input_tokens if uso else 0,
            entrada_em_cache=uso.input_tokens_details.cached_tokens if uso else 0,
            saida=uso.output_tokens if uso else 0,
            raciocinio=uso.output_tokens_details.reasoning_tokens if uso else 0,
        ),
        nivel_servico=getattr(resposta, "service_tier", None),
    )


def _ler_chat(resposta: ChatCompletion) -> _Saida:
    if not resposta.choices:
        raise ErroLLM("Resposta do modelo sem escolhas")
    escolha = resposta.choices[0]
    if escolha.finish_reason == "length":
        raise ErroSaidaForaDoEsquema(TRUNCADA)
    if escolha.message.refusal:
        raise ErroLLM(f"O modelo recusou o pedido: {escolha.message.refusal}")
    if escolha.finish_reason != "stop" or not escolha.message.content:
        raise ErroLLM(f"Resposta do modelo terminada por {escolha.finish_reason}")
    uso = resposta.usage
    cache = uso.prompt_tokens_details if uso else None
    raciocinio = uso.completion_tokens_details if uso else None
    return _Saida(
        texto=escolha.message.content,
        modelo=resposta.model,
        uso=Uso(
            entrada=uso.prompt_tokens if uso else 0,
            entrada_em_cache=(cache.cached_tokens or 0) if cache else 0,
            saida=uso.completion_tokens if uso else 0,
            raciocinio=(raciocinio.reasoning_tokens or 0) if raciocinio else 0,
        ),
        nivel_servico=resposta.service_tier,
    )


def _mensagem(erro: APIStatusError) -> str:
    """Mensagem do provedor, sem o prefixo do SDK."""
    corpo = erro.body
    if isinstance(corpo, dict) and isinstance(corpo.get("message"), str):
        return str(corpo["message"])
    return erro.message
