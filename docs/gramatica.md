# Mini-linguagem das expressões

O Modelador escreve a função objetivo e cada restrição como texto nesta
mini-linguagem (ADR-002). A sintaxe é a de Python, que os modelos de
linguagem já conhecem. O compilador (`po_multiagente.modelo`) analisa, checa
e instancia o texto; ninguém o executa como código.

## Elementos

| Elemento | Exemplo | Observação |
|---|---|---|
| Número | `200`, `0.5`, `1e3` | Ponto decimal. Constantes da descrição; os dados vêm dos parâmetros |
| Parâmetro ou variável escalar | `orcamento`, `y` | Declarado no modelo |
| Parâmetro ou variável indexada | `custo[i, j]` | Um índice por conjunto declarado, na mesma ordem |
| Membro fixo | `x["Loja A"]` | Entre aspas; precisa existir no conjunto |
| Somatório | `sum(c[i] * x[i] for i in PRODUTOS)` | Uma ou mais cláusulas `for ... in ...` |
| Operadores | `+ - * /` e parênteses | Precedência usual; associam à esquerda |
| Relação (só em restrição) | `<=`, `>=`, `==` | Uma por restrição |

Palavras reservadas: `sum`, `for`, `in`.

## Regras checadas na compilação

A compilação reúne todos os erros e os localiza pelo id da restrição ou por
`objetivo`. Pela ADR-008, esses erros voltam ao Modelador como nova
tentativa de formato, iguais nas duas configurações do experimento.

- Todo nome é parâmetro ou variável declarada. Um conjunto não é valor; um
  índice também não.
- Cada referência tem o número de índices declarado, e cada índice percorre
  o conjunto que a posição espera: se `x` é indexada por `PRODUTOS`, então
  `x[m]` com `m` em `MESES` é erro.
- Todo índice de `para_todo` e de somatório é usado.
- O modelo é linear: não há produto de variáveis nem divisão por variável.
- Objetivo e restrições contêm ao menos uma variável.
- Não há desigualdade estrita (`<`, `>`), que não existe em PL.

## Unidades (sinal S2)

As unidades dos parâmetros vêm do quadro de especificação, e as das
variáveis, do modelo. Notação: `R$/un`, `h/un`, `R$/(t·km)`, `m^2`,
`adimensional`. Tudo o que vem depois de `/` é denominador até o próximo
`/`: `R$/t·km` é real por tonelada-quilômetro. Algumas grafias equivalem
(`h`, `hora`, `horas`), mas não há conversão entre `km` e `m`: converter
unidade é tratamento de dado.

Números escritos na expressão não têm unidade: somados ou comparados,
assumem a do outro lado; multiplicando, contam como adimensionais.

## Exemplo

Alocação da produção com três famílias de restrições:

```text
objetivo    sum(margem[p] * x[p] for p in PRODUTOS)
marcenaria  sum(h_marc[p] * x[p] for p in PRODUTOS) <= cap_marc
acabamento  sum(h_acab[p] * x[p] for p in PRODUTOS) <= cap_acab
pedidos     x[p] <= pedidos[p]                      para_todo p em PRODUTOS
```
