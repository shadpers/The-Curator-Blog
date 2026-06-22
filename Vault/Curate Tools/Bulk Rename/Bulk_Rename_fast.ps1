Clear-Host

# --- CABEÇALHO ---
Write-Host ""
Write-Host " ╔═══════════════════════════════════════════════╗ " -ForegroundColor Cyan
Write-Host " ║       PADRONIZADOR DE NOMES DE ARQUIVOS       ║ " -ForegroundColor White -BackgroundColor DarkCyan
Write-Host " ╚═══════════════════════════════════════════════╝ " -ForegroundColor Cyan
Write-Host ""

# Busca todos os arquivos .mkv no diretório atual
$arquivos = Get-ChildItem -Filter "*.mkv"
$dadosArquivos = @()

foreach ($arquivo in $arquivos) {
    if ($arquivo.BaseName -match '\D(\d{2,3})\D') {
        $epNum = [int]$matches[1]
        $dadosArquivos += [PSCustomObject]@{
            ArquivoOriginal = $arquivo
            NomeOriginal    = $arquivo.Name
            NumEpisodio     = $epNum
        }
    }
}

$dadosArquivos = $dadosArquivos | Sort-Object NumEpisodio

if ($dadosArquivos.Count -eq 0) {
    Write-Host "  [!] Nenhum arquivo de vídeo compatível encontrado na pasta." -ForegroundColor Red
    Write-Host ""
    Read-Host "  Pressione ENTER para sair"
    exit
}

Write-Host "  [+] Encontrados " -ForegroundColor Green -NoNewline
Write-Host "$($dadosArquivos.Count) episódios" -ForegroundColor White -NoNewline
Write-Host " e ordenados com sucesso!`n" -ForegroundColor Green

# --- MENU DE OPÇÕES ---
Write-Host "  ESCOLHA O PADRÃO DE NOMENCLATURA:" -ForegroundColor DarkYellow
Write-Host "  -----------------------------------" -ForegroundColor DarkGray
Write-Host "  [ 1 ] " -ForegroundColor Cyan -NoNewline; Write-Host "ReZERO S2 Castellano Cap XX.mkv"
Write-Host "  [ 2 ] " -ForegroundColor Cyan -NoNewline; Write-Host "ReZERO S2 - S02EXX.mkv"
Write-Host "  [ 3 ] " -ForegroundColor Cyan -NoNewline; Write-Host "ReZero_S2_XX.mkv"
Write-Host "  [ 4 ] " -ForegroundColor Cyan -NoNewline; Write-Host "Criar meu próprio padrão customizado..." -ForegroundColor Yellow

Write-Host "`n  > Digite o número da opção desejada: " -ForegroundColor Green -NoNewline
$opcao = Read-Host

$padrao = ""
switch ($opcao) {
    '1' { $padrao = "ReZERO S2 Castellano Cap XX.mkv" }
    '2' { $padrao = "ReZERO S2 - S02EXX.mkv" }
    '3' { $padrao = "ReZero_S2_XX.mkv" }
    '4' {
        Write-Host "`n  > Digite o padrão (Use 'XX' onde o número deve entrar): " -ForegroundColor Yellow -NoNewline
        $padrao = Read-Host
        if (-not $padrao.Contains("XX")) {
            Write-Host "`n  [X] Erro: Seu padrão precisa conter 'XX' para inserir o número!" -ForegroundColor Red
            Read-Host "`n  Pressione ENTER para sair"
            exit
        }
    }
    default {
        Write-Host "`n  [X] Opção inválida!" -ForegroundColor Red
        Read-Host "`n  Pressione ENTER para sair"
        exit
    }
}

# --- PREVIEW ---
Write-Host "`n ───────────────── PREVIEW DA ALTERAÇÃO ─────────────────" -ForegroundColor DarkCyan
$contadorPreview = 0
foreach ($item in $dadosArquivos) {
    $numFormatado = "{0:D2}" -f $item.NumEpisodio
    $novoNome = $padrao -replace "XX", $numFormatado
    
    if ($contadorPreview -lt 3) {
        Write-Host "  Antes:  " -ForegroundColor DarkGray -NoNewline
        Write-Host $item.NomeOriginal -ForegroundColor Gray
        Write-Host "  Depois: " -ForegroundColor DarkGray -NoNewline
        Write-Host $novoNome -ForegroundColor White
        Write-Host ""
    }
    $contadorPreview++
}
Write-Host " ────────────────────────────────────────────────────────" -ForegroundColor DarkCyan

Write-Host "`n  > Deseja aplicar essas alterações em todos os arquivos? (S/N): " -ForegroundColor Yellow -NoNewline
$confirmacao = Read-Host

if ($confirmacao -match '^[sS]') {
    Write-Host ""
    foreach ($item in $dadosArquivos) {
        $numFormatado = "{0:D2}" -f $item.NumEpisodio
        $novoNome = $padrao -replace "XX", $numFormatado
        
        Rename-Item -Path $item.ArquivoOriginal.FullName -NewName $novoNome
    }
    Write-Host "  [✔] Sucesso! Todos os arquivos foram padronizados." -ForegroundColor Green
} else {
    Write-Host "`n  [!] Operação cancelada. Nenhum arquivo foi modificado." -ForegroundColor Red
}

Write-Host ""
Read-Host "  Pressione ENTER para sair"
