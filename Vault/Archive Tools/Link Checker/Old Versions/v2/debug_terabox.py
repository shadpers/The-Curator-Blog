import requests
import re
import os

def debug_terabox(url):
    """Debug específico para TeraBox"""
    print(f"\n{'='*60}")
    print(f"DEBUGGING: {url}")
    print(f"{'='*60}\n")
    
    url = url.replace("1024terabox.com", "www.terabox.com")
    print(f"URL normalizada: {url}\n")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        print(f"Status Code: {response.status_code}")
        print(f"Final URL: {response.url}\n")
        
        text = response.text
        
        # Verifica sinais de OFFLINE
        offline_words = ["expired", "error", "deleted", "not exist"]
        found_offline = False
        print("Checando palavras de OFFLINE:")
        for word in offline_words:
            if word in text.lower():
                print(f"  ✓ Encontrado: '{word}'")
                found_offline = True
        if not found_offline:
            print("  Nenhum indicador de OFFLINE encontrado")
        
        # Busca padrões de contagem
        print("\nBuscando padrões de contagem:")
        
        # Busca window.__INIT_DATA__
        match = re.search(r'window\.__INIT_DATA__\s*=\s*(\{.*?\});', text, re.DOTALL)
        if match:
            init_data = match.group(1)
            print(f"  ✓ window.__INIT_DATA__ encontrado ({len(init_data)} chars)")
            
            # Conta server_filename
            file_count = init_data.count('"server_filename"')
            print(f"  ✓ Arquivos detectados: {file_count}")
            
            # Busca fileCount específico
            fc_match = re.search(r'"fileCount"\s*:\s*(\d+)', init_data)
            if fc_match:
                print(f"  ✓ fileCount explícito: {fc_match.group(1)}")
        else:
            print("  ✗ window.__INIT_DATA__ não encontrado")
        
        # Busca locals.mset
        match = re.search(r'locals\.mset\((\{.*?\})\);', text, re.DOTALL)
        if match:
            locals_data = match.group(1)
            print(f"  ✓ locals.mset encontrado ({len(locals_data)} chars)")
            file_count = locals_data.count('"server_filename"')
            if file_count > 0:
                print(f"  ✓ Arquivos detectados: {file_count}")
        
        # Busca por "list" array
        match = re.search(r'"list"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if match:
            list_data = match.group(1)
            file_count = list_data.count('"server_filename"')
            print(f"  ✓ Array 'list' encontrado com {file_count} arquivos")
        
        # Busca padrões simples
        simple_patterns = [
            (r'"fileCount"\s*:\s*(\d+)', 'fileCount'),
            (r'"file_count"\s*:\s*(\d+)', 'file_count'),
            (r'(\d+)\s+files?', 'X files pattern'),
        ]
        
        for pattern, name in simple_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                print(f"  ✓ {name}: {matches[0]}")
        
        # Busca empty folder
        if 'empty folder' in text.lower() or '0 files' in text.lower():
            print(f"  ✓ Pasta vazia detectada!")
        
        # Salva HTML para inspeção
        html_file = 'debug_terabox.html'
        full_path = os.path.abspath(html_file)
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"\n✓ HTML salvo em:\n  {full_path}")
        print(f"  Tamanho: {len(text)} chars")
        
    except Exception as e:
        print(f"\n✗ ERRO: {e}")

if __name__ == "__main__":
    # Testa os links problemáticos
    links = [
        ("2 FILES", "https://1024terabox.com/s/1m4axG3QsmZ6zAJTpIk4NWw"),
        ("EMPTY", "https://1024terabox.com/s/1W23AWTymtCAZNaejV9pGPA"),
        ("DOWN", "https://1024terabox.com/s/1MTSGKAT7hcj-M-rgRk4oKA"),
        ("SINGLE UP", "https://1024terabox.com/s/1asoTsBJPpQOP0XQGH0ItRw"),
        ("SINGLE DOWN", "https://1024terabox.com/s/1TIrL15xi1briUadR0kIyUw"),
    ]
    
    for name, link in links:
        print(f"\n\n{'#'*60}")
        print(f"# TESTANDO: {name}")
        print(f"{'#'*60}")
        debug_terabox(link)
        input("\nPressione ENTER para próximo...")