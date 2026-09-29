# po-multiagente

Plataforma multiagente *low-code* que formula, resolve e explica problemas de
programação linear (PL) e linear inteira mista (PLIM) descritos em português,
com os parâmetros obtidos de planilhas do próprio usuário.

> **Estado:** em construção: agentes calibrados (F2) e interface mínima no
> Colab (F4). Artefato do Trabalho de
> Graduação *Plataforma multiagente low-code para formulação e resolução de
> problemas de programação linear e linear inteira mista a partir de
> descrições em língua portuguesa*. O roteiro
> está em [`docs/plano.md`](docs/plano.md).

## Como funciona

Cinco agentes especializados trabalham sobre um estado compartilhado:

| Agente | Faz | Entrega |
|---|---|---|
| Interpretador | Lê a descrição e as fontes de dados; pede ao usuário o tratamento de dado que faltar | Quadro de especificação |
| Modelador | Formula o modelo em representação intermediária | Modelo em JSON, com o requisito de origem de cada restrição |
| Gerador-Executor | Compila o modelo de forma determinística e chama o solver | Resultado do solver |
| Validador | Verifica o modelo com cinco sinais externos e devolve o erro localizado | Parecer das validações |
| Explicador | Traduz o resultado para a linguagem do negócio | Explicação final |

A solução vem sempre do solver, nunca do modelo de linguagem, e toda execução
gera um dossiê com cada artefato intermediário.

## Para quem usa (Google Colab)

Abra [`notebooks/colab.ipynb`](notebooks/colab.ipynb) no Colab, crie o segredo
`GEMINI_API_KEY` (gratuito em [aistudio.google.com](https://aistudio.google.com/apikey))
e rode as células:

```python
%pip install -q "po-multiagente[interface] @ git+https://github.com/ThiagoBibiano/po-multiagente@develop"
from po_multiagente import iniciar
iniciar()
```

A interface guia em etapas: descrever o problema e enviar as planilhas,
esclarecer os dados que a plataforma não conseguir ler e ver o resultado, com
a explicação primeiro e a formulação, a especificação e as validações em abas.
O botão *Carregar exemplo* traz o piloto da marcenaria.

## Para quem pesquisa

O pacote inclui o experimento pareado com e sem o agente Validador e a
avaliação contra gabaritos (fase F6). As decisões de projeto estão em
[`docs/adr/`](docs/adr/).

## Para quem contribui

```bash
uv sync --all-groups
uv run pre-commit install
uv run pytest
```

Veja [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licença

MIT. Veja [`LICENSE`](LICENSE).
