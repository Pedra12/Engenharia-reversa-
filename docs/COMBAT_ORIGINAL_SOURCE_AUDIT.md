# Auditoria da fonte original do sistema de batalha

## Regra principal

A pasta/release original descompilada é a fonte de verdade para reconstruir o combate. Inventários anteriores são índices auxiliares, nunca substitutos da inspeção dos arquivos originais. Quando um dado necessário não estiver no inventário, executar nova extração na fonte original e percorrer referências, prefabs, transformações, malhas, materiais, animações, áudio e componentes.

Não substituir estruturas originais por aproximações sem primeiro verificar se a estrutura exata existe na fonte.

## Fonte verificada

- Repositório: `Pedra12/Engenharia-reversa-`
- Release: `V1.0`
- Arquivo: `Block+Gun+3D_+FPS+Shooter+PvP_2.0.3_APKPure.apk_Decompiler.com.zip`
- Tamanho informado pelo release: aproximadamente 416 MB
- SHA-256 verificado pela auditoria: `e3e3cc4afac58236657240cc8c403fb56c9b02c9f8efa3b77bcc6044b1b480c0`
- Branch de trabalho: `feature/floresta-combate-mobile`
- Auditoria profunda: workflow `Block Gun - Deep original combat forensics`
- Execução: `42328770707`
- Artefato: `BlockGun-Combat-Deep-Audit`

## O que foi recuperado/indexado

A segunda auditoria produziu:

- 2.217 arquivos C# extraídos, 891 identificados por nomes/conteúdo relacionados a gameplay.
- 96 MonoScripts no bundle de Addressables analisado.
- 2.263 GameObjects do bundle indexados por hierarquia e componentes.
- 726 componentes classificados como relevantes para gameplay.
- 252 elementos de HUD/controles identificados nas cenas verificadas.
- 4 raízes de hierarquia de rig catalogadas.
- 3 malhas skinned no conjunto de rigs original auditado.
- 91 clipes de animação catalogados.
- 7 Animator Controllers catalogados.

A lista global de MonoScripts do catálogo original contém milhares de classes. Entre as classes relevantes estão `FirstPersonController`, `CharacterMotorBase`, `Player`, `AimAssistController`, `Crosshair`, `CanFire`, `Bullet`, `BulletData`, `WeaponBase`, `LocalWeapon`, `RemoteWeapon`, `WeaponAnimation`, `WeaponMovements`, `WeaponSoundManager`, `WeaponLoader`, `PhotonAIInput`, `PhotonAICharacter`, `AIController`, `NavMeshMovement`, `SpawnPointManager`, `SpawnPoint`, `CharacterHands`, `HandRigSaver`, `HandRigDataContainer`, `AnimationEventsHandler` e `FollowCamerasManager`.

## Arquitetura original do jogador

O prefab original separa o jogador local do corpo remoto:

- `LocalPlayer`: controle, entrada e câmera local.
- `LocalAnimator`: animação local.
- `MainCamera`: câmera em primeira pessoa.
- `LocalGuns`: armas locais.
- `RemotePlayer`: corpo completo e sockets para arma/mãos.
- `FollowCamera`, `DeathCamera` e `KillCam`: câmeras de acompanhamento, morte e replay.
- `RemoteAimPoint` e pontos auxiliares de mira.

O protótipo atual não reproduz toda essa separação. Ele usa uma cápsula de controle e mãos em primeira pessoa, sem o conjunto completo de corpo/câmeras do prefab original.

## UMP45: referência concreta para a primeira integração

A fonte contém prefabs distintos:

- `p_ump_fp`: primeira pessoa, com componente `LocalWeapon`.
- `p_ump_tp`: terceira pessoa, com componente `RemoteWeapon`.
- `p_ump_drop`: arma no chão/loja, com componentes de drop/loja.

O prefab de primeira pessoa contém as malhas skinned `Hands` e `UMP_45`, ambas ligadas ao mesmo esqueleto de 11 ossos. A malha da arma tem 2.689 vértices; a malha das mãos tem 144. Os pesos são rígidos por vértice, sem canal de pesos fracionários: na arma, 2.543 vértices usam o osso Base, 102 o Magazine e 44 o Shutter. Na malha das mãos, os vértices são distribuídos entre Hand_R, Elb_R, Hand_L, Elb_L, Wr_L e Wr_R.

Isso é importante: o canal de índices existe, mas o canal tradicional de pesos está ausente. O conversor atual rejeita esse formato; para importar o UMP corretamente, deve tratar cada vértice como peso 1.0 no único osso indicado pelo índice.

A UMP45 tem clipes próprios de 60 FPS:

- Fire
- Idle
- Reload
- Deploy

