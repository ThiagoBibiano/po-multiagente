import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from openai import APIConnectionError, BadRequestError

from po_multiagente.config import carregar_perfil
from po_multiagente.dominio import Especificacao, ModeloIR
from po_multiagente.llm import (
    AdaptadorOpenAI,
    Cassete,
    ErroLLM,
    ErroSaidaForaDoEsquema,
    LLMRoteirizado,
    Pedido,
    RespostaLLM,
    Uso,
    esquema_estrito,
)
from po_multiagente.llm.adaptador_openai import TRUNCADA

PEDIDO = Pedido("modelador", "instruções", "entrada", "Saida", {"type": "object"})


def todos_os_objetos(no: Any) -> list[dict[str, Any]]:
    if isinstance(no, dict):
        proprio = [no] if no.get("type") == "object" else []
        return proprio + [o for v in no.values() for o in todos_os_objetos(v)]
    if isinstance(no, list):
        return [o for v in no for o in todos_os_objetos(v)]
    return []


@pytest.mark.parametrize("modelo", [ModeloIR, Especificacao])
def test_esquema_estrito_exige_todas_as_propriedades(modelo: type) -> None:
    esquema = esquema_estrito(modelo)
    objetos = todos_os_objetos(esquema)
    assert objetos
    for objeto in objetos:
        assert objeto["additionalProperties"] is False
        assert set(objeto["required"]) == set(objeto["properties"])
    texto = json.dumps(esquema)
    assert '"default"' not in texto
    assert '"title"' not in texto


class ClienteFalso:
    def __init__(self, respostas: list[Any]) -> None:
        self.respostas = respostas
        self.chamadas: list[dict[str, Any]] = []
        self.responses = self
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def resposta_api(
    texto: str = '{"ok": 1}', status: str = "completed", motivo: str | None = None
) -> SimpleNamespace:
    uso = SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        input_tokens_details=SimpleNamespace(cached_tokens=20),
        output_tokens_details=SimpleNamespace(reasoning_tokens=30),
    )
    return SimpleNamespace(
        output_text=texto,
        status=status,
        usage=uso,
        model="gpt-6-luna",
        incomplete_details=SimpleNamespace(reason=motivo) if motivo else None,
    )


def test_adaptador_envia_esquema_estrito_e_raciocinio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    cliente = ClienteFalso([resposta_api()])
    adaptador = AdaptadorOpenAI(carregar_perfil("gpt-6-luna"), cliente)  # type: ignore[arg-type]
    resposta = adaptador.gerar(PEDIDO)
    (chamada,) = cliente.chamadas
    assert chamada["model"] == "gpt-6-luna"
    assert chamada["text"]["format"]["strict"] is True
    assert chamada["reasoning"] == {"effort": "low"}
    assert chamada["store"] is False
    assert "temperature" not in adaptador.parametros()
    assert resposta.uso == Uso(entrada=100, entrada_em_cache=20, saida=50, raciocinio=30)


def test_adaptador_tenta_de_novo_em_falha_de_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    erro = APIConnectionError(request=SimpleNamespace())  # type: ignore[arg-type]
    cliente = ClienteFalso([erro, resposta_api()])
    assert AdaptadorOpenAI(carregar_perfil("gpt-6-luna"), cliente).gerar(PEDIDO).texto  # type: ignore[arg-type]


def test_adaptador_distingue_recusa_por_esquema() -> None:
    requisicao = httpx2.Request("POST", "https://chat.maritaca.ai/api/responses")
    corpo = {"message": "[] should be non-empty", "code": "model_output_schema_mismatch"}
    recusa = BadRequestError("400", response=httpx2.Response(400, request=requisicao), body=corpo)
    cliente = ClienteFalso([recusa])
    with pytest.raises(ErroSaidaForaDoEsquema, match=r"^\[\] should be non-empty$"):
        AdaptadorOpenAI(carregar_perfil("sabiazinho-4"), cliente).gerar(PEDIDO)  # type: ignore[arg-type]
    assert len(cliente.chamadas) == 1


@pytest.mark.parametrize("perfil", ["gpt-6-luna", "sabiazinho-4"])
def test_adaptador_trata_saida_cortada_como_fora_do_esquema(perfil: str) -> None:
    requisicao = httpx2.Request("POST", "https://chat.maritaca.ai/api/responses")
    corte = BadRequestError(
        "400",
        response=httpx2.Response(400, request=requisicao),
        body={"message": "truncated: " + "{" * 5000, "code": "max_tokens_reached"},
    )
    respostas: dict[str, Any] = {
        "gpt-6-luna": resposta_api(status="incomplete", motivo="max_output_tokens"),
        "sabiazinho-4": corte,
    }
    cliente = ClienteFalso([respostas[perfil]])
    with pytest.raises(ErroSaidaForaDoEsquema) as erro:
        AdaptadorOpenAI(carregar_perfil(perfil), cliente).gerar(PEDIDO)  # type: ignore[arg-type]
    assert str(erro.value) == TRUNCADA


def resposta_chat(
    texto: str | None = '{"ok": 1}', fim: str = "stop", nivel: str | None = "flex"
) -> SimpleNamespace:
    uso = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=50,
        prompt_tokens_details=SimpleNamespace(cached_tokens=20),
        completion_tokens_details=None,
    )
    mensagem = SimpleNamespace(content=texto, refusal=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=fim, message=mensagem)],
        usage=uso,
        model="sabiazinho-4",
        service_tier=nivel,
    )


