#Requires -Version 5.1

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$InputFile
)

try {
    # ==================== CONFIGURAÇÃO ====================
    $Script:Config = @{
        FFprobePath = "C:\FFmpeg\bin\ffprobe.exe"
        Colors = @{
            Title = "Cyan"
            Success = "Green"
            Warning = "Yellow"
            Error = "Red"
            Info = "White"
            Highlight = "Magenta"
        }
    }

    # ==================== FUNÇÕES ====================

    function Write-ColorText {
        param(
            [string]$Text,
            [string]$Color = "White",
            [switch]$NoNewline
        )
        Write-Host $Text -ForegroundColor $Color -NoNewline:$NoNewline
    }

    function Write-Header {
        param([string]$Title)
        Write-Host "`n" -NoNewline
        Write-Host ("=" * 70) -ForegroundColor $Script:Config.Colors.Title
        Write-Host " $Title" -ForegroundColor $Script:Config.Colors.Title
        Write-Host ("=" * 70) -ForegroundColor $Script:Config.Colors.Title
    }

    function Write-Section {
        param([string]$Title)
        Write-Host "`n+-- " -ForegroundColor DarkGray -NoNewline
        Write-Host $Title -ForegroundColor $Script:Config.Colors.Highlight -NoNewline
        Write-Host " --+" -ForegroundColor DarkGray
    }

    function Test-FFprobe {
        if (-not (Test-Path -LiteralPath $Script:Config.FFprobePath)) {
            Write-ColorText "X FFprobe nao encontrado em: " $Script:Config.Colors.Error
            Write-ColorText $Script:Config.FFprobePath $Script:Config.Colors.Warning
            Write-Host "`n"
            
            # Tenta encontrar no PATH
            $ffprobeInPath = Get-Command ffprobe -ErrorAction SilentlyContinue
            if ($ffprobeInPath) {
                Write-ColorText "OK Encontrado no PATH do sistema!" $Script:Config.Colors.Success
                $Script:Config.FFprobePath = $ffprobeInPath.Source
                return $true
            }
            
            Write-ColorText "Instale o FFmpeg ou ajuste o caminho no script." $Script:Config.Colors.Warning
            return $false
        }
        return $true
    }

    function Get-FileSelection {
        Add-Type -AssemblyName System.Windows.Forms
        
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = "Selecione um arquivo de video"
        $dialog.Filter = "Arquivos MKV (*.mkv)|*.mkv|Todos os videos (*.mp4;*.avi;*.mkv;*.mov)|*.mp4;*.avi;*.mkv;*.mov|Todos (*.*)|*.*"
        $dialog.InitialDirectory = $PSScriptRoot
        
        if ($dialog.ShowDialog() -eq 'OK') {
            return $dialog.FileName
        }
        return $null
    }

    function Get-MediaInfo {
        param([string]$FilePath)
        
        # Executa ffprobe com saída em JSON (aspas duplas protegem colchetes)
        $jsonOutput = & $Script:Config.FFprobePath -v quiet -print_format json -show_format -show_streams "`"$FilePath`"" 2>&1 | Out-String
        
        try {
            $mediaData = $jsonOutput | ConvertFrom-Json
            return $mediaData
        } catch {
            Write-ColorText "X Erro ao analisar arquivo" $Script:Config.Colors.Error
            Write-Host "`nDetalhes: $($_.Exception.Message)" -ForegroundColor Yellow
            return $null
        }
    }

    function Format-FileSize {
        param([long]$Bytes)
        
        if ($Bytes -ge 1GB) {
            return "{0:N2} GB" -f ($Bytes / 1GB)
        } elseif ($Bytes -ge 1MB) {
            return "{0:N2} MB" -f ($Bytes / 1MB)
        } elseif ($Bytes -ge 1KB) {
            return "{0:N2} KB" -f ($Bytes / 1KB)
        } else {
            return "$Bytes bytes"
        }
    }

    function Format-Duration {
        param([string]$Seconds)
        
        $ts = [TimeSpan]::FromSeconds([double]$Seconds)
        return "{0:D2}:{1:D2}:{2:D2}" -f $ts.Hours, $ts.Minutes, $ts.Seconds
    }

    function Show-StreamInfo {
        param(
            [object]$MediaData,
            [string]$FilePath
        )
        
        Write-Section "INFORMACOES DO ARQUIVO"
        $fileInfo = Get-Item -LiteralPath $FilePath
        Write-ColorText "  Nome: " $Script:Config.Colors.Info -NoNewline
        Write-ColorText $fileInfo.Name $Script:Config.Colors.Highlight
        
        Write-ColorText "  Tamanho: " $Script:Config.Colors.Info -NoNewline
        Write-ColorText (Format-FileSize $fileInfo.Length) $Script:Config.Colors.Success
        
        if ($MediaData.format.duration) {
            Write-ColorText "  Duracao: " $Script:Config.Colors.Info -NoNewline
            Write-ColorText (Format-Duration $MediaData.format.duration) $Script:Config.Colors.Success
        }
        
        if ($MediaData.format.bit_rate) {
            $bitrateMbps = [math]::Round([long]$MediaData.format.bit_rate / 1000000, 2)
            Write-ColorText "  Bitrate: " $Script:Config.Colors.Info -NoNewline
            Write-ColorText "$bitrateMbps Mbps" $Script:Config.Colors.Success
        }
        
        # Streams de vídeo
        $videoStreams = $MediaData.streams | Where-Object { $_.codec_type -eq "video" }
        if ($videoStreams) {
            Write-Section "STREAMS DE VIDEO"
            $videoIndex = 1
            foreach ($stream in $videoStreams) {
                Write-ColorText "  [$videoIndex] " $Script:Config.Colors.Highlight -NoNewline
                Write-ColorText "$($stream.codec_name) " $Script:Config.Colors.Success -NoNewline
                Write-ColorText "| " $Script:Config.Colors.Info -NoNewline
                Write-ColorText "$($stream.width)x$($stream.height) " $Script:Config.Colors.Info -NoNewline
                
                if ($stream.r_frame_rate) {
                    $fpsValues = $stream.r_frame_rate -split '/'
                    if ($fpsValues.Count -eq 2) {
                        $fpsCalc = [double]$fpsValues[0] / [double]$fpsValues[1]
                        Write-ColorText "| " $Script:Config.Colors.Info -NoNewline
                        Write-ColorText ("{0:N2} fps" -f $fpsCalc) $Script:Config.Colors.Info
                    }
                } else {
                    Write-Host ""
                }
                
                # Bitrate do vídeo (tenta campo padrão, depois metadata BPS do MKV)
                $videoBitrate = $null
                if ($stream.bit_rate) {
                    $videoBitrate = [long]$stream.bit_rate
                } elseif ($stream.tags.BPS) {
                    $videoBitrate = [long]$stream.tags.BPS
                }
                if ($videoBitrate) {
                    $videoBitrateMbps = [math]::Round($videoBitrate / 1000000, 2)
                    Write-ColorText "      Bitrate: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText "$videoBitrateMbps Mbps" $Script:Config.Colors.Success
                }
                
                # Número de frames (tenta campo padrão, depois metadata NUMBER_OF_FRAMES do MKV)
                $frameCount = $null
                if ($stream.nb_frames) {
                    $frameCount = $stream.nb_frames
                } elseif ($stream.tags.NUMBER_OF_FRAMES) {
                    $frameCount = $stream.tags.NUMBER_OF_FRAMES
                }
                if ($frameCount) {
                    Write-ColorText "      Frames: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText "$frameCount frames" $Script:Config.Colors.Success
                }
                
                # Duração do stream de vídeo (tenta campo padrão, depois metadata DURATION do MKV)
                $videoDuration = $null
                if ($stream.duration) {
                    $videoDuration = $stream.duration
                } elseif ($stream.tags.DURATION) {
                    # DURATION vem no formato "HH:MM:SS.ffffff", converte para segundos
                    $durationStr = $stream.tags.DURATION
                    if ($durationStr -match '(\d+):(\d+):(\d+)\.(\d+)') {
                        $hours = [int]$matches[1]
                        $minutes = [int]$matches[2]
                        $seconds = [int]$matches[3]
                        $videoDuration = ($hours * 3600) + ($minutes * 60) + $seconds
                    }
                }
                if ($videoDuration) {
                    Write-ColorText "      Duracao: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText (Format-Duration $videoDuration) $Script:Config.Colors.Success
                }
                
                if ($stream.pix_fmt) {
                    Write-ColorText "      Pixel Format: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText $stream.pix_fmt $Script:Config.Colors.Warning
                }
                
                if ($stream.color_space) {
                    Write-ColorText "      Color Space: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText $stream.color_space $Script:Config.Colors.Warning
                }
                
                $videoIndex++
            }
        }
        
        # Streams de áudio
        $audioStreams = $MediaData.streams | Where-Object { $_.codec_type -eq "audio" }
        if ($audioStreams) {
            Write-Section "STREAMS DE AUDIO"
            $audioIndex = 1
            foreach ($stream in $audioStreams) {
                Write-ColorText "  [$audioIndex] " $Script:Config.Colors.Highlight -NoNewline
                Write-ColorText "$($stream.codec_name) " $Script:Config.Colors.Success -NoNewline
                Write-ColorText "| " $Script:Config.Colors.Info -NoNewline
                
                if ($stream.channels) {
                    $channelLayout = if ($stream.channel_layout) { $stream.channel_layout } else { "$($stream.channels)ch" }
                    Write-ColorText "$channelLayout " $Script:Config.Colors.Info -NoNewline
                }
                
                if ($stream.sample_rate) {
                    Write-ColorText "| " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText "$($stream.sample_rate) Hz" $Script:Config.Colors.Info
                } else {
                    Write-Host ""
                }
                
                # Bitrate do áudio (tenta campo padrão, depois metadata BPS do MKV)
                $audioBitrate = $null
                if ($stream.bit_rate) {
                    $audioBitrate = [long]$stream.bit_rate
                } elseif ($stream.tags.BPS) {
                    $audioBitrate = [long]$stream.tags.BPS
                }
                if ($audioBitrate) {
                    $audioBitrateKbps = [math]::Round($audioBitrate / 1000, 2)
                    Write-ColorText "      Bitrate: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText "$audioBitrateKbps kbps" $Script:Config.Colors.Success
                }
                
                # Duração do stream de áudio (tenta campo padrão, depois metadata DURATION do MKV)
                $audioDuration = $null
                if ($stream.duration) {
                    $audioDuration = $stream.duration
                } elseif ($stream.tags.DURATION) {
                    # DURATION vem no formato "HH:MM:SS.ffffff", converte para segundos
                    $durationStr = $stream.tags.DURATION
                    if ($durationStr -match '(\d+):(\d+):(\d+)\.(\d+)') {
                        $hours = [int]$matches[1]
                        $minutes = [int]$matches[2]
                        $seconds = [int]$matches[3]
                        $audioDuration = ($hours * 3600) + ($minutes * 60) + $seconds
                    }
                }
                if ($audioDuration) {
                    Write-ColorText "      Duracao: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText (Format-Duration $audioDuration) $Script:Config.Colors.Success
                }
                
                if ($stream.tags.language) {
                    Write-ColorText "      Idioma: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText $stream.tags.language.ToUpper() $Script:Config.Colors.Warning
                }
                
                if ($stream.tags.title) {
                    Write-ColorText "      Titulo: " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText $stream.tags.title $Script:Config.Colors.Warning
                }
                
                $audioIndex++
            }
        }
        
        # Streams de legenda
        $subtitleStreams = $MediaData.streams | Where-Object { $_.codec_type -eq "subtitle" }
        if ($subtitleStreams) {
            Write-Section "STREAMS DE LEGENDA"
            $subIndex = 1
            foreach ($stream in $subtitleStreams) {
                Write-ColorText "  [$subIndex] " $Script:Config.Colors.Highlight -NoNewline
                Write-ColorText "$($stream.codec_name) " $Script:Config.Colors.Success -NoNewline
                
                if ($stream.tags.language) {
                    Write-ColorText "| " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText $stream.tags.language.ToUpper() $Script:Config.Colors.Warning -NoNewline
                }
                
                if ($stream.tags.title) {
                    Write-ColorText " | " $Script:Config.Colors.Info -NoNewline
                    Write-ColorText $stream.tags.title $Script:Config.Colors.Info
                } else {
                    Write-Host ""
                }
                
                $subIndex++
            }
        }
    }

    function Save-Report {
        param(
            [string]$FilePath,
            [string]$OutputPath
        )
        
        Write-Host "`n"
        Write-ColorText "Salvando relatorio detalhado... " $Script:Config.Colors.Info
        
        # Gera relatório completo (aspas duplas protegem colchetes)
        $fullReport = & $Script:Config.FFprobePath -i "`"$FilePath`"" -hide_banner 2>&1 | Out-String
        $fullReport | Out-File -LiteralPath $OutputPath -Encoding UTF8
        
        Write-ColorText "OK " $Script:Config.Colors.Success -NoNewline
        Write-ColorText "Salvo em: " $Script:Config.Colors.Info -NoNewline
        Write-ColorText $OutputPath $Script:Config.Colors.Highlight
    }

    # ==================== MAIN ====================

    Clear-Host

    Write-Header "ANALISADOR DE MIDIA - FFprobe"

    # Verifica FFprobe
    if (-not (Test-FFprobe)) {
        Read-Host "`nPressione Enter para sair"
        exit 1
    }

    # Determina arquivo de entrada
    $targetFile = $null

    if ($InputFile -and $InputFile.Count -gt 0) {
        # Arquivo arrastado
        $targetFile = $InputFile[0]
        Write-ColorText "`nArquivo recebido via drag-and-drop" $Script:Config.Colors.Success
    } else {
        # Abre seletor de arquivos
        Write-ColorText "`nNenhum arquivo fornecido. Abrindo seletor..." $Script:Config.Colors.Warning
        Start-Sleep -Milliseconds 500
        $targetFile = Get-FileSelection
        
        if (-not $targetFile) {
            Write-ColorText "`nX Nenhum arquivo selecionado." $Script:Config.Colors.Error
            Read-Host "`nPressione Enter para sair"
            exit 0
        }
    }

    # Valida arquivo
    if (-not (Test-Path -LiteralPath $targetFile)) {
        Write-ColorText "`nX Arquivo nao encontrado: " $Script:Config.Colors.Error
        Write-ColorText $targetFile $Script:Config.Colors.Warning
        Read-Host "`nPressione Enter para sair"
        exit 1
    }

    # Analisa arquivo
    Write-ColorText "`nAnalisando arquivo... " $Script:Config.Colors.Info
    $mediaData = Get-MediaInfo -FilePath $targetFile

    if (-not $mediaData) {
        Read-Host "`nPressione Enter para sair"
        exit 1
    }

    # Exibe informações formatadas
    Show-StreamInfo -MediaData $mediaData -FilePath $targetFile

    # Salva relatório
    $outputPath = [System.IO.Path]::ChangeExtension($targetFile, ".txt")
    Save-Report -FilePath $targetFile -OutputPath $outputPath

    # Menu de ações
    Write-Host "`n" -NoNewline
    Write-Host ("=" * 70) -ForegroundColor DarkGray
    Write-ColorText "`nACOES DISPONIVEIS:" $Script:Config.Colors.Title
    Write-ColorText "  [1] " $Script:Config.Colors.Highlight -NoNewline
    Write-Host "Abrir relatorio em texto"
    Write-ColorText "  [2] " $Script:Config.Colors.Highlight -NoNewline
    Write-Host "Abrir pasta do arquivo"
    Write-ColorText "  [3] " $Script:Config.Colors.Highlight -NoNewline
    Write-Host "Analisar outro arquivo"
    Write-ColorText "  [Q] " $Script:Config.Colors.Highlight -NoNewline
    Write-Host "Sair"

    Write-Host "`n" -NoNewline
    $choice = Read-Host "Escolha"

    switch ($choice.ToUpper()) {
        "1" {
            Start-Process notepad.exe -ArgumentList $outputPath
        }
        "2" {
            Start-Process explorer.exe -ArgumentList "/select,`"$targetFile`""
        }
        "3" {
            & $PSCommandPath
        }
    }

    Write-ColorText "`nOK Concluido!" $Script:Config.Colors.Success
    Start-Sleep -Milliseconds 800

} catch {
    Write-Host "`n`n==== ERRO DETECTADO ====" -ForegroundColor Red
    Write-Host "Mensagem: " -NoNewline -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor White
    Write-Host "`nLinha: " -NoNewline -ForegroundColor Yellow
    Write-Host $_.InvocationInfo.ScriptLineNumber -ForegroundColor White
    Write-Host "`nComando: " -NoNewline -ForegroundColor Yellow
    Write-Host $_.InvocationInfo.Line -ForegroundColor Gray
    Write-Host "`n========================`n" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
}