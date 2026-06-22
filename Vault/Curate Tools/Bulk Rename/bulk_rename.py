import os
import re
import sys

def cabecalho():
    print()
    print(" ╔═══════════════════════════════════════════════╗")
    print(" ║       PADRONIZADOR DE NOMES DE ARQUIVOS       ║")
    print(" ╚═══════════════════════════════════════════════╝")
    print()

def extrair_padrao(nome):
    """Substitui o número do episódio por XX para gerar o template do padrão."""
    m = re.search(r'(\D)(\d{2,3})(\D)', nome)
    if m:
        return nome[:m.start()] + m.group(1) + "XX" + m.group(3) + nome[m.end():]
    return None

def main():
    cabecalho()

    pasta = os.path.dirname(os.path.abspath(__file__))

    padroes_encontrados = {}  # padrao -> lista de (num, nome)

    for nome in os.listdir(pasta):
        if nome.lower().endswith(".mkv"):
            m = re.search(r'\D(\d{2,3})\D', nome)
            if m:
                num = int(m.group(1))
                padrao = extrair_padrao(nome)
                if padrao:
                    if padrao not in padroes_encontrados:
                        padroes_encontrados[padrao] = []
                    padroes_encontrados[padrao].append((num, nome))

    total = sum(len(v) for v in padroes_encontrados.values())

    if not padroes_encontrados:
        print("  [!] Nenhum arquivo .mkv compatível encontrado na pasta.")
        input("\n  Pressione ENTER para sair: ")
        sys.exit()

    print(f"  [+] Encontrados {total} episódios com {len(padroes_encontrados)} padrão(ões) de nome.\n")

    lista_padroes = list(padroes_encontrados.keys())

    print("  PADRÕES DETECTADOS NA PASTA:")
    print("  -----------------------------------")
    for i, p in enumerate(lista_padroes, 1):
        qtd = len(padroes_encontrados[p])
        print(f"  [ {i} ]  {p}  ({qtd} arquivo(s))")
    print(f"  [ {len(lista_padroes) + 1} ]  Criar padrão customizado...")

    opcao = input("\n  > Para qual padrão deseja padronizar TODOS os arquivos? ").strip()

    try:
        opcao_num = int(opcao)
    except ValueError:
        print("\n  [X] Opção inválida!")
        input("\n  Pressione ENTER para sair: ")
        sys.exit()

    if 1 <= opcao_num <= len(lista_padroes):
        padrao_destino = lista_padroes[opcao_num - 1]
    elif opcao_num == len(lista_padroes) + 1:
        padrao_destino = input("\n  > Digite o padrão (use 'XX' onde o número deve entrar): ").strip()
        if "XX" not in padrao_destino:
            print("\n  [X] Erro: Seu padrão precisa conter 'XX' para inserir o número!")
            input("\n  Pressione ENTER para sair: ")
            sys.exit()
    else:
        print("\n  [X] Opção inválida!")
        input("\n  Pressione ENTER para sair: ")
        sys.exit()

    # Junta todos os arquivos e ordena por número
    todos = []
    for v in padroes_encontrados.values():
        todos.extend(v)
    todos.sort(key=lambda x: x[0])

    print("\n ───────────────── PREVIEW DA ALTERAÇÃO ─────────────────")
    for i, (num, nome_original) in enumerate(todos):
        novo_nome = padrao_destino.replace("XX", f"{num:02d}")
        if i < 3:
            print(f"  Antes:  {nome_original}")
            print(f"  Depois: {novo_nome}")
            print()
    if len(todos) > 3:
        print(f"  ... e mais {len(todos) - 3} arquivo(s).")
    print(" ────────────────────────────────────────────────────────")

    confirmacao = input("\n  > Deseja aplicar essas alterações em todos os arquivos? (S/N): ").strip().upper()

    if confirmacao == "S":
        print()
        erros = 0
        for num, nome_original in todos:
            novo_nome = padrao_destino.replace("XX", f"{num:02d}")
            origem = os.path.join(pasta, nome_original)
            destino = os.path.join(pasta, novo_nome)
            if origem == destino:
                print(f"  [=] {nome_original}  (sem alteração)")
                continue
            try:
                os.rename(origem, destino)
                print(f"  [✔] {nome_original}  →  {novo_nome}")
            except Exception as e:
                print(f"  [X] Erro ao renomear '{nome_original}': {e}")
                erros += 1
        if erros == 0:
            print("\n  [✔] Sucesso! Todos os arquivos foram padronizados.")
        else:
            print(f"\n  [!] Concluído com {erros} erro(s).")
    else:
        print("\n  [!] Operação cancelada. Nenhum arquivo foi modificado.")

    input("\n  Pressione ENTER para sair: ")

if __name__ == "__main__":
    main()
