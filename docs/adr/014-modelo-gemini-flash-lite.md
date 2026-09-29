# ADR-014: Modelo do experimento: gemini-3.5-flash-lite, nível gratuito

- **Estado:** aceita (substitui a escolha de modelo da ADR-012)
- **Data:** 2026-09-28

## Contexto

A ADR-012 escolheu o gpt-6-luna, mas a conta da OpenAI não tem créditos, e o
autor quer gastar o mínimo viável. Na partição de ajuste (24 instâncias, uma
repetição, com e sem Validador), o gemini-3.5-flash-lite no nível gratuito
acertou 22/24 nas duas configurações; o sabiazinho-4 (Maritaca), cerca de
9/24 (plano, seção 11).

## Decisão

- Modelo: `gemini-3.5-flash-lite`, perfil padrão da execução, pelo endpoint
  do Gemini compatível com a OpenAI (API de Chat Completions, saída
  estruturada estrita).
- Parâmetros fixos no perfil: `temperature: 0.0`, sem esforço de raciocínio
  explícito (a API recusa `none`; o padrão não gera tokens de raciocínio).
- Nível gratuito. Nesse nível, a Google usa os dados para melhorar os
  produtos; o autor aceita isso, inclusive para o conjunto-teste.

## Consequências

- Custo zero. O registro guarda o custo de referência do nível pago
  (US$ 0,30 e 2,50 por milhão de tokens de entrada e de saída).
- O cap. 3 pode manter a temperatura como parâmetro de inferência fixo e
  registrado; a troca por "esforço de raciocínio" prevista na ADR-012 deixa
  de valer.
- A latência do nível gratuito varia (de 10 a 180 s por chamada), e há
  limites diários não documentados; um lote pode parar e precisar ser
  retomado.
- O perfil `gpt-6-luna` continua no pacote, e trocar de modelo segue sendo
  trocar de perfil (ADR-003).
