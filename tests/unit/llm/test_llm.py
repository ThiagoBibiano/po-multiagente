import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openai import APIConnectionError

from po_multiagente.config import carregar_perfil
from po_multiagente.dominio import Especificacao, ModeloIR
from po_multiagente.llm import (
    AdaptadorOpenAI,
    Cassete,
    ErroLLM,
    LLMRoteirizado,
    Pedido,
    RespostaLLM,
    Uso,
    esquema_estrito,
)

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

    def create(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def resposta_api(texto: str = '{"ok": 1}', status: str = "completed") -> SimpleNamespace:
    uso = SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        input_tokens_details=SimpleNamespace(cached_tokens=20),
        output_tokens_details=SimpleNamespace(reasoning_tokens=30),
    )
    return SimpleNamespace(
        output_text=texto, status=status, usage=uso, model="gpt-6-luna", incomplete_details=None
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


def test_adaptador_rejeita_resposta_incompleta() -> None:
    cliente = ClienteFalso([resposta_api(status="incomplete")])
    with pytest.raises(ErroLLM, match="incomplete"):
        AdaptadorOpenAI(carregar_perfil("gpt-6-luna"), cliente).gerar(PEDIDO)  # type: ignore[arg-type]


def test_adaptador_exige_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ErroLLM, match="OPENAI_API_KEY"):
        AdaptadorOpenAI(carregar_perfil("gpt-6-luna"))


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