def test_adaptador_chat_pede_flex_e_registra_o_nivel_atendido() -> None:
    perfil = carregar_perfil("sabiazinho-4-flex")
    cliente = ClienteFalso([resposta_chat(), resposta_chat(nivel="default")])
    adaptador = AdaptadorOpenAI(perfil, cliente)  # type: ignore[arg-type]
    resposta = adaptador.gerar(PEDIDO)
    chamada = cliente.chamadas[0]
    assert chamada["service_tier"] == "flex"
    assert chamada["messages"][0] == {"role": "system", "content": "instruções"}
    assert chamada["response_format"]["json_schema"]["strict"] is True
    assert chamada["max_completion_tokens"] == perfil.max_saida_tokens
    assert "store" not in chamada
    assert resposta.uso == Uso(entrada=100, entrada_em_cache=20, saida=50, raciocinio=0)
    assert resposta.parametros["service_tier"] == "flex"
    assert adaptador.gerar(PEDIDO).parametros["service_tier"] == "default"


def test_adaptador_chat_trata_corte_e_resposta_vazia() -> None:
    perfil = carregar_perfil("sabiazinho-4-flex")
    cliente = ClienteFalso([resposta_chat(fim="length"), resposta_chat(texto=None)])
    with pytest.raises(ErroSaidaForaDoEsquema, match="limite de tokens"):
        AdaptadorOpenAI(perfil, cliente).gerar(PEDIDO)  # type: ignore[arg-type]
    with pytest.raises(ErroLLM, match="terminada por stop"):
        AdaptadorOpenAI(perfil, cliente).gerar(PEDIDO)  # type: ignore[arg-type]


def test_adaptador_rejeita_resposta_incompleta() -> None:
    cliente = ClienteFalso([resposta_api(status="incomplete")])
    with pytest.raises(ErroLLM, match="incomplete"):
        AdaptadorOpenAI(carregar_perfil("gpt-6-luna"), cliente).gerar(PEDIDO)  # type: ignore[arg-type]


def test_adaptador_exige_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ErroLLM, match="OPENAI_API_KEY"):
        AdaptadorOpenAI(carregar_perfil("gpt-6-luna"))


def test_perfil_da_maritaca_usa_endpoint_e_chave_proprios(monkeypatch: pytest.MonkeyPatch) -> None:
    perfil = carregar_perfil("sabiazinho-4")
    monkeypatch.delenv("MARITACA_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "chave-da-openai")
    with pytest.raises(ErroLLM, match="MARITACA_API_KEY"):
        AdaptadorOpenAI(perfil)
    monkeypatch.setenv("MARITACA_API_KEY", "chave-da-maritaca")
    cliente = AdaptadorOpenAI(perfil)._cliente
    assert str(cliente.base_url).rstrip("/") == "https://chat.maritaca.ai/api"
    assert cliente.api_key == "chave-da-maritaca"
    assert AdaptadorOpenAI(perfil, ClienteFalso([])).parametros() == {  # type: ignore[arg-type]
        "max_output_tokens": 16000,
        "temperature": 0.0,
    }
    assert perfil.moeda == "BRL"
    assert perfil.custo(1_000_000, 0, 1_000_000) == pytest.approx(5.0)


def test_cassete_grava_e_reproduz(tmp_path: Path) -> None:
    arquivo = tmp_path / "cassete.jsonl"
    real = LLMRoteirizado({"modelador": [{"a": 1}]})
    assert Cassete(arquivo, "gravar", real).gerar(PEDIDO).texto == '{"a": 1}'
    reproduzida = Cassete(arquivo, "reproduzir", modelo="roteirizado").gerar(PEDIDO)
    assert reproduzida == RespostaLLM(texto='{"a": 1}', modelo="roteirizado", gravada=True)
    outro = Pedido("modelador", "instruções", "outra entrada", "Saida", {"type": "object"})
    with pytest.raises(ErroLLM, match="não gravada"):
        Cassete(arquivo, "reproduzir", modelo="roteirizado").gerar(outro)
    with pytest.raises(ValueError, match="modelo real"):
        Cassete(arquivo, "gravar")


def test_cassete_grava_e_reproduz_recusa(tmp_path: Path) -> None:
    def recusa(_: Pedido) -> dict[str, Any]:
        raise ErroSaidaForaDoEsquema("fora do esquema")

    arquivo = tmp_path / "cassete.jsonl"
    real = LLMRoteirizado({"modelador": [recusa]})
    with pytest.raises(ErroSaidaForaDoEsquema):
        Cassete(arquivo, "gravar", real).gerar(PEDIDO)
    with pytest.raises(ErroSaidaForaDoEsquema, match="fora do esquema"):
        Cassete(arquivo, "reproduzir", modelo="roteirizado").gerar(PEDIDO)


def test_roteiro_esgotado() -> None:
    with pytest.raises(ErroLLM, match="Roteiro sem resposta"):
        LLMRoteirizado({}).gerar(PEDIDO)


def test_perfil_rejeita_temperatura_com_raciocinio() -> None:
    perfil = carregar_perfil("gpt-6-luna")
    with pytest.raises(ValueError, match="rejeita temperature"):
        type(perfil).model_validate({**perfil.model_dump(), "temperatura": 0.2})
    sem_raciocinio = type(perfil).model_validate(
        {**perfil.model_dump(), "temperatura": 0.2, "esforco_raciocinio": "none"}
    )
    assert AdaptadorOpenAI(sem_raciocinio, ClienteFalso([])).parametros()["temperature"] == 0.2  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        carregar_perfil("inexistente")
