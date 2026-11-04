# Plano mestre: engenharia reversa do Block Gun 3D e reconstrução na Godot

## Objetivo e limites

Este repositório é o projeto independente de engenharia reversa do pacote Block Gun 3D 2.0.3 e de desenvolvimento de um jogo próprio na Godot 4, usando como referência técnica e biblioteca de recursos tudo o que for recuperável do arquivo enviado.

Este projeto NÃO compartilha código, cenas, personagens, mapas ou decisões de implementação com o repositório FreeFire3D. O FreeFire3D está fora do escopo.

O objetivo é investigar o pacote inteiro, inclusive arquivos aninhados, recursos binários, dados Unity, bibliotecas, scripts decompilados, configurações, sons, texturas, modelos, animações, interfaces e referências entre objetos. Nenhuma categoria deve ser descartada apenas por parecer secundária.

A expressão “usar tudo” significa inventariar, entender e testar todos os recursos tecnicamente relevantes. Nem todo arquivo será diretamente importável na Godot: alguns exigirão conversão, reconstrução ou poderão estar incompletos/corrompidos. As limitações serão registradas, não escondidas.

## Estado inicial confirmado

- Arquivo de referência ZIP: aproximadamente 416 MB.
- Inventário recursivo anterior: aproximadamente 72,850 entradas e 1.46 GB descompactados.
- Dados Unity divididos: 21 famílias `.split` reconstruídas com 148 partes.
- Auditoria Unity anterior: 70,657 objetos catalogados, 78 tipos, 1,584 objetos exportados e 29,076 erros individuais de exportação.
- Exportações já obtidas: texturas/sprites PNG, malhas OBJ e áudio WAV.
- Tipos encontrados incluem GameObject, Transform, MeshRenderer, MeshFilter, MeshCollider, SkinnedMeshRenderer, Animator, AnimationClip, Material, Texture2D, AudioClip, NavMeshData, Light, Camera e outros.
- Foram identificadas partes de cenários com nomes associados a Forest, Middle East, India, Rome, Resort, Assault e Baghdad.
- Não foi recuperado um projeto Unity original convencional com cenas `.unity`, prefabs, `ProjectSettings` e `Packages` completos.
- Há evidência de dados de cena serializados e recursos parciais, mas ainda não está comprovado que uma fase inteira possa ser reconstituída sem perdas.
- O código IL2CPP original não pode ser presumido recuperável integralmente. Stubs e nomes de classes/métodos ajudam a entender arquitetura e comportamento, mas não equivalem ao código-fonte original.

## Princípios de trabalho

1. Preservar o ZIP original e seu SHA-256; nunca modificar a fonte.
2. Trabalhar em etapas reproduzíveis por GitHub Actions, guardando relatórios e artefatos.
3. Manter inventário com caminho original, tamanho, hash, tipo, origem, dependências, resultado de extração e motivo de falha.
4. Relacionar objetos Unity por `path_id`, referências PPtr, arquivo serializado, hierarquia e transformações.
5. Separar claramente recurso extraído, recurso convertido, recurso reconstruído e recurso ainda não validado.
6. Não declarar mapa, animação, arma ou sistema como funcional antes de teste na Godot.
7. Criar um projeto Godot independente e versionado, sem misturar o projeto FreeFire3D.
8. Manter os recursos originais e os convertidos organizados; não sobrescrever a evidência original.
9. Registrar licenças e direitos de uso. A extração técnica não concede automaticamente direito de redistribuir conteúdo proprietário do jogo original. Para distribuição pública, usar apenas recursos com autorização/licença compatível ou substitutos próprios.

## Fases

