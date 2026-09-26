"""Perfis de modelo de linguagem e configuração de execução."""

from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, PositiveInt, model_validator

EsforcoRaciocinio = Literal["none", "low", "medium", "high", "xhigh", "max"]


class _Estrito(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Precos(_Estrito):
    """Preços em dólares por milhão de tokens."""

    entrada: NonNegativeFloat
    entrada_em_cache: NonNegativeFloat
    saida: NonNegativeFloat


class PerfilModelo(_Estrito):
    """Capacidades e parâmetros de um modelo de linguagem (ADR-003).

    Attributes:
        temperatura: Aplicada só quando o provedor a aceita (nos modelos de
            raciocínio da OpenAI, só com ``esforco_raciocinio: none``).
    """

    id: str
    provedor: Literal["openai"]
    api: Literal["responses"]
    modelo: str
    esforco_raciocinio: EsforcoRaciocinio | None = None
    temperatura: float | None = None
    max_saida_tokens: PositiveInt
    saida_estruturada_estrita: bool
    aceita_seed: bool
    precos_usd_por_milhao: Precos

    @model_validator(mode="after")
    def _temperatura_so_sem_raciocinio(self) -> "PerfilModelo":
        if self.temperatura is not None and self.esforco_raciocinio not in (None, "none"):
            raise ValueError(
                "Com raciocínio ativo, a API rejeita temperature; use esforco_raciocinio: none"
            )
        return self

    def custo_usd(self, entrada: int, entrada_em_cache: int, saida: int) -> float:
        """Custo de uma chamada; os tokens em cache estão contidos em ``entrada``."""
        precos = self.precos_usd_por_milhao
        return (
            (entrada - entrada_em_cache) * precos.entrada
            + entrada_em_cache * precos.entrada_em_cache
            + saida * precos.saida
        ) / 1e6


def carregar_perfil(nome: str) -> PerfilModelo:
    """Carrega um perfil distribuído com o pacote (``config/modelos/<nome>.yaml``).

    Raises:
        FileNotFoundError: Se não houver perfil com esse nome.
    """
    arquivo = files("po_multiagente.config").joinpath("modelos", f"{nome}.yaml")
    if not arquivo.is_file():
        raise FileNotFoundError(f"Perfil de modelo {nome!r} não encontrado")
    return PerfilModelo.model_validate(yaml.safe_load(arquivo.read_text(encoding="utf-8")))


class ConfiguracaoExecucao(_Estrito):
    """Tudo o que define uma execução e fica igual entre as configurações do experimento.

    Só ``validador`` muda entre as duas configurações (Passo 7).
    """

    perfil_modelo: str = "gpt-6-luna"
    validador: bool = True
    max_iteracoes_validador: PositiveInt = Field(default=3, description="K do cap. 3")
    max_tentativas_formato: PositiveInt = Field(default=3, description="ADR-008")
    max_rodadas_tratamento: PositiveInt = 2
    backend_solver: str = "pulp"
    motor_solver: str = "cbc"
    limite_tempo_solver_s: float | None = 60.0
