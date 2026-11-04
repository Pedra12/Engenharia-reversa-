# Engenharia reversa do Block Gun 3D

Projeto independente para investigar o pacote Block Gun 3D 2.0.3 e reconstruir um jogo próprio na Godot 4 usando todos os recursos tecnicamente recuperáveis.

**Este repositório não faz parte do projeto FreeFire3D e não deve receber arquivos ou decisões daquele projeto.**

## Plano e documentação

- [Plano mestre e fases do projeto](docs/PLANO_MESTRE.md)
- [Cenas e mapas recuperados](docs/SCENAS_RECUPERADAS.md)
- [Análise técnica inicial](BLOCKGUN_ANALYSIS.md)
- [Inventário recursivo](BLOCKGUN_DEEP_INVENTORY.md)

## Protótipo Godot

A primeira pré-visualização do mapa Forest é gerada e validada automaticamente no workflow [Recursive Block Gun inventory](https://github.com/Pedra12/Engenharia-reversa-/actions/workflows/analyze-blockgun.yml). O projeto Godot e os recursos convertidos ficam no artefato da execução mais recente.

## Princípio

Todo o conteúdo do arquivo de referência será inventariado e investigado. Recursos serão classificados como extraídos, convertidos, reconstruídos, não recuperáveis ou ainda não validados. Nenhum recurso será declarado funcional sem teste.