### Fase 1 - Auditoria integral e preservação
- Confirmar integridade do arquivo de origem pelo SHA-256.
- Inventariar todas as pastas e subpastas, inclusive arquivos ocultos, extensões desconhecidas e duplicatas.
- Calcular hashes e tamanhos; agrupar arquivos por formato e provável função.
- Identificar APK/DEX/manifest, IL2CPP, bibliotecas nativas, dados Unity, bundles, arquivos serializados, sidecars e recursos externos.
- Produzir matriz de extração: sucesso, parcial, falha e causa.
- Não encerrar a auditoria enquanto houver famílias de arquivos sem classificação.

### Fase 2 - Engenharia reversa de dados e comportamento
- Reconstruir arquivos `.split` e associar `.resource`/`.ress`.
- Fazer segunda leitura Unity com resolução de referências PPtr.
- Reconstruir GameObject -> Transform -> componentes; capturar pai/filhos, posição, rotação, escala, ativo, layer, tag e arquivo de origem.
- Associar MeshFilter/SkinnedMeshRenderer a Mesh; Renderer a Material; Material a Shader e Textures.
- Catalogar esqueletos, clips, controllers, eventos e relações de animação.
- Investigar cenas serializadas, raízes de cena, spawn points, colisões, NavMesh, câmeras e iluminação.
- Mapear scripts, classes, enums, strings, estados, modos, armas, bots, UI, rede e fluxo de partida.
- Documentar o que é evidência direta e o que é inferência.

### Fase 3 - Conversão e biblioteca Godot
- Criar estrutura de projeto Godot 4.
- Converter/importar modelos para formatos aceitos pela Godot quando possível (preferência por glTF/GLB; OBJ como fonte intermediária).
- Converter texturas, áudio e materiais; registrar parâmetros não suportados.
- Recriar hierarquias e transformações a partir dos dados serializados.
- Converter ou reconstruir colisões, navegação, iluminação e animações.
- Gerar cenas Godot por ferramenta, com relatórios de validação e referências aos arquivos de origem.
- Não duplicar desnecessariamente recursos compartilhados.

### Fase 4 - Reconstrução do jogo próprio
- Recriar primeiro o loop essencial: inicialização, menu, seleção, partida, spawn, movimento, câmera, combate, dano, morte e resultado.
- Recriar modos e sistemas somente conforme evidência encontrada no pacote e testes.
- Recriar bots, armas, equipamentos, UI, áudio e progressão a partir do inventário e da análise.
- Implementar código próprio na Godot; usar o material decompilado como evidência técnica, não como promessa de código-fonte original recuperado.

### Fase 5 - Validação e Android
- Testar cada cena e sistema isoladamente no desktop/CI quando possível.
- Executar testes de importação, referências ausentes, colisões, animações e recursos.
- Exportar APK Android e testar no dispositivo real.
- Medir FPS, memória, tempo de carregamento, tamanho do APK e estabilidade.
- Corrigir problemas antes de avançar para conteúdo adicional.

## Próxima tarefa técnica imediata

Criar uma auditoria Unity de segunda passagem que preserve os arquivos serializados temporários durante a execução e gere um catálogo relacional, não apenas uma lista rasa de objetos. O relatório deve incluir:

- nome real do arquivo serializado de origem;
- tipo, nome, `path_id` e referências PPtr;
- hierarquia GameObject/Transform;
- posição, rotação e escala locais;
- MeshFilter e SkinnedMeshRenderer ligados às malhas;
- MeshRenderer e materiais ligados às texturas;
- colliders, rigidbodies, animator/controllers/clips;
- dados de cena, raízes, câmeras, luzes, spawn points e NavMesh;
- erros e referências não resolvidas.

A primeira amostra de reconstrução será o ambiente Forest, por ser um alvo de teste já identificado no catálogo. Forest é apenas o primeiro caso de validação, não uma decisão de ignorar os demais mapas.

## Critério de conclusão

Uma categoria só será marcada como concluída quando houver inventário verificável, conversão ou justificativa técnica documentada e teste correspondente. “Arquivo exportado” não significa “recurso funcional”; “cena gerada” não significa “mapa jogável”.