A recarga dura aproximadamente 3,35 s e contém eventos de áudio em 0,60 s, 1,883 s, 2,45 s e 2,833 s, com nomes de eventos `smg_mag_out_0`, `smg_mag_in_0`, `smg_bolt_back_0` e `smg_bolt_forward_0`. O saque também contém eventos de tecido e ferrolho. A arma possui sockets para muzzle, ejeção de cápsula, mira, coronha e compensador.

O protótipo atual usa uma OBJ estática da UMP45 e movimento de recuo por código. Isso não equivale ao prefab original e não reproduz a animação das mãos, carregador, ferrolho, sockets ou eventos.

## HUD e entrada original

Nas cenas de gameplay foram encontrados:

- `Joystick`, `Joystick-Walk-Base` e `Joystick-Walk-Hat`
- `button_fire_left` e `button_fire_right`
- `aim_button`, `jump_button`, `reload_button` e controles de agachar
- `Crosshair`, `SniperScope`, `AimAssistance`, `AutoAiming` e `AimFire`
- `TouchControl`, `ControlsManager`, rastreador de toque e controles de câmera
- elementos de vida, dano, munição e radar

A implementação atual tem botões de mira, pulo e recarga, mas não reproduz os dois botões originais de disparo; o disparo automático centralizado foi uma aproximação e deve ser substituído por entrada manual com suporte a toque mantido.

## IA, spawn e combate

O código/metadata original aponta para uma arquitetura com:

- `PhotonAICharacter`, `PhotonAIInput`, `AIController`, `BehaviorTree`, `TriggerSensor` e `NavMeshAgent`.
- `AimAssistController`, sensores de visão, seleção de alvo, linha de visão e estados de mira.
- `WeaponBase`, `LocalWeapon`, `RemoteWeapon`, `WeaponAnimation`, `WeaponMovements`, `WeaponSoundManager`, `Bullet` e `BulletData`.
- `SpawnPointManager` com listas de pontos neutros, azuis e amarelos; `SpawnPoint` possui cooldown, raio, equipe, vizinhos e altura de spawn.

A cena da floresta contém grupos de spawn neutros e por equipe, além de pontos específicos. O protótipo atual escolhe uma posição central e procura o chão por raycast; deve passar a usar os pontos originais, após aplicar a conversão correta de coordenadas Unity→Godot.

Há dados NavMesh no conjunto original de assets. A associação exata do NavMesh da floresta e a conversão para navegação Godot ainda precisam ser verificadas antes de afirmar que a navegação original foi recuperada.

## Limitações que não podem ser escondidas

Os arquivos C# são saídas de descompilação IL2CPP. Muitos métodos são stubs sem corpo executável. Os nomes de classes, campos, assinaturas e referências ajudam a reconstruir a arquitetura, mas não equivalem ao código-fonte original.

A auditoria local não encontrou instâncias serializadas de configuração da UMP45 com os valores numéricos completos de dano, cadência, alcance e munição. As classes `Weapon`, `WeaponInfo` e `WeaponBase` revelam o esquema desses dados, mas os valores precisam ser localizados em outra fonte de configuração ou validados; não inventar números e apresentá-los como originais.

## Divergências atuais que precisam ser corrigidas

1. Arma em primeira pessoa estática, em vez do prefab skinned `p_ump_fp`.
2. Falta o corpo completo do jogador e a separação local/remoto do prefab.
3. Falta o conjunto de arma de terceira pessoa e encaixe/IK da mão esquerda.
4. Disparo automático centralizado em vez dos controles manuais esquerdo/direito.
5. Faltam eventos originais de recarga, muzzle flash, ejeção de cápsulas e áudio associado.
6. IA atual de perseguição direta não reproduz sensores, árvore de comportamento e navegação do original.
7. Spawn por centro/raycast em vez de `SpawnPointManager` e pontos originais.
8. Auditoria de build precisa verificar comportamento: movimento, rotação de câmera, mira, disparo, recarga, pulo, animações, colisão, spawn e IA. Compilar APK sozinho não é prova de funcionamento.

## Ordem de implementação recomendada

1. Importar e validar o rig original UMP45 + mãos, incluindo o formato de pesos rígidos de um osso por vértice.
2. Converter os clipes Fire/Idle/Reload/Deploy e eventos de áudio para o rig Godot.
3. Reproduzir os sockets de muzzle, ejeção e mira; importar o prefab de terceira pessoa e o alvo da mão esquerda.
4. Recriar o HUD de toque com disparo manual, mira, pulo, recarga, agachar e joystick, preservando multitouch.
5. Corrigir o prefab do jogador, transformações e spawn usando pontos originais.
6. Implementar IA com navegação, sensores, seleção de alvo, linha de visão, mira e disparo.
7. Adicionar testes automáticos de comportamento antes de gerar outro APK.

Não alterar a branch de backup dos mapas estáveis nem misturar este projeto com o projeto independente Me Cobre Aí.
