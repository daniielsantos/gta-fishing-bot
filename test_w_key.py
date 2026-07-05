"""
Teste isolado da tecla W (anti-afk).

Uso:
  1. Abra o jogo e deixe o personagem parado
  2. Clique na janela do jogo (foco)
  3. Rode: .venv\\Scripts\\python.exe test_w_key.py
  4. Voce tera 5s para garantir que o jogo esta em foco
  5. W sera mantida por 5 segundos - o personagem deve andar para frente
"""

from __future__ import annotations

import sys
import time

from keyboard_input import debug_key_info, hold_key


def main() -> None:
    hold_sec = 5.0
    print("=== Teste tecla W ===")
    print(debug_key_info("w"))
    print("Metodo: SendInput com SCANCODE (compativel com jogos)")
    print()
    print("Clique na janela do JOGO agora.")
    print("W sera pressionada em 5 segundos...")
    sys.stdout.flush()

    for remaining in range(5, 0, -1):
        print(f"  {remaining}...")
        sys.stdout.flush()
        time.sleep(1)

    print("[test] W DOWN - segurando 5s...")
    sys.stdout.flush()
    t0 = time.perf_counter()
    hold_key("w", hold_ms=hold_sec * 1000, use_scancode=True)
    elapsed = time.perf_counter() - t0
    print(f"[test] W UP - concluido em {elapsed:.2f}s")
    print()
    print("O personagem andou para frente?")
    print("  SIM -> anti-afk ok no bot")
    print("  NAO -> jogo precisa estar em foco ou use borderless/janela")


if __name__ == "__main__":
    main()
