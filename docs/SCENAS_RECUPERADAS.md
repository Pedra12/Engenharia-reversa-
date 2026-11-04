# Cenas e mapas identificados nos dados Unity

## Resultado da segunda auditoria

A segunda passagem leu 70.657 objetos de 21 arquivos serializados, registrou 138.983 referências PPtr e extraiu 21.666 transformações. Os arquivos level0 a level9 aparecem separadamente no catálogo. Isso permite distinguir dados de cena serializados de simples modelos avulsos.

## Raízes de mapa confirmadas por hierarquia

| Arquivo | Raiz de mapa | Partes de cenário como filhos diretos |
|---|---|---:|
| level1 | lvl_baghdad | 7 |
| level2 | lvl_assault | 7 |
| level3 | lvl_middle_east | 5 |
| level4 | lvl_resort | 9 |
| level5 | lvl_forest | 6 |
| level6 | lvl_house | 4 |
| level7 | lvl_india | 3 |
| level8 | lvl_rome | 5 |
| level9 | lvl_deluxe_fest | 3 |

Esses nomes e relações vêm de objetos Transform/GameObject e dos pais/filhos serializados. São evidência direta de grupos de cenário organizados em arquivos levelN. Não provam, sozinhos, que todos os materiais, colisores, scripts e dependências estejam íntegros nem que a fase já esteja pronta para jogar.

## Exemplo detalhado: Forest

O arquivo level5 contém a raiz lvl_forest, na origem (0, 0, 0), escala (1, 1, 1), com seis grupos filhos:

| Grupo | Posição local (X, Y, Z) |
|---|---|
| sm_forest_s3 | (-54.000, 12.375, 7.000) |
| sm_forest_s1 | (-47.095, -5.786, -5.342) |
| sm_forest_s2 | (-50.243, -0.506, -0.882) |
| sm_forest_s4_background | (-48.790, -8.807, -0.000) |
| sm_forest_alpha_0 | (-50.636, -1.461, 12.745) |
| sm_forest_alpha_1 | (-61.383, -2.849, 20.531) |

Há ainda objetos de spawn, captura, câmera, iluminação e gerenciadores dentro dos arquivos de nível. A auditoria relacional também identificou componentes MeshFilter, MeshRenderer, MeshCollider, Light, Animator, NavMeshData e outros.

## level0

level0 contém raízes como CharacterAndGunsForShop, BattlePassTutorialManager, InputSystem, Lights, MainCamera, MainMenuTutorial e Managers. A evidência aponta para conteúdo global/menu/serviços, mas a função exata de cada raiz ainda será validada pelos componentes e scripts ligados.

## Primeira conversão para Godot

A ferramenta agora gera nove manifestos de mapas, exporta malhas OBJ com nomes únicos (70 malhas nesta execução) e exporta 353 texturas PNG com origem e path_id. As referências de MeshFilter, MeshRenderer, MeshCollider e materiais foram relacionadas entre arquivos serializados externos quando disponíveis.

Foi gerado um projeto Godot 4.4.1 de pré-visualização do Forest. Ele contém a hierarquia recuperada de 7 nós, 5 malhas OBJ utilizadas e 2 texturas PNG utilizadas. O projeto foi importado e executado em modo headless no GitHub Actions; a execução confirmou `FOREST_SCENE_LOADED nodes=7` sem erros de runtime nessa última validação. Isso valida a estrutura e o carregamento do protótipo, mas não substitui inspeção visual no dispositivo nem confirma que o mapa já seja jogável.

## Próxima etapa

1. Completar a resolução das referências PPtr restantes e ampliar os dados de materiais, texturas e lightmaps.
2. Relacionar cada GameObject de cenário aos seus componentes e aos objetos Mesh correspondentes.
3. Exportar transformações completas e recursos usados por cada um dos nove mapas.
4. Melhorar a cena Forest na Godot, incluindo materiais, colisões, iluminação e navegação recuperáveis.
5. Fazer inspeção visual e testes de movimento/colisão antes de classificá-la como mapa jogável.

## Limitações atuais

- A extração anterior exportou 58 malhas OBJ e a nova auditoria relacional registrou referências de malha. Ainda é necessário resolver as referências externas para identificar todos os Mesh IDs correspondentes.
- A auditoria Unity anterior registrou 29.076 erros individuais de exportação. Isso não significa 29.076 recursos perdidos, mas exige tratamento específico.
- Os arquivos de cena serializados não equivalem a um projeto Unity original completo.
- Não há ainda uma cena Godot validada nem APK jogável deste projeto.
- A extração técnica não concede automaticamente direitos de redistribuição dos recursos proprietários do jogo original.