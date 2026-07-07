# Planejamento técnico — GTA Driving Bot

Documento complementar ao `README.md` com detalhes de decisão e algoritmos.

## 1. Problema do minimapa puro

O GPS no minimapa fornece uma **polyline** — não semântica de faixa.

```
Entrada:  imagem do minimapa + linha roxa
Saída:    ângulo desejado θ_target

Falta:    "este pixel à esquerda é asfalto dirigível?"
```

**Casos de falha:**

- Virar à esquerda → calçada
- Virar à esquerda → rio / muro
- Seguir linha → cortar curva por dentro (atalho inválido)
- Rotatória → sair na saída errada

**Mitigação:** camada 2 (pista) + camada 3 (obstáculo).

---

## 2. Detecção no minimapa

### 2.1 Seta do jogador

Opções (em ordem de preferência para MVP):

1. **Template matching** — recorte da seta branca/colorida
2. **Cor + contorno** — triângulo/pequeno blob no centro do minimapa rotacionado
3. **Centro fixo aproximado** — se a seta sempre está no meio do minimapa rotativo (GTA rotaciona o mapa)

No GTA V o minimapa **rotaciona** com o carro; a seta costuma ficar central. Isso simplifica:

- Posição do jogador ≈ centro da ROI do minimapa
- **Ângulo** = orientação da seta OU derivado do movimento entre frames

### 2.2 Linha do GPS

- Máscara HSV para roxo/laranja
- Morfologia para unir segmentos
- Ponto-alvo = pixel da linha mais próximo **à frente** da seta (não atrás)
- `θ_target = atan2(dy, dx)` do vetor seta → ponto-alvo

### 2.3 “Estou na rua?”

- Amostrar pixels sob a seta no minimapa
- Ruas = cinza médio; grama = verde; água = azul; prédio = escuro
- Calibrar faixas em `calibrate_minimap.py`

---

## 3. Visão frontal (fase 2)

### ROI

Faixa inferior-central da tela (onde a estrada aparece).

### Lane keeping simples

1. Converter para HSV ou Lab
2. Máscara de asfalto (cinza escuro)
3. Projeção por colunas → histograma de “asfalto por coluna”
4. Centro de massa das colunas com asfalto = `x_lane`
5. `erro_faixa = x_lane - x_centro_imagem`

### Fusão

```python
erro_total = w_gps * erro_gps + w_lane * erro_faixa

if not on_road_pixel(minimap):
    erro_total += k_recovery * erro_volta_para_rua
```

---

## 4. Checkpoints

### Waypoints em coordenadas normalizadas

```json
{ "minimap_x": 0.45, "minimap_y": 0.62, "stop_radius_px": 18 }
```

- `(x, y)` em fração da ROI do minimapa (0–1)
- Distância euclidiana da seta ao waypoint
- Se `dist < stop_radius` → estado `STOPPING`

### Parada

1. Soltar W
2. Segurar S ou Space até velocidade ≈ 0 (heurística: minimapa não muda / optical flow baixo)
3. Aguardar `checkpoint_wait_ms`
4. Próximo waypoint

---

## 5. Anti-colisão (fase 4)

### Nível básico — “túnel livre”

- ROI estreita no centro da visão frontal
- Medir % de pixels “estrada longe” (parte superior da ROI) vs “próximo”
- Se ratio < limiar → `brake = True`

### Nível médio

- Centro de massa do obstáculo (não-estrada) deslocado
- Pequena correção de volante **enquanto freia**

---

## 6. Máquina de estados

```
                    ┌──────────┐
                    │   IDLE   │
                    └────┬─────┘
                         │ F6 / start
                         ▼
              ┌──────────────────────┐
         ┌───►│     NAVIGATING       │◄───┐
         │    └──────────┬───────────┘    │
         │               │ waypoint near  │
         │               ▼                │
         │    ┌──────────────────────┐    │
         │    │ APPROACHING_CHECKPOINT│   │
         │    └──────────┬───────────┘    │
         │               │ dist < radius  │
         │               ▼                │
         │    ┌──────────────────────┐    │
         │    │      STOPPING        │    │
         │    └──────────┬───────────┘    │
         │               │ stopped        │
         │               ▼                │
         │    ┌──────────────────────┐    │
         │    │  AT_CHECKPOINT       │────┘
         │    └──────────────────────┘   next waypoint
         │
         │    obstacle detected
         │    ┌──────────────────────┐
         └────│     OBSTACLE         │
              └──────────┬───────────┘
                         │ clear
                         └──────────────► NAVIGATING

         off road / lost route
              ┌──────────────────────┐
              │    RECOVERY          │
              └──────────────────────┘
```

---

## 7. Controle (PID simplificado)

```python
# Erro angular em graus, normalizado
steer = kp * erro_angular + kd * (erro_angular - erro_angular_prev)

# Converter para pulsos A/D
if steer > deadband:
    tap_key("d", duration_ms=clamp(steer * gain))
elif steer < -deadband:
    tap_key("a", duration_ms=clamp(-steer * gain))

# Throttle
if not braking and abs(erro_angular) < 15:
    hold_key("w")
else:
    release_key("w")  # reduzir em curva fechada
```

**Volante analógico simulado:** pulsos de 30–80 ms repetidos a 10–20 Hz são mais suaves que key down contínuo.

---

## 8. Debug (igual fishing bot)

- Overlay no minimapa: seta, linha GPS, waypoints, estado
- Overlay na visão frontal: máscara de asfalto, centro da faixa
- `debug_record_frames` → pasta `captures/`
- Log: `drive_bot.log.txt`

---

## 9. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Minimapa muda com resolução/UI | `calibrate_minimap.py` + `config.json` |
| Cores do GPS variam (dia/noite) | Calibração HSV + múltiplos ranges |
| Latência captura → controle | `capture_fps` 30+, buffer mínimo |
| FiveM UI diferente | Perfil de config por servidor |
| SendInput sem foco | Aviso no README; bot só com jogo ativo |

---

## 10. Critérios de “fase concluída”

| Fase | Critério de aceite |
|------|-------------------|
| 1 | 60 s seguindo GPS em estrada rural sem intervenção |
| 2 | 0 calçadas em 5 voltas de rota curta conhecida |
| 3 | Para em 3 waypoints com tolerância ±20 px |
| 4 | Freia antes de muro estático em 8/10 tentativas |
| 5 | Recupera após sair da rota em < 5 s |
